"""Listening and private media end to end: real worker, fake AI/TTS, temp media dir."""

import asyncio
import os
import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_auth_integration import bearer, make_settings, new_account
from test_database_integration import alembic
from test_reading_integration import KEYS, correct_option, revision, walk, wrong_option
from test_writing_integration import FAST, drain, get, post, start

from app.ai.contracts import SpeechAudio
from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.db.session import Database
from app.main import create_app
from app.modules.catalog.seed import seed
from app.modules.media.storage import MediaStore
from app.worker.runner import Worker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]

ANSWERS = {1: "A blue kite", 2: "Near the old market", 3: "A chicken sandwich", 4: "Her teacher"}


@pytest.fixture(scope="module", autouse=True)
def media_dir(tmp_path_factory):
    """API and worker share one private directory, as in Docker."""
    path = tmp_path_factory.mktemp("media")
    previous = os.environ.get("MEDIA_STORAGE_DIR")
    os.environ["MEDIA_STORAGE_DIR"] = str(path)
    yield path
    if previous is None:
        os.environ.pop("MEDIA_STORAGE_DIR", None)
    else:
        os.environ["MEDIA_STORAGE_DIR"] = previous


@pytest.fixture(scope="module")
def engine(media_dir):
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


def files(media_dir) -> set[str]:
    return {p.relative_to(media_dir).as_posix() for p in media_dir.rglob("*") if p.is_file()}


def create(client, tokens, **body):
    body = {"difficulty": "intermediate", "topic": {"mode": "custom", "text": "Sekolah"}, **body}
    return post(client, tokens, "/listening/exercises", body)


def ready(client, tokens, **body) -> dict:
    response = create(client, tokens, **body)
    assert response.status_code == 202, response.text
    drain()
    exercise = get(client, tokens, f"/exercises/{response.json()['exercise_id']}").json()
    assert exercise["generation_status"] == "ready", exercise
    return exercise


MIXED = {"question_types": ["multiple_choice", "short_answer"]}  # 3 questions: MC, SA, MC


def save(client, tokens, attempt_id, answers=(), current=None, position=0, rev=None):
    return client.patch(
        f"/api/v1/attempts/{attempt_id}/draft",
        headers=bearer(tokens),
        json={
            "revision": rev or revision(client, tokens, attempt_id),
            "draft": {
                "skill": "listening",
                "playback_position_ms": position,
                "current_question_id": current,
                "answers": list(answers),
            },
        },
    )


def full_answers(exercise, right=True) -> list[dict]:
    result = []
    for q in exercise["questions"]:
        if q["question_type"] == "multiple_choice":
            option = correct_option(q) if right else wrong_option(q)
            result.append(
                {
                    "question_id": q["question_id"],
                    "selected_option_id": option,
                    "response_text": None,
                }
            )
        else:
            reply = ANSWERS[q["position"]] if right else "I do not know"
            result.append(
                {
                    "question_id": q["question_id"],
                    "selected_option_id": None,
                    "response_text": reply,
                }
            )
    return result


def submit(client, tokens, attempt_id, key=None):
    body = {"revision": revision(client, tokens, attempt_id)}
    return post(client, tokens, f"/attempts/{attempt_id}/submit", body, key=key)


def submitted(client, tokens, **body) -> tuple[dict, str, dict]:
    exercise = ready(client, tokens, **body)
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    assert save(client, tokens, attempt_id, full_answers(exercise)).status_code == 200
    response = submit(client, tokens, attempt_id)
    assert response.status_code in (200, 202), response.text
    return exercise, attempt_id, response.json()


def run_worker(action, ai=None):
    async def go():
        settings = make_settings(**FAST)
        database = Database(settings)
        try:
            return await action(Worker(settings, database, ai or FakeAIEngine()))
        finally:
            await database.close()

    return asyncio.run(go())


def job_row(engine, job_id) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT status, attempt_count, next_retry_at FROM ai_jobs WHERE job_id=:id"),
                {"id": job_id},
            )
            .mappings()
            .one()
        )


