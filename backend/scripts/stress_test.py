# ruff: noqa: E501 - report table formatting
"""Stress test: N virtual users run every practice flow against the API at the same time.

Each user registers, logs in, reads the light endpoints (profile, dashboard, topics...),
then runs the Writing, Reading, Listening and Speaking flows end to end: create the
exercise, wait for the AI job, start an attempt, answer, submit and fetch the evaluation.
Every HTTP call and every AI job is timed; a summary is printed and saved.

Usage (from backend/, API running):
    python scripts/stress_test.py                          # 30 users, all flows
    python scripts/stress_test.py --users 10 --flows writing,reading
    python scripts/stress_test.py --parallel-flows         # each user runs 3 flows at once
    python scripts/stress_test.py --wav my_voice.wav       # real speech for Speaking (real AI)

Before running:
  * Set AUTH_RATE_LIMIT_ENABLED=false in backend/.env (register/login allow 10 per 5 min
    per IP, so 30 users from one machine would be refused) and restart the API.
  * With real AI, raise WORKER_CONCURRENCY (default 1 = one job at a time) and expect
    provider rate limits. Try a small run first (--users 3).

Needs only httpx:  pip install httpx
"""

import argparse
import asyncio
import csv
import io
import json
import math
import random
import struct
import sys
import time
import uuid
import wave
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import httpx

ESSAY = (
    "Last year I visited my grandmother in a small village near Bandung. The air was fresh "
    "and the people was very friendly. Every morning we walked to the market and buyed "
    "vegetables for lunch. I think living in a village is more relax than living in a big "
    "city, because there is less traffic and noise. However, there are not many jobs, so "
    "young people often move to the city. In the future I want to visit her again and help "
    "her in the garden. It was one of the best holiday in my life."
)
TERMINAL = {"succeeded", "failed", "cancelled"}


# ---------------------------------------------------------------- metrics
@dataclass
class Metrics:
    requests: list[dict] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)
    flows: list[dict] = field(default_factory=list)
    health: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def req(self, user, name, status, ms, code=None):
        self.requests.append(
            {"user": user, "endpoint": name, "status": status, "ms": round(ms, 1), "code": code}
        )

    def err(self, text):
        if len(self.errors) < 400:
            self.errors.append(text)


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


class FlowError(Exception):
    pass


