"""Speaking end to end: real worker, fake STT/LLM/TTS, private recordings in a temp dir."""

import asyncio
import io
import os
import wave
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_auth_integration import bearer, make_settings, new_account
from test_database_integration import alembic
from test_writing_integration import FAST, drain, get, post

from app.ai.contracts import SpeakingCriterionResult, SpeakingEvaluation
from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.main import create_app
from app.modules.catalog.seed import seed

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]


@pytest.fixture(scope="module", autouse=True)
def media_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("speaking-media")
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


def recording(seconds: float = 2.0, rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def persona_id(client, tokens, index: int = 0) -> str:
    return get(client, tokens, "/personas").json()["items"][index]["persona_id"]


def ready_exercise(client, tokens) -> dict:
    body = {
        "difficulty": "intermediate",
        "topic": {"mode": "custom", "text": "Weekend plans"},
        "persona_id": persona_id(client, tokens),
    }
    response = post(client, tokens, "/speaking/exercises", body)
    assert response.status_code == 202, response.text
    drain()
    exercise = get(client, tokens, f"/exercises/{response.json()['exercise_id']}").json()
    assert exercise["generation_status"] == "ready", exercise
    return exercise


def started(client, tokens, greet: bool = True) -> tuple[dict, str]:
    exercise = ready_exercise(client, tokens)
    response = post(client, tokens, f"/exercises/{exercise['exercise_id']}/attempts", {})
    assert response.status_code == 201, response.text
    attempt_id = response.json()["attempt"]["attempt_id"]
    if greet:
        drain()
    return exercise, attempt_id


def turn(client, tokens, attempt_id, audio=None, key=None, idem=None):
    return client.post(
        f"/api/v1/speaking/attempts/{attempt_id}/turns",
        headers={**bearer(tokens), "Idempotency-Key": idem or str(uuid4())},
        files={"audio": ("turn.wav", audio if audio is not None else recording(), "audio/wav")},
        data={"client_message_key": key or str(uuid4())},
    )


def messages(client, tokens, attempt_id, **query) -> dict:
    params = "&".join(f"{k}={v}" for k, v in query.items())
    return get(client, tokens, f"/speaking/attempts/{attempt_id}/messages?{params}").json()


def action(client, tokens, attempt_id, name):
    return post(client, tokens, f"/speaking/attempts/{attempt_id}/{name}")


# --- Happy path --------------------------------------------------------------------------------


def test_full_conversation_and_feedback(client) -> None:
    _, tokens = new_account(client)
    exercise = ready_exercise(client, tokens)
    persona = exercise["content"]["persona"]
    assert set(persona) == {"persona_id", "name", "role_description"}  # no instructions
    assert exercise["content"]["rubric_version"] == "speaking-ielts-practice-v1"

    created = post(client, tokens, f"/exercises/{exercise['exercise_id']}/attempts", {})
    assert created.status_code == 201
    body = created.json()
    attempt_id = body["attempt"]["attempt_id"]
    assert body["attempt"]["current_stage"] == "conversation"
    assert body["conversation"]["status"] == "active"
    assert body["job"]["job_type"] == "start_conversation"
    assert body["conversation"]["active_job"]["job_id"] == body["job"]["job_id"]

    # A turn while the greeting is still being prepared is refused, not queued twice.
    busy = turn(client, tokens, attempt_id)
    assert busy.status_code == 409 and busy.json()["code"] == "TURN_IN_PROGRESS"
    drain()
    greeting = messages(client, tokens, attempt_id)["items"]
    assert len(greeting) == 1
    assert greeting[0]["sender"] == "assistant" and greeting[0]["delivery_status"] == "ready"
    assert persona["name"] in greeting[0]["transcript"]
    assert greeting[0]["audio"]["purpose"] == "speaking_ai_audio"

    first = turn(client, tokens, attempt_id, recording(2.0))
    assert first.status_code == 202, first.text
    result = first.json()
    assert result["job"]["job_type"] == "process_voice_turn"
    user_message = result["message"]
    assert user_message["sender"] == "user" and user_message["position"] == 2
    assert user_message["transcription_status"] == "pending"
    assert user_message["audio"]["purpose"] == "speaking_user_audio"
    assert user_message["audio"]["duration_ms"] == 2000
    drain()

    second = turn(client, tokens, attempt_id, recording(3.0))
    assert second.status_code == 202
    drain()
    items = messages(client, tokens, attempt_id)["items"]
    assert [(m["sender"], m["position"]) for m in items] == [
        ("assistant", 1),
        ("user", 2),
        ("assistant", 3),
        ("user", 4),
        ("assistant", 5),
    ]
    assert all(m["delivery_status"] == "ready" for m in items)
    assert items[2]["reply_to_message_id"] == items[1]["message_id"]
    assert items[1]["transcription_status"] == "completed" and items[1]["transcript"]
    replay = get(client, tokens, f"/media/{items[1]['audio']['media_id']}/download")
    assert replay.status_code == 200 and replay.content == recording(2.0)  # original kept

    page = messages(client, tokens, attempt_id, limit=2)
    assert [m["position"] for m in page["items"]] == [1, 2] and page["next_cursor"]
    rest = messages(client, tokens, attempt_id, limit=10, cursor=page["next_cursor"])
    assert [m["position"] for m in rest["items"]] == [3, 4, 5] and rest["next_cursor"] is None

    finished = action(client, tokens, attempt_id, "finish")
    assert finished.status_code == 202, finished.text
    assert finished.json()["job"]["job_type"] == "evaluate_attempt"
    assert finished.json()["attempt"]["status"] == "submitted"
    assert (
        get(client, tokens, f"/speaking/attempts/{attempt_id}/conversation").json()["status"]
        == "ended"
    )
    late = turn(client, tokens, attempt_id)
    assert late.status_code == 409 and late.json()["code"] == "CONVERSATION_ENDED"
    assert action(client, tokens, attempt_id, "resume").status_code == 409
    drain()

    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["attempt"]["status"] == "completed"
    assert detail["draft"] is None and detail["conversation"]["status"] == "ended"
    evaluation = detail["evaluation"]
    criteria = {c["criterion_code"]: c for c in evaluation["criteria"]}
    assert list(criteria) == [
        "fluency_coherence",
        "lexical_resource",
        "grammatical_range_accuracy",
        "pronunciation",
    ]
    for code in ("fluency_coherence", "pronunciation"):
        assert criteria[code]["assessment_status"] == "not_assessed"
        assert criteria[code]["score"] is None and criteria[code]["max_score"] is None
    for code in ("lexical_resource", "grammatical_range_accuracy"):
        assert criteria[code]["assessment_status"] == "assessed"
        assert criteria[code]["max_score"] == 9.0
    # A required criterion is unassessed, so there is no overall band (never a zero).
    assert evaluation["overall_score"] is None and evaluation["max_score"] is None
    assert any("audio assessor" in item for item in evaluation["feedback_payload"]["limitations"])
    assert evaluation["feedback_payload"]["corrections"] == []
    assert detail["attempt"]["score"] is None


# --- Idempotency and concurrency ------------------------------------------------------------


def test_retries_never_duplicate_turns(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    key, idem, audio = str(uuid4()), str(uuid4()), recording(1.5)
    first = turn(client, tokens, attempt_id, audio, key=key, idem=idem)
    again = turn(client, tokens, attempt_id, audio, key=key, idem=idem)  # exact retry
    assert first.status_code == again.status_code == 202
    assert first.json()["message"]["message_id"] == again.json()["message"]["message_id"]
    # Same client key, fresh Idempotency-Key, same audio: still the same turn.
    other_idem = turn(client, tokens, attempt_id, audio, key=key)
    assert other_idem.status_code == 202
    assert other_idem.json()["job"]["job_id"] == first.json()["job"]["job_id"]
    # Same client key with different audio is a conflict.
    changed = turn(client, tokens, attempt_id, recording(2.5), key=key)
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    # Same Idempotency-Key with different audio is a conflict too.
    reused = turn(client, tokens, attempt_id, recording(2.5), key=key, idem=idem)
    assert reused.status_code == 409
    drain()
    items = messages(client, tokens, attempt_id)["items"]
    assert [m["sender"] for m in items] == ["assistant", "user", "assistant"]


def test_simultaneous_turns_cannot_both_start(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: turn(client, tokens, attempt_id), range(4)))
    codes = sorted(r.status_code for r in responses)
    assert codes == [202, 409, 409, 409], [r.text for r in responses]
    assert all(r.json()["code"] == "TURN_IN_PROGRESS" for r in responses if r.status_code == 409)


# --- Failures, context and lifecycle -------------------------------------------------------


class Recorder(FakeAIEngine):
    histories: list = []

    def __init__(self, break_reply: bool = False) -> None:
        super().__init__()
        self.break_reply = break_reply

    async def converse(self, request):
        Recorder.histories.append([(t.sender, t.text) for t in request.history])
        if self.break_reply:
            raise AIError("AI_UNAVAILABLE", retryable=True)
        return await super().converse(request)


def test_failed_turns_stay_in_history_but_not_in_context(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    assert turn(client, tokens, attempt_id, recording(1.0)).status_code == 202
    drain()
    failing = turn(client, tokens, attempt_id, recording(4.0)).json()
    drain(Recorder(break_reply=True), rounds=10)
    job = get(client, tokens, f"/jobs/{failing['job']['job_id']}").json()
    assert job["status"] == "failed" and job["can_retry"] is True
    failed = messages(client, tokens, attempt_id)["items"][-1]
    assert failed["message_id"] == failing["message"]["message_id"]
    assert failed["delivery_status"] == "failed" and failed["transcription_status"] == "failed"
    assert failed["audio"]["status"] == "ready"  # recording kept for history

    # The next turn's context skips the failed one entirely.
    Recorder.histories = []
    assert turn(client, tokens, attempt_id, recording(2.0)).status_code == 202
    drain(Recorder())
    (history,) = Recorder.histories
    assert [sender for sender, _ in history] == ["assistant", "user", "assistant", "user"]
    assert len(history[1][1].split()) < len(history[3][1].split())  # 1 s turn, then 2 s turn
    assert not any("practice " * 8 in text for _, text in history)  # 4 s turn absent

    # A failed turn can be retried once nothing else is running.
    assert post(client, tokens, f"/jobs/{failing['job']['job_id']}/retry").status_code == 202
    drain()
    retried = next(
        m
        for m in messages(client, tokens, attempt_id)["items"]
        if m["message_id"] == failing["message"]["message_id"]
    )
    assert retried["delivery_status"] == "ready" and retried["transcription_status"] == "completed"


def test_silence_is_reported_not_invented(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    sent = turn(client, tokens, attempt_id, recording(0.1)).json()
    drain()
    job = get(client, tokens, f"/jobs/{sent['job']['job_id']}").json()
    assert job["status"] == "failed" and job["error"]["code"] == "NO_SPEECH_DETECTED"
    finish = action(client, tokens, attempt_id, "finish")
    assert finish.status_code == 409 and finish.json()["code"] == "STATE_CONFLICT"


def test_pause_resume_and_finish_rules(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens, greet=False)
    pending = action(client, tokens, attempt_id, "finish")
    assert pending.status_code == 409 and pending.json()["code"] == "TURN_IN_PROGRESS"
    drain()
    assert action(client, tokens, attempt_id, "finish").json()["code"] == "STATE_CONFLICT"

    sent = turn(client, tokens, attempt_id)
    paused = action(client, tokens, attempt_id, "pause")
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    assert paused.json()["active_job"]["job_id"] == sent.json()["job"]["job_id"]
    blocked = turn(client, tokens, attempt_id)
    assert blocked.status_code == 409 and blocked.json()["code"] == "CONVERSATION_PAUSED"
    drain()  # the accepted turn still finishes while paused
    assert messages(client, tokens, attempt_id)["items"][-1]["delivery_status"] == "ready"
    assert action(client, tokens, attempt_id, "pause").status_code == 200  # idempotent
    resumed = action(client, tokens, attempt_id, "resume")
    assert resumed.status_code == 200 and resumed.json()["status"] == "active"
    assert turn(client, tokens, attempt_id).status_code == 202


def test_cancel_attempt_ends_session_and_stops_voice_work(client) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    sent = turn(client, tokens, attempt_id).json()
    assert post(client, tokens, f"/attempts/{attempt_id}/cancel").status_code == 200
    conversation = get(client, tokens, f"/speaking/attempts/{attempt_id}/conversation").json()
    assert conversation["status"] == "ended" and conversation["active_job"] is None
    job = get(client, tokens, f"/jobs/{sent['job']['job_id']}").json()
    assert job["status"] == "cancelled" and job["can_retry"] is False
    last = messages(client, tokens, attempt_id)["items"][-1]
    assert last["delivery_status"] == "cancelled" and last["audio"]["status"] == "ready"
    assert action(client, tokens, attempt_id, "resume").json()["code"] == "CONVERSATION_ENDED"
    drain()


# --- Upload validation and ownership ---------------------------------------------------------


def test_uploads_are_checked_by_content(client, media_dir) -> None:
    _, tokens = new_account(client)
    _, attempt_id = started(client, tokens)
    before = {p for p in media_dir.rglob("*") if p.is_file()}
    fake_wav = turn(client, tokens, attempt_id, b"RIFF\x00\x00\x00\x00WAVEjunk" + b"\x00" * 64)
    assert fake_wav.status_code == 415 and fake_wav.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
    mp3 = turn(client, tokens, attempt_id, b"ID3\x04" + b"\x00" * 500)
    assert mp3.status_code == 415
    too_long = turn(client, tokens, attempt_id, recording(121, rate=8_000))
    assert too_long.status_code == 413 and too_long.json()["code"] == "CAPACITY_EXCEEDED"
    missing = client.post(
        f"/api/v1/speaking/attempts/{attempt_id}/turns",
        headers={**bearer(tokens), "Idempotency-Key": str(uuid4())},
        data={"client_message_key": str(uuid4())},
    )
    assert missing.status_code == 422
    assert {p for p in media_dir.rglob("*") if p.is_file()} == before  # nothing stored
    assert [m["sender"] for m in messages(client, tokens, attempt_id)["items"]] == ["assistant"]


def test_speaking_routes_respect_ownership_and_skill(client) -> None:
    _, owner = new_account(client)
    _, intruder = new_account(client)
    _, attempt_id = started(client, owner)
    greeting_audio = messages(client, owner, attempt_id)["items"][0]["audio"]["media_id"]
    for path in ("conversation", "messages"):
        response = get(client, intruder, f"/speaking/attempts/{attempt_id}/{path}")
        assert response.status_code == 404
    for name in ("pause", "resume", "finish"):
        assert action(client, intruder, attempt_id, name).status_code == 404
    assert turn(client, intruder, attempt_id).status_code == 404
    assert get(client, intruder, f"/media/{greeting_audio}/download").status_code == 404
    submit = post(client, owner, f"/attempts/{attempt_id}/submit", {"revision": 1})
    assert submit.status_code == 409  # Speaking finishes with /finish
    inactive = post(
        client,
        owner,
        "/speaking/exercises",
        {"difficulty": "beginner", "persona_id": str(uuid4())},
    )
    assert inactive.status_code == 422


# --- Audio-capable assessment ---------------------------------------------------------------


class Overclaiming(FakeAIEngine):
    """Claims scores for every criterion, including ones that need audio."""

    seen_recordings: list = []

    async def evaluate_speaking(self, request):
        Overclaiming.seen_recordings.append(len(request.recordings))
        return SpeakingEvaluation(
            summary="Clear answers.",
            criteria=[
                SpeakingCriterionResult(code=c.code, assessed=True, score=6.5, feedback="Good.")
                for c in request.criteria
            ],
        )


class AudioAssessor(Overclaiming):
    assesses_audio = True


def finished_attempt(client, tokens) -> tuple[str, str]:
    _, attempt_id = started(client, tokens)
    turn(client, tokens, attempt_id, recording(1.0))
    drain()
    turn(client, tokens, attempt_id, recording(2.0))
    drain()
    job = action(client, tokens, attempt_id, "finish").json()["job"]["job_id"]
    return attempt_id, job


def test_transcript_engine_cannot_score_pronunciation(client) -> None:
    _, tokens = new_account(client)
    attempt_id, _ = finished_attempt(client, tokens)
    Overclaiming.seen_recordings = []
    drain(Overclaiming())
    assert Overclaiming.seen_recordings == [0]  # no audio sent to a text-only engine
    evaluation = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    status = {c["criterion_code"]: c["assessment_status"] for c in evaluation["criteria"]}
    assert status["pronunciation"] == status["fluency_coherence"] == "not_assessed"
    assert evaluation["overall_score"] is None


def test_audio_assessor_gets_recordings_and_overall_band(client) -> None:
    _, tokens = new_account(client)
    attempt_id, _ = finished_attempt(client, tokens)
    Overclaiming.seen_recordings = []
    drain(AudioAssessor())
    assert Overclaiming.seen_recordings == [2]  # both original recordings
    evaluation = get(client, tokens, f"/attempts/{attempt_id}/evaluation").json()
    assert all(c["assessment_status"] == "assessed" for c in evaluation["criteria"])
    assert evaluation["overall_score"] == 6.5 and evaluation["max_score"] == 9.0
    summary = get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]
    assert summary["score"] == {"value": 6.5, "max": 9.0}


def test_evaluation_failure_keeps_conversation_and_retries(client, engine) -> None:
    _, tokens = new_account(client)
    attempt_id, job_id = finished_attempt(client, tokens)
    drain(FakeAIEngine(fail_with=AIError("AI_UNAVAILABLE", retryable=True), fail_times=99))
    failed = get(client, tokens, f"/jobs/{job_id}").json()
    assert failed["status"] == "failed" and failed["can_retry"] is True
    assert get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["status"] == "failed"
    assert len(messages(client, tokens, attempt_id)["items"]) == 5
    assert post(client, tokens, f"/jobs/{job_id}/retry").status_code == 202
    drain()
    assert get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["status"] == "completed"
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT count(*) FROM criterion_results c JOIN evaluations e USING (evaluation_id) "
                "WHERE e.attempt_id=:id"
            ),
            {"id": attempt_id},
        ).scalar_one()
    assert rows == 4