def media_id_of(exercise) -> str:
    return exercise["content"]["audio"]["media_id"]


# --- Generation and private audio -----------------------------------------------------------


def test_generation_stores_private_audio_and_hides_transcript(client, media_dir) -> None:
    _, tokens = new_account(client)
    before = files(media_dir)
    exercise = ready(client, tokens)
    assert exercise["skill"] == "listening"
    content = exercise["content"]
    assert content["question_count"] == 3
    assert content["feedback_mode"] == content["transcript_policy"] == "after_submission"
    audio = content["audio"]
    assert audio["purpose"] == "listening_audio" and audio["mime_type"] == "audio/wav"
    assert audio["status"] == "ready" and audio["available"] is True
    assert 10_000 < audio["duration_ms"] < 600_000
    assert [q["position"] for q in exercise["questions"]] == [1, 2, 3]
    assert not (set(walk(exercise)) & (KEYS | {"transcript"}))  # no keys, no script
    # The script itself stays hidden (question texts may mention names, not the lines).
    assert "brought a blue kite" not in str(exercise) and "Nadia:" not in str(exercise)
    added = files(media_dir) - before
    assert len(added) == 1 and next(iter(added)).startswith("listening_audio/")

    media = get(client, tokens, f"/media/{audio['media_id']}").json()
    assert media == audio

    whole = get(client, tokens, f"/media/{audio['media_id']}/download")
    assert whole.status_code == 200
    assert whole.headers["content-type"] == "audio/wav"
    assert whole.headers["accept-ranges"] == "bytes"
    assert whole.headers["cache-control"] == "private, no-store"
    assert len(whole.content) == audio["size_bytes"] and whole.content[:4] == b"RIFF"

    def ranged(value):
        return client.get(
            f"/api/v1/media/{audio['media_id']}/download",
            headers={**bearer(tokens), "Range": value},
        )

    part = ranged("bytes=0-99")
    assert part.status_code == 206 and part.content == whole.content[:100]
    assert part.headers["content-range"] == f"bytes 0-99/{audio['size_bytes']}"
    assert part.headers["content-length"] == "100"
    tail = ranged("bytes=-10")
    assert tail.status_code == 206 and tail.content == whole.content[-10:]
    for bad in ("bytes=0-1,5-9", f"bytes={audio['size_bytes']}-", "bytes=9-1"):
        response = ranged(bad)
        assert response.status_code == 416, bad
        assert response.json()["code"] == "RANGE_NOT_SATISFIABLE"
        assert response.headers["content-range"] == f"bytes */{audio['size_bytes']}"


def test_requests_are_honoured_or_rejected(client) -> None:
    _, tokens = new_account(client)
    assert create(client, tokens, question_count=11).status_code == 413
    response = create(client, tokens, question_types=["short_answer", "short_answer"])
    assert response.status_code == 422
    exercise = ready(client, tokens, question_count=4, **MIXED)
    types = [q["question_type"] for q in exercise["questions"]]
    assert types == ["multiple_choice", "short_answer", "multiple_choice", "short_answer"]


def test_invalid_tts_output_fails_without_leaving_files(client, engine, media_dir) -> None:
    class BrokenTTS(FakeAIEngine):
        async def synthesize_speech(self, request):
            return SpeechAudio(audio=b"RIFF\x00\x00\x00\x00WAVEnot really audio" + b"\x00" * 64)

    _, tokens = new_account(client)
    before = files(media_dir)
    created = create(client, tokens).json()
    drain(BrokenTTS())
    job = get(client, tokens, f"/jobs/{created['job']['job_id']}").json()
    assert job["status"] == "failed" and job["error"]["code"] == "TTS_OUTPUT_INVALID"
    assert job["can_retry"] is True
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "failed" and exercise["content"] is None
    assert files(media_dir) == before
    # Retry with a working engine produces the exercise and exactly one file.
    assert post(client, tokens, f"/jobs/{job['job_id']}/retry").status_code == 202
    drain()
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "ready"
    assert len(files(media_dir) - before) == 1