# ---------------------------------------------------------------- one virtual user
class User:
    def __init__(self, idx, args, client, metrics, run_id, wav):
        self.idx, self.args, self.c, self.m = idx, args, client, metrics
        self.email = f"stress-{run_id}-{idx}@example.test"
        self.password = "stress-test-password-1"
        self.token = self.refresh_token = None
        self.wav = wav

    # -------------------------------------------------- http
    async def call(
        self,
        method,
        path,
        name,
        *,
        json_body=None,
        files=None,
        data=None,
        auth=True,
        idem=False,
        expect=(200,),
        raw=False,
        headers=None,
    ):
        hdrs = dict(headers or {})
        if idem:
            hdrs["Idempotency-Key"] = str(uuid.uuid4())
        for attempt in range(2):
            if auth:
                hdrs["Authorization"] = f"Bearer {self.token}"
            t0 = time.perf_counter()
            try:
                r = await self.c.request(
                    method, path, json=json_body, files=files, data=data, headers=hdrs
                )
            except httpx.HTTPError as e:
                ms = (time.perf_counter() - t0) * 1000
                self.m.req(self.idx, name, 0, ms, type(e).__name__)
                raise FlowError(f"{name}: {type(e).__name__}") from None
            ms = (time.perf_counter() - t0) * 1000
            code = None
            if r.status_code >= 400:
                try:
                    code = r.json().get("code")
                except Exception:
                    code = None
            self.m.req(self.idx, name, r.status_code, ms, code)
            if r.status_code == 401 and auth and attempt == 0 and self.refresh_token:
                await self.refresh()
                continue
            if r.status_code not in expect:
                body = r.text[:200].replace("\n", " ")
                raise FlowError(f"{name}: HTTP {r.status_code} {code or ''} {body}")
            return r if raw else (r.json() if r.content else None)

    async def refresh(self):
        r = await self.c.post("/auth/refresh", json={"refresh_token": self.refresh_token})
        if r.status_code == 200:
            tokens = r.json()
            self.token, self.refresh_token = tokens["access_token"], tokens["refresh_token"]

    async def wait_job(self, job, label):
        """Polls a job with backoff until it finishes; records how long it took."""
        job_id, t0, delay = job["job_id"], time.perf_counter(), 1.0
        status = job["status"]
        while status not in TERMINAL:
            if time.perf_counter() - t0 > self.args.job_timeout:
                self.m.jobs.append(
                    {
                        "user": self.idx,
                        "job": label,
                        "type": job.get("job_type"),
                        "status": "timeout",
                        "sec": round(time.perf_counter() - t0, 1),
                        "error": None,
                    }
                )
                raise FlowError(f"{label}: job timeout after {self.args.job_timeout}s")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5)
            job = await self.call("GET", f"/jobs/{job_id}", "GET /jobs/{id}")
            status = job["status"]
        sec = time.perf_counter() - t0
        error = (job.get("error") or {}).get("code")
        self.m.jobs.append(
            {
                "user": self.idx,
                "job": label,
                "type": job.get("job_type"),
                "status": status,
                "sec": round(sec, 1),
                "error": error,
            }
        )
        if status != "succeeded":
            raise FlowError(f"{label}: job {status} {error or ''}")
        return job

    # -------------------------------------------------- setup
    async def login(self):
        await self.call(
            "POST",
            "/auth/register",
            "POST /auth/register",
            auth=False,
            expect=(201, 409),
            json_body={
                "email": self.email,
                "display_name": f"Stress {self.idx}",
                "password": self.password,
                "password_confirmation": self.password,
                "user_role": "student",
            },
        )
        tokens = await self.call(
            "POST",
            "/auth/login",
            "POST /auth/login",
            auth=False,
            json_body={"email": self.email, "password": self.password},
        )
        self.token, self.refresh_token = tokens["access_token"], tokens["refresh_token"]

    async def browse(self):
        for path in (
            "/users/me",
            "/dashboard",
            "/capabilities",
            "/topics",
            "/personas",
            "/attempts",
        ):
            await self.call("GET", path, f"GET {path}")

    async def create_exercise(self, skill, body):
        """Create + wait. A full per-user generation queue (429/409) is retried after a pause."""
        for attempt in range(6):
            try:
                created = await self.call(
                    "POST",
                    f"/{skill}/exercises",
                    f"POST /{skill}/exercises",
                    json_body=body,
                    idem=True,
                    expect=(202,),
                )
                break
            except FlowError as e:
                if ("429" in str(e) or "409" in str(e)) and attempt < 5:
                    await asyncio.sleep(5 + attempt * 5)
                    continue
                raise
        await self.wait_job(created["job"], f"generate {skill}")
        return await self.call("GET", f"/exercises/{created['exercise_id']}", "GET /exercises/{id}")

    async def start_attempt(self, exercise):
        return await self.call(
            "POST",
            f"/exercises/{exercise['exercise_id']}/attempts",
            "POST /exercises/{id}/attempts",
            json_body={},
            idem=True,
            expect=(201,),
        )

    async def finish_evaluation(self, attempt_id, result):
        if result.get("job"):
            await self.wait_job(result["job"], "evaluate")
        return await self.call(
            "GET", f"/attempts/{attempt_id}/evaluation", "GET /attempts/{id}/evaluation"
        )

    # -------------------------------------------------- flows
    async def flow_writing(self):
        ex = await self.create_exercise(
            "writing",
            {
                "difficulty": random.choice(["beginner", "intermediate"]),
                "topic": {"mode": "random"},
                "target_word_count": 100,
            },
        )
        started = await self.start_attempt(ex)
        aid, rev = started["attempt"]["attempt_id"], started["attempt"]["revision"]
        saved = await self.call(
            "PATCH",
            f"/attempts/{aid}/draft",
            "PATCH /attempts/{id}/draft",
            json_body={"revision": rev, "draft": {"skill": "writing", "response_text": ESSAY}},
        )
        result = await self.call(
            "POST",
            f"/attempts/{aid}/submit",
            "POST /attempts/{id}/submit",
            json_body={"revision": saved["revision"]},
            idem=True,
            expect=(200, 202),
        )
        evaluation = await self.finish_evaluation(aid, result)
        return f"score {evaluation.get('overall_score')}/{evaluation.get('max_score')}"

    async def answer_questions(self, aid, rev, questions, *, one_by_one):
        answers = []
        for q in questions:
            if q["question_type"] == "multiple_choice" and q.get("options"):
                answers.append(
                    {
                        "question_id": q["question_id"],
                        "selected_option_id": random.choice(q["options"])["option_id"],
                        "response_text": None,
                    }
                )
            else:
                answers.append(
                    {
                        "question_id": q["question_id"],
                        "selected_option_id": None,
                        "response_text": "I think it is about the main topic of the text.",
                    }
                )
        if not one_by_one:
            return answers, rev
        for a in answers:
            body = (
                {"revision": rev, "selected_option_id": a["selected_option_id"]}
                if a["selected_option_id"]
                else {"revision": rev, "response_text": a["response_text"]}
            )
            res = await self.call(
                "POST",
                f"/attempts/{aid}/answers/{a['question_id']}/submit",
                "POST /attempts/{id}/answers/{q}/submit",
                json_body=body,
                idem=True,
                expect=(200, 202),
            )
            rev = res.get("attempt_revision", rev)
            if res.get("job"):
                await self.wait_job(res["job"], "grade answer")
            await self.call(
                "GET",
                f"/attempts/{aid}/answers/{a['question_id']}/feedback",
                "GET /attempts/{id}/answers/{q}/feedback",
            )
        return answers, rev

    async def latest_revision(self, aid):
        detail = await self.call("GET", f"/attempts/{aid}", "GET /attempts/{id}")
        return detail["attempt"]["revision"]

    async def flow_reading(self):
        ex = await self.create_exercise(
            "reading",
            {
                "difficulty": "beginner",
                "topic": {"mode": "random"},
                "question_count": 3,
                "question_types": ["multiple_choice", "short_answer"],
            },
        )
        await self.call(
            "GET", f"/exercises/{ex['exercise_id']}/vocabulary", "GET /exercises/{id}/vocabulary"
        )
        started = await self.start_attempt(ex)
        aid, rev = started["attempt"]["attempt_id"], started["attempt"]["revision"]
        _, rev = await self.answer_questions(aid, rev, ex.get("questions") or [], one_by_one=True)
        rev = await self.latest_revision(aid)
        result = await self.call(
            "POST",
            f"/attempts/{aid}/submit",
            "POST /attempts/{id}/submit",
            json_body={"revision": rev},
            idem=True,
            expect=(200, 202),
        )
        evaluation = await self.finish_evaluation(aid, result)
        return f"score {evaluation.get('overall_score')}/{evaluation.get('max_score')}"

    async def flow_listening(self):
        ex = await self.create_exercise(
            "listening",
            {"difficulty": "beginner", "topic": {"mode": "random"}, "question_count": 3},
        )
        media = ((ex.get("content") or {}).get("audio") or {}).get("media_id")
        size = 0
        if media:
            await self.call("GET", f"/media/{media}", "GET /media/{id}")
            r = await self.call(
                "GET", f"/media/{media}/download", "GET /media/{id}/download", raw=True
            )
            size = len(r.content)
        started = await self.start_attempt(ex)
        aid, rev = started["attempt"]["attempt_id"], started["attempt"]["revision"]
        answers, _ = await self.answer_questions(
            aid, rev, ex.get("questions") or [], one_by_one=False
        )
        saved = await self.call(
            "PATCH",
            f"/attempts/{aid}/draft",
            "PATCH /attempts/{id}/draft",
            json_body={
                "revision": rev,
                "draft": {
                    "skill": "listening",
                    "playback_position_ms": 0,
                    "current_question_id": None,
                    "answers": answers,
                },
            },
        )
        result = await self.call(
            "POST",
            f"/attempts/{aid}/submit",
            "POST /attempts/{id}/submit",
            json_body={"revision": saved["revision"]},
            idem=True,
            expect=(200, 202),
        )
        evaluation = await self.finish_evaluation(aid, result)
        await self.call("GET", f"/attempts/{aid}/transcript", "GET /attempts/{id}/transcript")
        return f"audio {size // 1024}KB, score {evaluation.get('overall_score')}/{evaluation.get('max_score')}"

    async def flow_speaking(self):
        personas = await self.call("GET", "/personas", "GET /personas")
        if not personas["items"]:
            raise FlowError("no personas (run the seed)")
        persona = random.choice(personas["items"])["persona_id"]
        ex = await self.create_exercise(
            "speaking",
            {"difficulty": "beginner", "topic": {"mode": "random"}, "persona_id": persona},
        )
        started = await self.start_attempt(ex)
        aid = started["attempt"]["attempt_id"]
        if started.get("job"):
            await self.wait_job(started["job"], "speaking greeting")
        await self.call(
            "GET",
            f"/speaking/attempts/{aid}/conversation",
            "GET /speaking/attempts/{id}/conversation",
        )
        for _ in range(self.args.speaking_turns):
            turn = await self.call(
                "POST",
                f"/speaking/attempts/{aid}/turns",
                "POST /speaking/attempts/{id}/turns",
                idem=True,
                files={"audio": ("turn.wav", self.wav, "audio/wav")},
                data={"client_message_key": str(uuid.uuid4())},
                expect=(202,),
            )
            if turn.get("job"):
                await self.wait_job(turn["job"], "speaking turn")
            page = await self.call(
                "GET", f"/speaking/attempts/{aid}/messages", "GET /speaking/attempts/{id}/messages"
            )
            reply = next(
                (
                    m
                    for m in reversed(page["items"])
                    if m["sender"] == "assistant" and m.get("audio")
                ),
                None,
            )
            if reply and reply["audio"].get("media_id"):
                await self.call(
                    "GET",
                    f"/media/{reply['audio']['media_id']}/download",
                    "GET /media/{id}/download",
                    raw=True,
                )
        result = await self.call(
            "POST",
            f"/speaking/attempts/{aid}/finish",
            "POST /speaking/attempts/{id}/finish",
            json_body=None,
            idem=True,
            expect=(202,),
        )
        evaluation = await self.finish_evaluation(aid, result)
        return f"{self.args.speaking_turns} turns, score {evaluation.get('overall_score')}"

    async def run_flow(self, name):
        t0 = time.perf_counter()
        try:
            note = await getattr(self, f"flow_{name}")()
            ok = True
        except FlowError as e:
            note, ok = str(e), False
            self.m.err(f"user {self.idx} {name}: {e}")
        except Exception as e:  # noqa: BLE001
            note, ok = f"{type(e).__name__}: {e}", False
            self.m.err(f"user {self.idx} {name}: {note}")
        sec = time.perf_counter() - t0
        self.m.flows.append(
            {"user": self.idx, "flow": name, "ok": ok, "sec": round(sec, 1), "note": note[:200]}
        )
        mark = "OK  " if ok else "FAIL"
        print(f"  [{mark}] user {self.idx:>3} {name:<9} {sec:6.1f}s  {note[:90]}", flush=True)

    async def run(self, flows):
        await asyncio.sleep(random.uniform(0, self.args.ramp))
        try:
            await self.login()
            await self.browse()
        except FlowError as e:
            self.m.err(f"user {self.idx} login: {e}")
            for name in flows:
                self.m.flows.append(
                    {"user": self.idx, "flow": name, "ok": False, "sec": 0, "note": "login failed"}
                )
            print(f"  [FAIL] user {self.idx:>3} login     {e}", flush=True)
            return
        order = random.sample(flows, len(flows))
        if self.args.parallel_flows:
            slots = asyncio.Semaphore(3)  # the API allows 3 active generation jobs per user

            async def guarded(name):
                async with slots:
                    await self.run_flow(name)

            await asyncio.gather(*(guarded(n) for n in order))
        else:
            for name in order:
                await self.run_flow(name)


