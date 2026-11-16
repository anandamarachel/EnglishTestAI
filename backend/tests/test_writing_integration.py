"""Writing end to end with the real worker and the fake AI engine (_test database)."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_auth_integration import bearer, make_settings, new_account
from test_database_integration import alembic

from app.ai.contracts import CorrectionResult
from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.db.session import Database
from app.main import create_app
from app.modules.catalog.seed import seed
from app.worker.runner import Worker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]

FAST = {"job_retry_base_seconds": 0, "job_max_attempts": 3}
ESSAY = "Yesterday i go to school with my friend and we was late. 🌍 " + "We learn a lot. " * 200


@pytest.fixture(scope="module")
def engine():
    settings = make_settings()
    alembic("upgrade", "head")
    asyncio.run(seed(settings))
    db = create_engine(settings.database_url, hide_parameters=True)
    yield db
    db.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(make_settings(**FAST))) as test_client:
        yield test_client


def drain(ai=None, rounds: int = 10, **overrides) -> int:
    """Run the worker until no job is ready. Returns how many executions ran."""

    async def go() -> int:
        settings = make_settings(**FAST, **overrides)
        database = Database(settings)
        worker = Worker(settings, database, ai or FakeAIEngine())
        total = 0
        try:
            for _ in range(rounds):
                ran = await worker.run_once()
                total += ran
                if ran == 0:
                    break
        finally:
            await database.close()
        return total

    return asyncio.run(go())


def executions(engine, job_id) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT attempt_count FROM ai_jobs WHERE job_id = :id"), {"id": job_id}
        ).scalar()


def post(client, tokens, path, json=None, key=None):
    headers = {**bearer(tokens), "Idempotency-Key": key or str(uuid4())}
    return client.post(f"/api/v1{path}", json=json, headers=headers)


def get(client, tokens, path):
    return client.get(f"/api/v1{path}", headers=bearer(tokens))


def create_exercise(client, tokens, **body):
    body = {"difficulty": "intermediate", "topic": {"mode": "custom", "text": "My school"}, **body}
    return post(client, tokens, "/writing/exercises", body)


def ready_exercise(client, tokens) -> str:
    exercise_id = create_exercise(client, tokens).json()["exercise_id"]
    drain()
    assert get(client, tokens, f"/exercises/{exercise_id}").json()["generation_status"] == "ready"
    return exercise_id


def start(client, tokens, exercise_id, **body) -> dict:
    response = post(client, tokens, f"/exercises/{exercise_id}/attempts", body)
    assert response.status_code == 201, response.text
    return response.json()["attempt"]


def save(client, tokens, attempt_id, revision, response_text):
    return client.patch(
        f"/api/v1/attempts/{attempt_id}/draft",
        headers=bearer(tokens),
        json={"revision": revision, "draft": {"skill": "writing", "response_text": response_text}},
    )


def submitted_attempt(client, tokens, essay=ESSAY) -> tuple[str, dict]:
    attempt = start(client, tokens, ready_exercise(client, tokens))
    assert save(client, tokens, attempt["attempt_id"], 1, essay).status_code == 200
    response = post(client, tokens, f"/attempts/{attempt['attempt_id']}/submit", {"revision": 2})
    assert response.status_code == 202, response.text
    return attempt["attempt_id"], response.json()["job"]


# --- Happy path ---------------------------------------------------------------------


def test_complete_writing_flow(client) -> None:
    _, tokens = new_account(client)
    created = create_exercise(client, tokens, target_word_count=150)
    assert created.status_code == 202
    exercise_id, job = created.json()["exercise_id"], created.json()["job"]
    assert job["status"] == "queued" and job["target"] == {"type": "exercise", "id": exercise_id}
    assert job["can_cancel"] is True and job["result_refs"] == {}

    pending = get(client, tokens, f"/exercises/{exercise_id}").json()
    assert pending["generation_status"] == "pending"
    assert pending["content"] is None and pending["title"] is None
    assert pending["topic"] == {"mode": "custom", "topic_id": None, "name": "My school"}

    drain()
    done = get(client, tokens, f"/jobs/{job['job_id']}").json()
    assert done["status"] == "succeeded"
    assert done["result_refs"] == {"exercise_id": exercise_id}
    assert done["can_cancel"] is False and done["error"] is None
    exercise = get(client, tokens, f"/exercises/{exercise_id}").json()
    assert exercise["generation_status"] == "ready"
    assert exercise["title"] and "150 words" in exercise["instructions"]
    assert exercise["content"] == {
        "target_word_count": 150,
        "rubric_version": "writing-ielts-practice-v1",
    }

    attempt = start(client, tokens, exercise_id)
    assert attempt["attempt_number"] == 1 and attempt["revision"] == 1
    assert attempt["status"] == "in_progress" and attempt["current_stage"] == "writing"
    attempt_id = attempt["attempt_id"]

    # Empty drafts save; long drafts (far beyond 500 characters) save untouched.
    assert save(client, tokens, attempt_id, 1, "").json()["revision"] == 2
    saved = save(client, tokens, attempt_id, 2, ESSAY)
    assert saved.status_code == 200 and saved.json()["revision"] == 3
    assert len(ESSAY) > 3000
    stale = save(client, tokens, attempt_id, 2, "older text")
    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT" and stale.json()["current_revision"] == 3
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["draft"] == {"skill": "writing", "response_text": ESSAY}
    assert detail["evaluation"] is None and detail["active_jobs"] == []

    dashboard = get(client, tokens, "/dashboard").json()
    assert dashboard["resume_attempt"]["attempt_id"] == attempt_id

    submitted = post(client, tokens, f"/attempts/{attempt_id}/submit", {"revision": 3})
    assert submitted.status_code == 202
    body = submitted.json()
    assert body["attempt"]["status"] == "submitted" and body["attempt"]["revision"] == 4
    assert body["job"]["job_type"] == "evaluate_attempt"
    assert save(client, tokens, attempt_id, 4, "too late").status_code == 409
    pending_eval = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    assert pending_eval["status"] == "pending" and pending_eval["overall_score"] is None
    assert (
        get(client, tokens, "/dashboard").json()["pending_attempts"][0]["attempt_id"] == attempt_id
    )

    drain()
    evaluation = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    assert evaluation["status"] == "completed"
    assert [c["criterion_code"] for c in evaluation["criteria"]] == [
        "task_response",
        "coherence_cohesion",
        "lexical_resource",
        "grammatical_range_accuracy",
    ]
    scores = [c["score"] for c in evaluation["criteria"]]
    assert all(
        c["max_score"] == 9 and c["assessment_status"] == "assessed" for c in evaluation["criteria"]
    )
    assert evaluation["max_score"] == 9
    mean = sum(scores) / 4
    assert evaluation["overall_score"] == int(mean * 2 + 0.5) / 2
    corrections = evaluation["feedback_payload"]["corrections"]
    assert [(c["original"], c["replacement"]) for c in corrections[:3]] == [
        ("i", "I"),
        ("go", "went"),
        ("was", "were"),
    ]
    for correction in corrections:
        assert ESSAY[correction["start"] : correction["end"]] == correction["original"]
    assert evaluation["corrected_text"].startswith("Yesterday I went to school")
    limitations = evaluation["feedback_payload"]["limitations"]
    assert any("not an official IELTS score" in item for item in limitations)
    assert any("illustrative" in item for item in limitations)

    final = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert (
        final["attempt"]["status"] == "completed" and final["attempt"]["current_stage"] == "results"
    )
    assert final["attempt"]["score"] == {"value": evaluation["overall_score"], "max": 9.0}
    assert final["draft"]["response_text"] == ESSAY  # original text is preserved
    history = get(client, tokens, "/attempts?skill=writing").json()["items"]
    assert history[0]["attempt_id"] == attempt_id and history[0]["score"] is not None


def test_unicode_spans_use_code_points(client) -> None:
    _, tokens = new_account(client)
    essay = "🌍🌏 Yesterday i go home."
    attempt_id, _ = submitted_attempt(client, tokens, essay)
    drain()
    corrections = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()[
        "feedback_payload"
    ]["corrections"]
    assert [(c["start"], c["end"]) for c in corrections] == [(13, 14), (15, 17)]
    for correction in corrections:
        assert essay[correction["start"] : correction["end"]] == correction["original"]


def test_random_topic_resolves_to_catalog_topic(client) -> None:
    _, tokens = new_account(client)
    created = post(client, tokens, "/writing/exercises", {"difficulty": "beginner"})
    exercise_id = created.json()["exercise_id"]
    before = get(client, tokens, f"/exercises/{exercise_id}").json()
    assert before["topic"] == {"mode": "random", "topic_id": None, "name": None}
    assert before["content_cefr_level"] == "A2"
    drain()
    after = get(client, tokens, f"/exercises/{exercise_id}").json()
    assert after["topic"]["mode"] == "random"
    assert after["topic"]["topic_id"] and after["topic"]["name"]


def test_catalog_topic_must_be_active(client, engine) -> None:
    _, tokens = new_account(client)
    topics = get(client, tokens, "/topics").json()["items"]
    ok = create_exercise(
        client, tokens, topic={"mode": "catalog", "topic_id": topics[0]["topic_id"]}
    )
    assert ok.status_code == 202
    missing = create_exercise(client, tokens, topic={"mode": "catalog", "topic_id": str(uuid4())})
    assert missing.status_code == 422
    assert missing.json()["details"][0]["field"] == "topic.topic_id"
    for bad in ({"mode": "custom", "text": "   "}, {"mode": "random", "text": "x"}, {"mode": "x"}):
        assert create_exercise(client, tokens, topic=bad).status_code == 422


def test_edit_copies_original_text_into_new_attempt(client) -> None:
    _, tokens = new_account(client)
    attempt_id, _ = submitted_attempt(client, tokens, "Yesterday i go home.")
    drain()
    exercise_id = get(client, tokens, f"/attempts/{attempt_id}").json()["exercise"]["exercise_id"]
    copy = start(client, tokens, exercise_id, source_attempt_id=attempt_id)
    assert copy["attempt_number"] == 2 and copy["source_attempt_id"] == attempt_id
    draft = get(client, tokens, f"/attempts/{copy['attempt_id']}").json()["draft"]
    assert draft["response_text"] == "Yesterday i go home."  # original, not corrected
    fresh = start(client, tokens, exercise_id)
    assert fresh["attempt_number"] == 3
    assert (
        get(client, tokens, f"/attempts/{fresh['attempt_id']}").json()["draft"]["response_text"]
        == ""
    )
    # Unsubmitted attempts cannot be used as a source.
    bad = post(
        client,
        tokens,
        f"/exercises/{exercise_id}/attempts",
        {"source_attempt_id": fresh["attempt_id"]},
    )
    assert bad.status_code == 422


# --- Validation and capacity ----------------------------------------------------------


def test_blank_submission_and_wrong_revision(client) -> None:
    _, tokens = new_account(client)
    attempt = start(client, tokens, ready_exercise(client, tokens))
    attempt_id = attempt["attempt_id"]
    save(client, tokens, attempt_id, 1, " \n\t ")
    blank = post(client, tokens, f"/attempts/{attempt_id}/submit", {"revision": 2})
    assert blank.status_code == 422
    assert blank.json()["details"][0]["field"] == "response_text"
    stale = post(client, tokens, f"/attempts/{attempt_id}/submit", {"revision": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "REVISION_CONFLICT"


def test_submission_over_model_capacity_keeps_draft(engine) -> None:
    with TestClient(create_app(make_settings(writing_max_submission_chars=1_000))) as client:
        _, tokens = new_account(client)
        attempt_id = start(client, tokens, ready_exercise(client, tokens))["attempt_id"]
        assert save(client, tokens, attempt_id, 1, ESSAY).status_code == 200
        response = post(client, tokens, f"/attempts/{attempt_id}/submit", {"revision": 2})
        assert response.status_code == 413 and response.json()["code"] == "CAPACITY_EXCEEDED"
        detail = get(client, tokens, f"/attempts/{attempt_id}").json()
        assert detail["attempt"]["status"] == "in_progress"
        assert detail["draft"]["response_text"] == ESSAY


def test_missing_idempotency_key_and_draft_skill(client) -> None:
    _, tokens = new_account(client)
    response = client.post(
        "/api/v1/writing/exercises", headers=bearer(tokens), json={"difficulty": "beginner"}
    )
    assert response.status_code == 422
    assert response.json()["details"][0]["field"] == "Idempotency-Key"
    attempt_id = start(client, tokens, ready_exercise(client, tokens))["attempt_id"]
    wrong = client.patch(
        f"/api/v1/attempts/{attempt_id}/draft",
        headers=bearer(tokens),
        json={"revision": 1, "draft": {"skill": "reading", "response_text": "x"}},
    )
    assert wrong.status_code == 422


def test_generation_capacity_per_user(engine) -> None:
    with TestClient(create_app(make_settings(max_active_generation_jobs_per_user=2))) as client:
        _, tokens = new_account(client)
        assert create_exercise(client, tokens).status_code == 202
        assert create_exercise(client, tokens).status_code == 202
        third = create_exercise(client, tokens)
        assert third.status_code == 429 and third.json()["code"] == "RATE_LIMITED"


# --- Idempotency ----------------------------------------------------------------------


def test_idempotent_replay_and_conflict(client, engine) -> None:
    _, tokens = new_account(client)
    key = str(uuid4())
    body = {"difficulty": "advanced", "topic": {"mode": "custom", "text": "Robots"}}
    first = post(client, tokens, "/writing/exercises", body, key=key)
    again = post(client, tokens, "/writing/exercises", body, key=key)
    assert first.status_code == again.status_code == 202
    assert first.json()["exercise_id"] == again.json()["exercise_id"]
    changed = post(
        client, tokens, "/writing/exercises", {**body, "difficulty": "beginner"}, key=key
    )
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    other_path = post(client, tokens, f"/exercises/{uuid4()}/attempts", {}, key=key)
    assert other_path.status_code == 409
    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM exercises WHERE custom_topic = 'Robots' AND created_by = "
                "(SELECT user_id FROM users u JOIN api_idempotency_keys k USING (user_id) "
                "WHERE k.idempotency_key = :k)"
            ),
            {"k": key},
        ).scalar()
    assert count == 1


def test_concurrent_requests_with_one_key_create_one_exercise(client) -> None:
    _, tokens = new_account(client)
    headers = {**bearer(tokens), "Idempotency-Key": str(uuid4())}
    body = {"difficulty": "beginner", "topic": {"mode": "custom", "text": "Concurrency"}}

    async def go():
        application = create_app(make_settings(**FAST))
        async with application.router.lifespan_context(application):
            transport = httpx.ASGITransport(app=application)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as h:
                return await asyncio.gather(
                    *(
                        h.post("/api/v1/writing/exercises", json=body, headers=headers)
                        for _ in range(5)
                    )
                )

    responses = asyncio.run(go())
    assert {r.status_code for r in responses} == {202}
    assert len({r.json()["exercise_id"] for r in responses}) == 1


def test_concurrent_submits_create_one_evaluation_job(client) -> None:
    _, tokens = new_account(client)
    attempt_id = start(client, tokens, ready_exercise(client, tokens))["attempt_id"]
    save(client, tokens, attempt_id, 1, "Some text.")

    async def go():
        application = create_app(make_settings(**FAST))
        async with application.router.lifespan_context(application):
            transport = httpx.ASGITransport(app=application)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as h:
                return await asyncio.gather(
                    *(
                        h.post(
                            f"/api/v1/attempts/{attempt_id}/submit",
                            json={"revision": 2},
                            headers={**bearer(tokens), "Idempotency-Key": str(uuid4())},
                        )
                        for _ in range(5)
                    )
                )

    codes = sorted(r.status_code for r in asyncio.run(go()))
    assert codes == [202, 409, 409, 409, 409]


# --- Ownership ------------------------------------------------------------------------


def test_other_users_cannot_see_or_change_anything(client) -> None:
    _, owner = new_account(client)
    _, intruder = new_account(client)
    attempt_id, job = submitted_attempt(client, owner, "Yesterday i go home.")
    exercise_id = get(client, owner, f"/attempts/{attempt_id}").json()["exercise"]["exercise_id"]
    for path in (
        f"/exercises/{exercise_id}",
        f"/attempts/{attempt_id}",
        f"/attempts/{attempt_id}/evaluation",
        f"/jobs/{job['job_id']}",
    ):
        assert get(client, intruder, path).status_code == 404, path
    assert save(client, intruder, attempt_id, 1, "x").status_code == 404
    for path in (
        f"/attempts/{attempt_id}/submit",
        f"/attempts/{attempt_id}/cancel",
        f"/jobs/{job['job_id']}/cancel",
        f"/jobs/{job['job_id']}/retry",
        f"/exercises/{exercise_id}/attempts",
    ):
        body = {"revision": 2} if path.endswith("submit") else {}
        assert post(client, intruder, path, body).status_code == 404, path
    assert get(client, intruder, "/attempts").json()["items"] == []


# --- Failures, retries, cancellation and stale workers -----------------------------------


def test_generation_failure_retry_and_recovery(client, engine) -> None:
    _, tokens = new_account(client)
    created = create_exercise(client, tokens).json()
    job_id, exercise_id = created["job"]["job_id"], created["exercise_id"]
    broken = FakeAIEngine(fail_with=AIError("AI_UNAVAILABLE", retryable=True), fail_times=99)
    drain(broken)
    assert executions(engine, job_id) == 3  # bounded: max_attempts executions, then stop
    job = get(client, tokens, f"/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert job["error"] == {"code": "AI_UNAVAILABLE", "retryable": True}
    assert job["can_retry"] is True
    assert get(client, tokens, f"/exercises/{exercise_id}").json()["generation_status"] == "failed"

    retried = post(client, tokens, f"/jobs/{job_id}/retry")
    assert retried.status_code == 202 and retried.json()["status"] == "queued"
    assert get(client, tokens, f"/exercises/{exercise_id}").json()["generation_status"] == "pending"
    drain()
    assert get(client, tokens, f"/exercises/{exercise_id}").json()["generation_status"] == "ready"
    assert post(client, tokens, f"/jobs/{job_id}/retry").status_code == 409
    assert post(client, tokens, f"/jobs/{job_id}/cancel").json()["code"] == "ALREADY_COMPLETED"


class BadSpanEngine(FakeAIEngine):
    async def evaluate_writing(self, request):
        result = await super().evaluate_writing(request)
        wrong = CorrectionResult(
            start=0,
            end=3,
            original="xyz",
            replacement="abc",
            category="grammar",
            title="Bad",
            explanation="Bad span.",
            example="",
        )
        return result.model_copy(update={"corrections": [wrong]})


def test_invalid_model_output_is_rejected_and_submission_kept(client) -> None:
    _, tokens = new_account(client)
    attempt_id, job = submitted_attempt(client, tokens, "Yesterday i go home.")
    drain(BadSpanEngine())
    evaluation = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    assert evaluation["status"] == "failed" and evaluation["overall_score"] is None
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["status"] == "failed"
    assert detail["draft"]["response_text"] == "Yesterday i go home."
    failed = get(client, tokens, f"/jobs/{job['job_id']}").json()
    assert failed["error"]["code"] == "AI_OUTPUT_INVALID"

    assert post(client, tokens, f"/jobs/{job['job_id']}/retry").status_code == 202
    assert get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["status"] == "submitted"
    drain()
    assert get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()["status"] == "completed"


def test_cancel_queued_generation(client) -> None:
    _, tokens = new_account(client)
    created = create_exercise(client, tokens).json()
    cancelled = post(client, tokens, f"/jobs/{created['job']['job_id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "cancelled"
    drain()
    assert post(client, tokens, f"/jobs/{created['job']['job_id']}/cancel").status_code == 409
    assert (
        post(client, tokens, f"/exercises/{created['exercise_id']}/attempts", {}).status_code == 409
    )


def _claim_one(**overrides):
    async def go():
        settings = make_settings(**FAST, **overrides)
        database = Database(settings)
        worker = Worker(settings, database, FakeAIEngine())
        [job_id] = await worker._candidates(1)  # noqa: SLF001
        claim = await worker._claim(job_id)  # noqa: SLF001
        await database.close()
        return claim

    return asyncio.run(go())


def _process(claim) -> None:
    async def go():
        settings = make_settings(**FAST)
        database = Database(settings)
        try:
            await Worker(settings, database, FakeAIEngine()).process(claim)
        finally:
            await database.close()

    asyncio.run(go())


def test_cancelling_a_running_evaluation_discards_late_result(client) -> None:
    _, tokens = new_account(client)
    attempt_id, job = submitted_attempt(client, tokens, "Yesterday i go home.")
    claim = _claim_one()  # worker now "running" the evaluation
    assert (
        get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["status"] == "evaluating"
    )
    cancelled = post(client, tokens, f"/jobs/{job['job_id']}/cancel")
    assert cancelled.status_code == 202 and cancelled.json()["status"] == "cancel_requested"

    _process(claim)  # the late result must not be published
    job_now = get(client, tokens, f"/jobs/{job['job_id']}").json()
    assert job_now["status"] == "cancelled"
    evaluation = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    assert evaluation["status"] == "cancelled" and evaluation["criteria"] == []
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["status"] == "failed"  # retryable, submission kept
    assert job_now["can_retry"] is True
    assert post(client, tokens, f"/jobs/{job['job_id']}/retry").status_code == 202
    drain()
    assert get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()["status"] == "completed"


def test_expired_lease_is_recovered_and_old_execution_discarded(client, engine) -> None:
    _, tokens = new_account(client)
    created = create_exercise(client, tokens).json()
    stale = _claim_one()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ai_jobs SET lease_expires_at = now() - interval '1 second' "
                "WHERE job_id = :id"
            ),
            {"id": created["job"]["job_id"]},
        )
    drain()  # recovered with a new execution version and completed
    _process(stale)  # the vanished worker comes back: its result is ignored
    job = get(client, tokens, f"/jobs/{created['job']['job_id']}").json()
    assert job["status"] == "succeeded"
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT execution_version FROM ai_jobs WHERE job_id = :id"),
            {"id": created["job"]["job_id"]},
        ).scalar()
    assert version == 2


def test_cancel_attempt_freezes_everything(client) -> None:
    _, tokens = new_account(client)
    attempt_id, job = submitted_attempt(client, tokens, "Yesterday i go home.")
    cancelled = post(client, tokens, f"/attempts/{attempt_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["attempt"]["status"] == "cancelled"
    assert get(client, tokens, f"/jobs/{job['job_id']}").json()["status"] == "cancelled"
    assert get(client, tokens, f"/jobs/{job['job_id']}").json()["can_retry"] is False
    assert post(client, tokens, f"/jobs/{job['job_id']}/retry").status_code == 409
    assert get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()["status"] == "cancelled"
    drain()
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["draft"]["response_text"] == "Yesterday i go home."  # history kept
    # Completed attempts cannot be cancelled.
    done_id, _ = submitted_attempt(client, tokens, "Fine text.")
    drain()
    assert post(client, tokens, f"/attempts/{done_id}/cancel").status_code == 409


def test_cancel_in_progress_attempt(client) -> None:
    _, tokens = new_account(client)
    attempt_id = start(client, tokens, ready_exercise(client, tokens))["attempt_id"]
    save(client, tokens, attempt_id, 1, "draft")
    assert post(client, tokens, f"/attempts/{attempt_id}/cancel").status_code == 200
    assert save(client, tokens, attempt_id, 2, "more").status_code == 409
    assert get(client, tokens, "/dashboard").json()["resume_attempt"] is None


def test_superseded_execution_cannot_publish_while_newer_one_runs(client, engine) -> None:
    """Only the service's version check stops this; the database would allow it."""
    _, tokens = new_account(client)
    created = create_exercise(client, tokens).json()
    job_id = created["job"]["job_id"]
    with engine.begin() as conn:  # make our job the oldest so the claims pick it
        conn.execute(
            text(
                "UPDATE ai_jobs SET status = 'cancelled', finished_at = now() "
                "WHERE status = 'queued' AND job_id <> :id"
            ),
            {"id": job_id},
        )
    old = _claim_one()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ai_jobs SET lease_expires_at = now() - interval '1 second' "
                "WHERE job_id = :id"
            ),
            {"id": job_id},
        )
    new = _claim_one()
    assert (str(old.job_id), str(new.job_id)) == (job_id, job_id)
    assert new.version == old.version + 1

    _process(old)
    assert get(client, tokens, f"/jobs/{job_id}").json()["status"] == "running"
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "generating" and exercise["title"] is None

    _process(new)
    assert get(client, tokens, f"/jobs/{job_id}").json()["status"] == "succeeded"