def test_cancelled_generation_discards_its_audio(client, engine, media_dir) -> None:
    """The file is written before publish; a cancel in between must not leave it behind."""
    _, tokens = new_account(client)
    created = create(client, tokens).json()
    job_id = created["job"]["job_id"]

    class CancelDuringTTS(FakeAIEngine):
        async def synthesize_speech(self, request):
            response = post(client, tokens, f"/jobs/{job_id}/cancel")
            assert response.status_code == 202  # running: cancel requested
            return await super().synthesize_speech(request)

    before = files(media_dir)
    drain(CancelDuringTTS())
    assert files(media_dir) == before
    assert get(client, tokens, f"/jobs/{job_id}").json()["status"] == "cancelled"
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "cancelled"
    with engine.connect() as connection:
        user_media = connection.execute(
            text(
                "SELECT count(*) FROM media_assets m JOIN exercises e "
                "ON e.created_by=m.owner_user_id WHERE e.exercise_id=:id"
            ),
            {"id": created["exercise_id"]},
        ).scalar_one()
    assert user_media == 0


def test_orphan_sweep_keeps_referenced_audio(client, media_dir) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens)
    store = MediaStore(media_dir)
    orphan = store.new_key("listening_audio", "wav")
    store.write(orphan, b"left behind by a crashed worker")
    temp = media_dir / "listening_audio" / ".tmp-crashed"
    temp.write_bytes(b"partial")
    fresh = store.new_key("listening_audio", "wav")
    store.write(fresh, b"may still be publishing")
    past = time.time() - 7_200
    for path in [store.path(orphan), temp, *media_dir.rglob("*.wav")]:
        if path != store.path(fresh):
            os.utime(path, (past, past))

    removed = run_worker(lambda worker: worker.sweep_media())
    assert removed == 2
    remaining = files(media_dir)
    assert orphan not in remaining and ".tmp-crashed" not in str(remaining)
    assert fresh in remaining  # inside the grace period
    whole = get(client, tokens, f"/media/{media_id_of(exercise)}/download")
    assert whole.status_code == 200  # referenced audio untouched


# --- Attempts -------------------------------------------------------------------------------


