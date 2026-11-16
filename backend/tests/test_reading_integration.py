"""Reading end to end with the real worker and the fake AI engine (_test database)."""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from test_auth_integration import bearer, make_settings, new_account
from test_database_integration import alembic
from test_writing_integration import FAST, drain, get, post, save, start

from app.ai.engine import AIError
from app.ai.fake import FakeAIEngine
from app.main import create_app
from app.modules.catalog.seed import seed

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]

KEYS = {"is_correct", "reference_answer", "reference_explanation", "evidence_spans", "explanation"}


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


def create(client, tokens, **body):
    body = {"difficulty": "intermediate", "topic": {"mode": "custom", "text": "Budaya"}, **body}
    return post(client, tokens, "/reading/exercises", body)


def ready(client, tokens, **body) -> dict:
    response = create(client, tokens, **body)
    assert response.status_code == 202, response.text
    drain()
    exercise = get(client, tokens, f"/exercises/{response.json()['exercise_id']}").json()
    assert exercise["generation_status"] == "ready", exercise
    return exercise


def correct_option(question: dict) -> str:
    """The fake engine puts the right answer at index (position - 1) % 4."""
    return question["options"][(question["position"] - 1) % 4]["option_id"]


def wrong_option(question: dict) -> str:
    right = correct_option(question)
    return next(o["option_id"] for o in question["options"] if o["option_id"] != right)


def revision(client, tokens, attempt_id) -> int:
    return get(client, tokens, f"/attempts/{attempt_id}").json()["attempt"]["revision"]


def answer(client, tokens, attempt_id, question_id, **body):
    body = {"revision": revision(client, tokens, attempt_id), **body}
    return post(client, tokens, f"/attempts/{attempt_id}/answers/{question_id}/submit", body)


def finish(client, tokens, attempt_id):
    body = {"revision": revision(client, tokens, attempt_id)}
    return post(client, tokens, f"/attempts/{attempt_id}/submit", body)


def draft(client, tokens, attempt_id, rev, answers=(), current=None, paragraph=0, offset=0):
    return client.patch(
        f"/api/v1/attempts/{attempt_id}/draft",
        headers=bearer(tokens),
        json={
            "revision": rev,
            "draft": {
                "skill": "reading",
                "paragraph_index": paragraph,
                "offset_in_paragraph": offset,
                "current_question_id": current,
                "answers": list(answers),
            },
        },
    )