# ---------------------------------------------------------------- audio for Speaking
def tone_wav(seconds=2.5, rate=16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(6000 * math.sin(2 * math.pi * 220 * n / rate)))
                for n in range(int(seconds * rate))
            )
        )
    return buffer.getvalue()


def load_wav(path: str | None) -> tuple[bytes, str]:
    if path:
        data = Path(path).read_bytes()
        if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            sys.exit(f"{path} is not a PCM WAV file")
        return data, path
    return tone_wav(), "generated tone (fine for the fake engine; real STT will find no speech)"


# ---------------------------------------------------------------- report
def report(m: Metrics, wall: float, args, out: Path):
    lines = []
    p = lines.append
    p("=" * 100)
    p(
        f"STRESS TEST  users={args.users}  flows={args.flows}  parallel_flows={args.parallel_flows}  wall={wall:.0f}s"
    )
    p("=" * 100)

    by_flow = defaultdict(list)
    for f in m.flows:
        by_flow[f["flow"]].append(f)
    p("\nFLOWS (end to end per user)")
    p(f"  {'flow':<10}{'ok':>6}{'fail':>6}{'success':>9}{'p50 s':>9}{'p95 s':>9}{'max s':>9}")
    for name, items in sorted(by_flow.items()):
        ok = [f["sec"] for f in items if f["ok"]]
        p(
            f"  {name:<10}{len(ok):>6}{len(items) - len(ok):>6}{100 * len(ok) / len(items):>8.0f}%"
            f"{pct(ok, 50):>9.1f}{pct(ok, 95):>9.1f}{max(ok, default=0):>9.1f}"
        )

    p("\nAI JOBS (queue wait + processing)")
    p(f"  {'job':<20}{'n':>5}{'ok':>5}{'fail':>6}{'p50 s':>9}{'p95 s':>9}{'max s':>9}  errors")
    by_job = defaultdict(list)
    for j in m.jobs:
        by_job[j["job"]].append(j)
    for name, items in sorted(by_job.items()):
        ok = [j["sec"] for j in items if j["status"] == "succeeded"]
        errs = Counter(j["error"] or j["status"] for j in items if j["status"] != "succeeded")
        p(
            f"  {name:<20}{len(items):>5}{len(ok):>5}{len(items) - len(ok):>6}{pct(ok, 50):>9.1f}"
            f"{pct(ok, 95):>9.1f}{max(ok, default=0):>9.1f}  {dict(errs) if errs else ''}"
        )

    p("\nHTTP ENDPOINTS")
    p(
        f"  {'endpoint':<48}{'n':>6}{'err%':>7}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'max ms':>9}  statuses"
    )
    by_ep = defaultdict(list)
    for r in m.requests:
        by_ep[r["endpoint"]].append(r)
    for name, items in sorted(by_ep.items(), key=lambda kv: -len(kv[1])):
        ms = [r["ms"] for r in items]
        bad = [r for r in items if r["status"] == 0 or r["status"] >= 500]
        statuses = Counter(r["status"] for r in items)
        p(
            f"  {name:<48}{len(items):>6}{100 * len(bad) / len(items):>6.1f}%{pct(ms, 50):>9.0f}{pct(ms, 95):>9.0f}"
            f"{pct(ms, 99):>9.0f}{max(ms):>9.0f}  {dict(sorted(statuses.items()))}"
        )
    total = len(m.requests)
    p(
        f"\n  total requests {total}, {total / wall:.1f} req/s, "
        f"5xx/network errors {sum(1 for r in m.requests if r['status'] == 0 or r['status'] >= 500)}, "
        f"4xx {sum(1 for r in m.requests if 400 <= r['status'] < 500)}"
    )
    if m.health:
        hs = [h["ms"] for h in m.health if h["ok"]]
        p(
            f"  /health/ready during test: {len(hs)}/{len(m.health)} ok, p95 {pct(hs, 95):.0f} ms, "
            f"max {max(hs, default=0):.0f} ms"
        )
    if m.errors:
        p("\nERRORS (first 15 distinct)")
        for e in list(dict.fromkeys(m.errors))[:15]:
            p(f"  - {e[:180]}")
    text = "\n".join(lines)
    print("\n" + text)

    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.txt").write_text(text, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps(
            {"flows": m.flows, "jobs": m.jobs, "health": m.health, "errors": m.errors}, indent=2
        ),
        encoding="utf-8",
    )
    with open(out / "requests.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["user", "endpoint", "status", "ms", "code"])
        w.writeheader()
        w.writerows(m.requests)
    print(f"\nSaved: {out / 'summary.txt'}, {out / 'results.json'}, {out / 'requests.csv'}")


async def watch_health(client, metrics, stop):
    while not stop.is_set():
        t0 = time.perf_counter()
        try:
            r = await client.get("/health/ready")
            metrics.health.append(
                {
                    "t": time.time(),
                    "ok": r.status_code == 200,
                    "ms": (time.perf_counter() - t0) * 1000,
                }
            )
        except httpx.HTTPError:
            metrics.health.append(
                {"t": time.time(), "ok": False, "ms": (time.perf_counter() - t0) * 1000}
            )
        try:
            await asyncio.wait_for(stop.wait(), 2)
        except TimeoutError:
            pass


async def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", default="http://localhost:8000/api/v1")
    ap.add_argument("--users", type=int, default=30)
    ap.add_argument("--flows", default="writing,reading,listening,speaking")
    ap.add_argument(
        "--parallel-flows", action="store_true", help="each user runs up to 3 flows at once"
    )
    ap.add_argument(
        "--ramp", type=float, default=5, help="spread user start over this many seconds"
    )
    ap.add_argument("--speaking-turns", type=int, default=2)
    ap.add_argument("--job-timeout", type=float, default=900, help="seconds to wait for one AI job")
    ap.add_argument("--wav", help="PCM WAV with real speech for Speaking turns")
    ap.add_argument("--out", default="stress_results")
    args = ap.parse_args()
    flows = [f.strip() for f in args.flows.split(",") if f.strip()]
    unknown = set(flows) - {"writing", "reading", "listening", "speaking"}
    if unknown:
        sys.exit(f"unknown flows: {unknown}")
    wav, wav_note = load_wav(args.wav)

    limits = httpx.Limits(max_connections=args.users * 4, max_keepalive_connections=args.users * 2)
    async with httpx.AsyncClient(
        base_url=args.base, timeout=httpx.Timeout(120, connect=10), limits=limits
    ) as client:
        try:
            ready = await client.get("/health/ready")
            if ready.status_code != 200:
                sys.exit(f"API not ready: {ready.status_code} {ready.text}")
        except httpx.HTTPError as e:
            sys.exit(f"Cannot reach {args.base}: {e}")
        run_id = uuid.uuid4().hex[:8]
        print(f"Run {run_id}: {args.users} users x {flows} against {args.base}")
        print(f"Speaking audio: {wav_note}\n")
        metrics = Metrics()
        stop = asyncio.Event()
        watcher = asyncio.create_task(watch_health(client, metrics, stop))
        t0 = time.perf_counter()
        users = [User(i + 1, args, client, metrics, run_id, wav) for i in range(args.users)]
        await asyncio.gather(*(u.run(flows) for u in users))
        wall = time.perf_counter() - t0
        stop.set()
        await watcher
    if any(r["status"] == 429 and r["endpoint"].startswith("POST /auth") for r in metrics.requests):
        print(
            "\n!! Login/register got 429: set AUTH_RATE_LIMIT_ENABLED=false in .env and restart the API."
        )
    report(metrics, wall, args, Path(args.out))
    failed = sum(1 for f in metrics.flows if not f["ok"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