def test_multiple_choice_listening_flow(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens)
    questions = exercise["questions"]
    attempt = start(client, tokens, exercise["exercise_id"])
    attempt_id = attempt["attempt_id"]
    assert attempt["current_stage"] == "listening"

    locked = get(client, tokens, f"/attempts/{attempt_id}/transcript")
    assert locked.status_code == 409 and locked.json()["code"] == "TRANSCRIPT_LOCKED"
    feedback = get(
        client, tokens, f"/attempts/{attempt_id}/answers/{questions[0]['question_id']}/feedback"
    )
    assert feedback.json()["code"] == "FEEDBACK_LOCKED"

    # Free navigation: question 3 can be current before 1 and 2 are answered.
    first_two = full_answers(exercise, right=True)[:1] + full_answers(exercise, right=False)[1:2]
    saved = save(
        client, tokens, attempt_id, first_two, current=questions[2]["question_id"], position=4_200
    )
    assert saved.status_code == 200, saved.text
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["current_stage"] == "quiz"
    assert detail["draft"]["playback_position_ms"] == 4_200
    assert detail["draft"]["current_question_id"] == questions[2]["question_id"]
    assert all(a["submitted_at"] is None for a in detail["answers"])  # nothing locked yet
    duration = exercise["content"]["audio"]["duration_ms"]
    beyond = save(client, tokens, attempt_id, position=duration + 1)
    assert beyond.status_code == 422

    # A missing answer blocks submission and names the question; nothing is locked.
    incomplete = submit(client, tokens, attempt_id)
    assert incomplete.status_code == 409
    assert incomplete.json()["details"] == [
        {"field": f"answers.{questions[2]['question_id']}", "message": "Answer this question."}
    ]
    assert all(
        a["submitted_at"] is None
        for a in get(client, tokens, f"/attempts/{attempt_id}").json()["answers"]
    )

    third = full_answers(exercise, right=True)[2:]
    assert save(client, tokens, attempt_id, third).status_code == 200
    response = submit(client, tokens, attempt_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["attempt"]["status"] == "completed"
    evaluation = result["evaluation"]
    assert evaluation["overall_score"] == pytest.approx(66.67)
    assert evaluation["summary"] == "2 of 3 answers correct."
    assert evaluation["quiz_summary"]["correct_count"] == 2
    assert evaluation["rubric_version"] == "listening-quiz-v1"

    transcript = get(client, tokens, f"/attempts/{attempt_id}/transcript").json()
    assert transcript["exercise_id"] == exercise["exercise_id"]
    assert {e["question_id"] for e in transcript["evidence"]} == {
        q["question_id"] for q in questions
    }
    for item in transcript["evidence"]:
        for span in item["spans"]:
            assert transcript["transcript"][span["start"] : span["end"]] == span["original"]
    wrong = get(
        client, tokens, f"/attempts/{attempt_id}/answers/{questions[1]['question_id']}/feedback"
    ).json()
    assert wrong["is_correct"] is False and wrong["correct_option_id"] == correct_option(
        questions[1]
    )
    after = save(client, tokens, attempt_id, third)
    assert after.status_code == 409  # answers are locked with the attempt
    # Replay after results uses the same stored audio.
    assert get(client, tokens, f"/media/{media_id_of(exercise)}/download").status_code == 200


def test_mixed_quiz_uses_grading_jobs_and_a_coordinator(client, engine) -> None:
    _, tokens = new_account(client)
    exercise, attempt_id, result = submitted(client, tokens, **MIXED)
    short = exercise["questions"][1]
    job = result["job"]
    assert job["job_type"] == "evaluate_attempt" and result["attempt"]["status"] == "submitted"
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert all(a["submitted_at"] is not None for a in detail["answers"])  # locked together
    assert [a["grading_status"] for a in detail["answers"]] == ["graded", "pending", "graded"]
    assert len(detail["active_jobs"]) == 2  # one grade_answer + the coordinator

    # Transcript unlocks at submission; evidence only for questions already graded.
    transcript = get(client, tokens, f"/attempts/{attempt_id}/transcript").json()
    assert short["question_id"] not in {e["question_id"] for e in transcript["evidence"]}
    assert len(transcript["evidence"]) == 2
    pending = get(client, tokens, f"/attempts/{attempt_id}/answers/{short['question_id']}/feedback")
    assert pending.json()["code"] == "GRADING_PENDING"

    # The coordinator waits for the grade without using one of its attempts.
    assert run_worker(lambda worker: worker._claim(UUID(job["job_id"]))) is None
    waiting = job_row(engine, job["job_id"])
    assert waiting["status"] == "queued" and waiting["attempt_count"] == 0
    assert waiting["next_retry_at"] is not None

    drain()
    done = job_row(engine, job["job_id"])
    assert done["status"] == "succeeded" and done["attempt_count"] == 1
    final = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert final["attempt"]["status"] == "completed"
    assert final["evaluation"]["overall_score"] == 100.0
    assert final["evaluation"]["summary"] == "3 of 3 points."
    assert final["evaluation"]["quiz_summary"]["correct_count"] is None
    assert len(get(client, tokens, f"/attempts/{attempt_id}/transcript").json()["evidence"]) == 3
    feedback = get(
        client, tokens, f"/attempts/{attempt_id}/answers/{short['question_id']}/feedback"
    ).json()
    assert feedback["awarded_points"] == 1.0 and feedback["reference_answer"] == ANSWERS[2]


def test_failed_grade_fails_coordinator_and_retry_reruns_only_that_grade(client) -> None:
    class Counting(FakeAIEngine):
        graded = 0

        def __init__(self, broken: bool = False) -> None:
            super().__init__()
            self.broken = broken

        async def grade_short_answer(self, request):
            Counting.graded += 1
            if self.broken and "market" in request.response_text:
                raise AIError("AI_UNAVAILABLE", retryable=True)
            return await super().grade_short_answer(request)

    _, tokens = new_account(client)
    exercise, attempt_id, result = submitted(
        client, tokens, question_count=4, question_types=["short_answer"]
    )
    drain(Counting(broken=True), rounds=30)
    coordinator = get(client, tokens, f"/jobs/{result['job']['job_id']}").json()
    assert coordinator["status"] == "failed" and coordinator["error"]["code"] == "GRADING_FAILED"
    assert coordinator["can_retry"] is True
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["status"] == "failed"
    assert [a["grading_status"] for a in detail["answers"]] == [
        "graded",
        "failed",
        "graded",
        "graded",
    ]
    failed_answer = detail["answers"][1]["answer_id"]
    assert detail["active_jobs"] == []
    # The failed child is retried through its coordinator, not on its own.
    (child_id,) = _job_ids_for_answer(failed_answer)
    child_job = get(client, tokens, f"/jobs/{child_id}").json()
    assert child_job["can_retry"] is False
    assert post(client, tokens, f"/jobs/{child_job['job_id']}/retry").status_code == 409

    Counting.graded = 0
    assert post(client, tokens, f"/jobs/{coordinator['job_id']}/retry").status_code == 202
    drain(Counting())
    assert Counting.graded == 1  # completed grades were kept, not re-run
    final = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert final["attempt"]["status"] == "completed"
    assert final["evaluation"]["overall_score"] == 100.0


def _job_ids_for_answer(answer_id) -> list[str]:
    settings = make_settings()
    database_engine = create_engine(settings.database_url, hide_parameters=True)
    try:
        with database_engine.connect() as connection:
            return [
                str(row)
                for row in connection.execute(
                    text("SELECT job_id FROM ai_jobs WHERE answer_id=:id"), {"id": answer_id}
                ).scalars()
            ]
    finally:
        database_engine.dispose()


def test_cancelling_the_coordinator_cancels_outstanding_grades(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id, result = submitted(client, tokens, **MIXED)
    cancel = post(client, tokens, f"/jobs/{result['job']['job_id']}/cancel")
    assert cancel.status_code == 200
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["active_jobs"] == []
    assert [a["grading_status"] for a in detail["answers"]] == ["graded", "cancelled", "graded"]
    assert detail["attempt"]["status"] == "failed"
    assert detail["evaluation"]["status"] == "cancelled"
    # Retrying the coordinator brings the cancelled grade back and finishes the attempt.
    assert post(client, tokens, f"/jobs/{result['job']['job_id']}/retry").status_code == 202
    drain()
    final = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert final["attempt"]["status"] == "completed"


def test_cancelling_the_attempt_stops_all_grading(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id, result = submitted(client, tokens, **MIXED)
    assert post(client, tokens, f"/attempts/{attempt_id}/cancel").status_code == 200
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["status"] == "cancelled" and detail["active_jobs"] == []
    coordinator = get(client, tokens, f"/jobs/{result['job']['job_id']}").json()
    assert coordinator["status"] == "cancelled" and coordinator["can_retry"] is False
    drain()
    assert get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["status"] == "cancelled"


def test_idempotent_whole_quiz_submit(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens, **MIXED)
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    assert save(client, tokens, attempt_id, full_answers(exercise)).status_code == 200
    key = str(uuid4())
    first = submit(client, tokens, attempt_id, key=key)
    body = {"revision": first.json()["attempt"]["revision"] - 1}
    second = post(client, tokens, f"/attempts/{attempt_id}/submit", body, key=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["job"]["job_id"] == second.json()["job"]["job_id"]
    assert len(get(client, tokens, f"/attempts/{attempt_id}").json()["active_jobs"]) == 2


# --- Ownership, availability and wrong-skill routes ------------------------------------------


def test_private_media_and_transcript_ownership(client) -> None:
    _, owner = new_account(client)
    _, intruder = new_account(client)
    exercise, attempt_id, _ = submitted(client, owner)
    media_id = media_id_of(exercise)
    for path in (
        f"/media/{media_id}",
        f"/media/{media_id}/download",
        f"/attempts/{attempt_id}/transcript",
        f"/exercises/{exercise['exercise_id']}",
        f"/media/{uuid4()}",
    ):
        response = get(client, intruder, path)
        assert response.status_code == 404, path
        assert response.json()["code"] == "NOT_FOUND"
    assert client.get(f"/api/v1/media/{media_id}/download").status_code == 401
    # Per-question submit is Reading only.
    question_id = exercise["questions"][0]["question_id"]
    response = post(
        client,
        owner,
        f"/attempts/{attempt_id}/answers/{question_id}/submit",
        {"revision": 1, "selected_option_id": correct_option(exercise["questions"][0])},
    )
    assert response.status_code == 409


def test_deleted_or_expired_audio_keeps_results(client, engine, media_dir) -> None:
    _, tokens = new_account(client)
    exercise, attempt_id, result = submitted(client, tokens)
    media_id = media_id_of(exercise)

    def set_media(**values):
        assignments = ", ".join(f"{k}=:{k}" for k in values)
        with engine.begin() as connection:
            connection.execute(
                text(f"UPDATE media_assets SET {assignments} WHERE media_id=:id"),
                {"id": media_id, **values},
            )

    # Expiry must follow creation (a table check), so move both into the past.
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE media_assets SET created_at=now() - interval '2 hours', "
                "expires_at=now() - interval '1 hour' WHERE media_id=:id"
            ),
            {"id": media_id},
        )
    expired = get(client, tokens, f"/media/{media_id}/download")
    assert expired.status_code == 410 and expired.json()["code"] == "MEDIA_UNAVAILABLE"
    assert get(client, tokens, f"/media/{media_id}").json()["available"] is False

    set_media(expires_at=None, status="deleted")
    gone = get(client, tokens, f"/media/{media_id}/download")
    assert gone.status_code == 410
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["evaluation"] == result["evaluation"]  # results stay, nothing invented
    assert detail["exercise"]["content"]["audio"]["available"] is False
    assert get(client, tokens, f"/attempts/{attempt_id}/transcript").status_code == 200
    retake = post(client, tokens, f"/exercises/{exercise['exercise_id']}/attempts", {})
    assert retake.status_code == 409 and retake.json()["code"] == "MEDIA_UNAVAILABLE"


def test_missing_file_is_reported_as_unavailable(client, media_dir) -> None:
    _, tokens = new_account(client)
    before = files(media_dir)
    exercise = ready(client, tokens)
    (key,) = files(media_dir) - before
    (media_dir / key).unlink()
    response = get(client, tokens, f"/media/{media_id_of(exercise)}/download")
    assert response.status_code == 410 and response.json()["code"] == "MEDIA_UNAVAILABLE"


def test_pending_media_is_not_downloadable(client, engine) -> None:
    _, tokens = new_account(client)
    user = get(client, tokens, "/users/me").json()
    media_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO media_assets (media_id, owner_user_id, storage_key, purpose, "
                "mime_type, size_bytes, status) VALUES (:id, :owner, :key, 'speaking_user_audio', "
                "'audio/wav', 0, 'pending')"
            ),
            {
                "id": media_id,
                "owner": user["user_id"],
                "key": f"speaking_user_audio/{uuid4().hex}.wav",
            },
        )
    response = get(client, tokens, f"/media/{media_id}/download")
    assert response.status_code == 409 and response.json()["code"] == "MEDIA_NOT_READY"
    assert response.json()["retryable"] is True