def walk(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


# --- Happy paths --------------------------------------------------------------------------


def test_multiple_choice_reading_flow(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens)
    assert exercise["skill"] == "reading"
    passage = exercise["content"]["passage"]
    assert exercise["content"]["question_count"] == 5
    assert exercise["content"]["feedback_mode"] == "per_question"
    assert exercise["content"]["requested_word_count"] is None
    assert 120 <= len(passage.split()) <= 280  # default target 200 words, within tolerance
    questions = exercise["questions"]
    assert [q["position"] for q in questions] == [1, 2, 3, 4, 5]
    assert all(
        q["question_type"] == "multiple_choice" and len(q["options"]) == 4 for q in questions
    )
    assert not (set(walk(exercise)) & KEYS)  # no answer keys anywhere

    # Vocabulary is available before any attempt, with exact passage spans.
    vocabulary = get(client, tokens, f"/exercises/{exercise['exercise_id']}/vocabulary").json()
    assert len(vocabulary["items"]) == 5
    for item in vocabulary["items"]:
        for span in item["occurrences"]:
            assert passage[span["start"] : span["end"]] == span["original"]
        assert item["word_or_phrase"].lower() in item["example_from_passage"].lower()

    attempt = start(client, tokens, exercise["exercise_id"])
    attempt_id = attempt["attempt_id"]
    assert attempt["current_stage"] == "reading"
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert len(detail["answers"]) == 5
    assert all(
        a["grading_status"] == "pending" and not a["feedback_available"] for a in detail["answers"]
    )
    assert not (set(walk(detail)) & KEYS)

    q1, q2, *_ = questions
    saved = draft(
        client,
        tokens,
        attempt_id,
        1,
        answers=[
            {
                "question_id": q1["question_id"],
                "selected_option_id": wrong_option(q1),
                "response_text": None,
            }
        ],
        current=q1["question_id"],
        paragraph=1,
        offset=5,
    )
    assert saved.status_code == 200, saved.text
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["draft"]["paragraph_index"] == 1 and detail["draft"]["offset_in_paragraph"] == 5
    assert detail["draft"]["answers"][0]["selected_option_id"] == wrong_option(q1)
    assert detail["attempt"]["current_stage"] == "quiz"

    # Questions are answered in order.
    assert draft(client, tokens, attempt_id, 2, current=q2["question_id"]).status_code == 409
    skipped = answer(
        client, tokens, attempt_id, q2["question_id"], selected_option_id=correct_option(q2)
    )
    assert skipped.status_code == 409
    assert (
        get(client, tokens, f"/attempts/{attempt_id}/answers/{q1['question_id']}/feedback").json()[
            "code"
        ]
        == "FEEDBACK_LOCKED"
    )

    wrong = answer(
        client, tokens, attempt_id, q1["question_id"], selected_option_id=wrong_option(q1)
    )
    assert wrong.status_code == 200, wrong.text
    body = wrong.json()
    assert body["attempt_revision"] == 3
    assert body["answer"]["grading_status"] == "graded" and body["answer"]["feedback_available"]
    feedback = body["feedback"]
    assert feedback["is_correct"] is False and feedback["awarded_points"] == 0
    assert feedback["correct_option_id"] == correct_option(q1)
    assert feedback["explanation"] and feedback["reference_answer"] is None
    for span in feedback["evidence_spans"]:
        assert passage[span["start"] : span["end"]] == span["original"]
    again = get(client, tokens, f"/attempts/{attempt_id}/answers/{q1['question_id']}/feedback")
    assert again.json() == feedback
    # Locked: neither resubmission nor draft edits can change it.
    assert (
        answer(
            client, tokens, attempt_id, q1["question_id"], selected_option_id=correct_option(q1)
        ).status_code
        == 409
    )
    locked = draft(
        client,
        tokens,
        attempt_id,
        revision(client, tokens, attempt_id),
        answers=[
            {"question_id": q1["question_id"], "selected_option_id": None, "response_text": None}
        ],
    )
    assert locked.status_code == 409
    # Other questions' keys stay hidden.
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert not (set(walk(detail)) & KEYS)

    assert finish(client, tokens, attempt_id).status_code == 409  # unanswered questions
    for question in questions[1:]:
        ok = answer(
            client,
            tokens,
            attempt_id,
            question["question_id"],
            selected_option_id=correct_option(question),
        )
        assert ok.status_code == 200 and ok.json()["feedback"]["is_correct"] is True

    stale = post(client, tokens, f"/attempts/{attempt_id}/submit", {"revision": 1})
    assert stale.status_code == 409 and stale.json()["code"] == "REVISION_CONFLICT"
    done = finish(client, tokens, attempt_id)
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["attempt"]["status"] == "completed"
    evaluation = result["evaluation"]
    assert evaluation["status"] == "completed"
    assert evaluation["overall_score"] == 80.0 and evaluation["max_score"] == 100.0
    assert evaluation["quiz_summary"] == {
        "question_count": 5,
        "graded_count": 5,
        "correct_count": 4,
        "awarded_points": 4.0,
        "max_points": 5.0,
    }
    assert evaluation["summary"] == "4 of 5 answers correct."
    assert evaluation["criteria"] == [] and evaluation["corrected_text"] is None
    history = get(client, tokens, "/attempts?skill=reading").json()["items"]
    assert history[0]["score"] == {"value": 80.0, "max": 100.0}


def test_mixed_quiz_with_short_answers(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(
        client,
        tokens,
        question_count=4,
        question_types=["multiple_choice", "short_answer"],
        requested_word_count=150,
    )
    questions = exercise["questions"]
    assert [q["question_type"] for q in questions] == [
        "multiple_choice",
        "short_answer",
        "multiple_choice",
        "short_answer",
    ]
    assert questions[1]["options"] == []
    assert exercise["content"]["requested_word_count"] == 150
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    q1, q2, q3, q4 = questions

    assert (
        answer(
            client, tokens, attempt_id, q1["question_id"], selected_option_id=correct_option(q1)
        ).status_code
        == 200
    )
    queued = answer(
        client, tokens, attempt_id, q2["question_id"], response_text="near the old market"
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["job"]["job_type"] == "grade_answer"
    assert queued.json()["job"]["target"]["type"] == "answer"
    assert queued.json()["answer"]["grading_status"] == "pending"
    pending = get(client, tokens, f"/attempts/{attempt_id}/answers/{q2['question_id']}/feedback")
    assert pending.status_code == 409 and pending.json()["code"] == "GRADING_PENDING"
    assert len(get(client, tokens, f"/attempts/{attempt_id}").json()["active_jobs"]) == 1

    # The next question can be answered while grading runs.
    assert (
        answer(
            client, tokens, attempt_id, q3["question_id"], selected_option_id=wrong_option(q3)
        ).status_code
        == 200
    )
    assert (
        answer(
            client, tokens, attempt_id, q4["question_id"], response_text="The shopkeeper"
        ).status_code
        == 202
    )
    assert finish(client, tokens, attempt_id).json()["code"] == "GRADING_PENDING"

    drain()
    graded = get(
        client, tokens, f"/attempts/{attempt_id}/answers/{q2['question_id']}/feedback"
    ).json()
    assert graded["awarded_points"] == 1.0 and graded["is_correct"] is None
    assert graded["reference_answer"] == "Near the old market"
    assert "development engine" in graded["explanation"]
    q4_feedback = get(
        client, tokens, f"/attempts/{attempt_id}/answers/{q4['question_id']}/feedback"
    ).json()
    assert q4_feedback["awarded_points"] == 0.0  # Mira helped her teacher, not the shopkeeper

    result = finish(client, tokens, attempt_id).json()
    assert result["evaluation"]["quiz_summary"]["correct_count"] is None  # mixed quiz
    assert result["evaluation"]["quiz_summary"]["awarded_points"] == 2.0
    assert result["evaluation"]["overall_score"] == 50.0
    assert result["evaluation"]["summary"] == "2 of 4 points."


def test_retake_creates_numbered_practice_attempt(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens, question_count=1)
    first = start(client, tokens, exercise["exercise_id"])
    second = start(client, tokens, exercise["exercise_id"])
    assert (first["attempt_number"], second["attempt_number"]) == (1, 2)
    source = post(
        client,
        tokens,
        f"/exercises/{exercise['exercise_id']}/attempts",
        {"source_attempt_id": first["attempt_id"]},
    )
    assert source.status_code == 422  # copying is Writing only


# --- Validation and capacity --------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"question_count": 16}, 413),
        ({"requested_word_count": 5000}, 413),
        ({"question_count": 5, "requested_word_count": 50}, 422),
        ({"question_types": ["short_answer", "short_answer"]}, 422),
        ({"question_types": []}, 422),
        ({"question_types": ["essay"]}, 422),
        ({"question_count": 0}, 422),
    ],
)
def test_generation_requests_are_honoured_or_rejected(client, body, status) -> None:
    _, tokens = new_account(client)
    assert create(client, tokens, **body).status_code == status


def test_draft_answer_validation(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(
        client, tokens, question_count=2, question_types=["multiple_choice", "short_answer"]
    )
    other = ready(client, tokens, question_count=1)
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    mcq, short = exercise["questions"]
    cases = [
        {"question_id": mcq["question_id"], "selected_option_id": None, "response_text": "text"},
        {
            "question_id": short["question_id"],
            "selected_option_id": correct_option(mcq),
            "response_text": None,
        },
        {
            "question_id": mcq["question_id"],
            "selected_option_id": str(uuid4()),
            "response_text": None,
        },
        {
            "question_id": other["questions"][0]["question_id"],
            "selected_option_id": None,
            "response_text": None,
        },
        {
            "question_id": mcq["question_id"],
            "selected_option_id": correct_option(mcq),
            "response_text": "x",
        },
    ]
    for case in cases:
        assert draft(client, tokens, attempt_id, 1, answers=[case]).status_code == 422, case
    assert draft(client, tokens, attempt_id, 1, paragraph=99).status_code == 422
    ok = draft(
        client,
        tokens,
        attempt_id,
        1,
        answers=[
            {
                "question_id": short["question_id"],
                "selected_option_id": None,
                "response_text": "draft",
            },
        ],
    )
    assert ok.status_code == 200
    cleared = draft(
        client,
        tokens,
        attempt_id,
        2,
        answers=[
            {
                "question_id": short["question_id"],
                "selected_option_id": None,
                "response_text": None,
            },
        ],
    )
    assert cleared.status_code == 200
    assert (
        get(client, tokens, f"/attempts/{attempt_id}").json()["draft"]["answers"][1][
            "response_text"
        ]
        is None
    )
    # Omitted answers keep their values.
    draft(
        client,
        tokens,
        attempt_id,
        3,
        answers=[
            {
                "question_id": mcq["question_id"],
                "selected_option_id": correct_option(mcq),
                "response_text": None,
            },
        ],
    )
    draft(client, tokens, attempt_id, 4, answers=[])
    assert get(client, tokens, f"/attempts/{attempt_id}").json()["draft"]["answers"][0][
        "selected_option_id"
    ] == correct_option(mcq)
    # Wrong submit formats.
    for body in (
        {"selected_option_id": correct_option(mcq), "response_text": "x"},
        {},
        {"response_text": " "},
    ):
        assert answer(client, tokens, attempt_id, mcq["question_id"], **body).status_code == 422, (
            body
        )
    assert (
        answer(client, tokens, attempt_id, mcq["question_id"], response_text="text").status_code
        == 422
    )


def test_invalid_generated_package_fails_safely(client) -> None:
    class WrongCount(FakeAIEngine):
        async def generate_reading(self, request):
            package = await super().generate_reading(request)
            return package.model_copy(update={"questions": package.questions[:-1]})

    _, tokens = new_account(client)
    created = create(client, tokens).json()
    drain(WrongCount())
    job = get(client, tokens, f"/jobs/{created['job']['job_id']}").json()
    assert job["status"] == "failed" and job["error"]["code"] == "AI_OUTPUT_INVALID"
    exercise = get(client, tokens, f"/exercises/{created['exercise_id']}").json()
    assert exercise["generation_status"] == "failed" and exercise["questions"] == []


# --- Failures, cancellation and ownership --------------------------------------------------


def test_short_answer_grading_failure_and_retry(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens, question_count=2, question_types=["short_answer"])
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    q1 = exercise["questions"][0]
    job = answer(client, tokens, attempt_id, q1["question_id"], response_text="A blue kite").json()[
        "job"
    ]
    drain(FakeAIEngine(fail_with=AIError("AI_UNAVAILABLE", retryable=True), fail_times=99))
    failed = get(client, tokens, f"/jobs/{job['job_id']}").json()
    assert failed["status"] == "failed" and failed["can_retry"] is True
    feedback = get(client, tokens, f"/attempts/{attempt_id}/answers/{q1['question_id']}/feedback")
    assert feedback.json()["code"] == "GRADING_FAILED"
    assert finish(client, tokens, attempt_id).status_code == 409
    assert post(client, tokens, f"/jobs/{job['job_id']}/retry").status_code == 202
    drain()
    assert (
        get(client, tokens, f"/attempts/{attempt_id}/answers/{q1['question_id']}/feedback").json()[
            "awarded_points"
        ]
        == 1.0
    )


def test_cancel_attempt_cancels_answer_grading(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens, question_count=1, question_types=["short_answer"])
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    question_id = exercise["questions"][0]["question_id"]
    job = answer(client, tokens, attempt_id, question_id, response_text="A blue kite").json()["job"]
    assert post(client, tokens, f"/attempts/{attempt_id}/cancel").status_code == 200
    job_now = get(client, tokens, f"/jobs/{job['job_id']}").json()
    assert job_now["status"] == "cancelled" and job_now["can_retry"] is False
    detail = get(client, tokens, f"/attempts/{attempt_id}").json()
    assert detail["answers"][0]["grading_status"] == "cancelled"
    assert detail["answers"][0]["response_text"] == "A blue kite"  # history kept


def test_reading_routes_respect_ownership_and_skill(client) -> None:
    _, owner = new_account(client)
    _, intruder = new_account(client)
    exercise = ready(client, owner, question_count=1)
    attempt_id = start(client, owner, exercise["exercise_id"])["attempt_id"]
    question_id = exercise["questions"][0]["question_id"]
    answer(
        client,
        owner,
        attempt_id,
        question_id,
        selected_option_id=correct_option(exercise["questions"][0]),
    )
    for path in (
        f"/exercises/{exercise['exercise_id']}/vocabulary",
        f"/attempts/{attempt_id}/answers/{question_id}/feedback",
    ):
        assert get(client, intruder, path).status_code == 404, path
    response = post(
        client,
        intruder,
        f"/attempts/{attempt_id}/answers/{question_id}/submit",
        {"revision": 1, "selected_option_id": str(uuid4())},
    )
    assert response.status_code == 404
    unknown = get(client, owner, f"/attempts/{attempt_id}/answers/{uuid4()}/feedback")
    assert unknown.status_code == 404

    # Writing exercises have no vocabulary and no per-question submission.
    writing = post(client, owner, "/writing/exercises", {"difficulty": "beginner"}).json()
    drain()
    assert get(client, owner, f"/exercises/{writing['exercise_id']}/vocabulary").status_code == 409
    writing_attempt = start(client, owner, writing["exercise_id"])["attempt_id"]
    save(client, owner, writing_attempt, 1, "text")
    blocked = post(
        client,
        owner,
        f"/attempts/{writing_attempt}/answers/{uuid4()}/submit",
        {"revision": 2, "response_text": "x"},
    )
    assert blocked.status_code == 409


def test_idempotent_answer_submission(client) -> None:
    _, tokens = new_account(client)
    exercise = ready(client, tokens, question_count=1)
    attempt_id = start(client, tokens, exercise["exercise_id"])["attempt_id"]
    question = exercise["questions"][0]
    key = str(uuid4())
    body = {"revision": 1, "selected_option_id": correct_option(question)}
    path = f"/attempts/{attempt_id}/answers/{question['question_id']}/submit"
    first = post(client, tokens, path, body, key=key)
    replay = post(client, tokens, path, body, key=key)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert revision(client, tokens, attempt_id) == 2  # applied once
