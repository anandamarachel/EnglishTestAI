"""Exercise the migrated PostgreSQL schema, including deferred cross-table checks."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from test_database_integration import alembic

from app.core.config import Settings
from app.db import models as m

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]


@pytest.fixture(scope="module")
def engine():
    settings = Settings()
    if not settings.postgres_db.endswith("_test"):
        pytest.fail("Refusing schema tests: POSTGRES_DB must end with _test")
    alembic("upgrade", "head")
    db = create_engine(settings.database_url, hide_parameters=True)
    yield db
    db.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as connection, connection.begin() as transaction:
        yield connection
        transaction.rollback()


def add(conn, model, **values):
    table = model.__table__
    return conn.execute(insert(table).values(**values).returning(*table.primary_key)).scalar_one()


def change(conn, model, identity, **values):
    table = model.__table__
    conn.execute(update(table).where(next(iter(table.primary_key)) == identity).values(**values))


def validate(conn):
    # Force commit-time constraints while keeping test data inside a rollback-only transaction.
    conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))


@contextmanager
def rejected(conn, message):
    validate(conn)
    with pytest.raises(IntegrityError, match=message), conn.begin_nested():
        yield
        validate(conn)


def user(conn):
    return add(
        conn,
        m.User,
        email=f"{uuid4()}@example.test",
        password_hash="test-hash",
        display_name="Learner",
    )


def media(conn, owner, purpose="listening_audio"):
    return add(
        conn,
        m.MediaAsset,
        owner_user_id=owner,
        purpose=purpose,
        storage_key=f"test/{uuid4()}.wav",
        mime_type="audio/wav",
        size_bytes=128,
        status="ready",
    )


def exercise(conn, skill="writing", owner=None, ready=True):
    owner = owner or user(conn)
    eid = add(
        conn,
        m.Exercise,
        created_by=owner,
        topic_selection="custom",
        custom_topic="Travel",
        skill=skill,
        difficulty="intermediate",
        content_cefr_level="B1",
        title="Travel practice",
        instructions="Practise your English.",
    )
    if skill == "writing":
        add(conn, m.WritingExercise, exercise_id=eid, rubric_version="v1", rubric_snapshot={})
    elif skill in ("reading", "listening"):
        if skill == "reading":
            add(
                conn,
                m.ReadingExercise,
                exercise_id=eid,
                passage="Hi 🌍. We travel.",
                question_count=1,
            )
        else:
            add(
                conn,
                m.ListeningExercise,
                exercise_id=eid,
                transcript="Hi 🌍. We travel.",
                question_count=1,
                audio_media_id=media(conn, owner),
            )
        qid = add(
            conn,
            m.Question,
            exercise_id=eid,
            question_type="multiple_choice",
            question_text="What do we do?",
            reference_explanation="We travel.",
            grading_method="answer_key",
            position=1,
            max_points=1,
        )
        add(
            conn,
            m.QuestionOption,
            question_id=qid,
            option_text="Travel",
            position=1,
            is_correct=True,
        )
        add(
            conn,
            m.QuestionOption,
            question_id=qid,
            option_text="Sleep",
            position=2,
            is_correct=False,
        )
    else:
        persona = add(
            conn,
            m.AIPersona,
            name="Guide",
            role_description="Friendly guide",
            behavior_instructions="Discuss travel.",
            voice_key="guide",
        )
        add(
            conn,
            m.SpeakingExercise,
            exercise_id=eid,
            persona_id=persona,
            persona_snapshot={"name": "Guide"},
            rubric_version="v1",
            rubric_snapshot={},
        )
    if ready:
        change(conn, m.Exercise, eid, generation_status="ready")
    return eid, owner


def attempt(conn, eid, owner, skill="writing", number=1, source=None):
    aid = add(
        conn,
        m.Attempt,
        user_id=owner,
        exercise_id=eid,
        attempt_number=number,
        source_attempt_id=source,
        current_stage="conversation" if skill == "speaking" else skill,
    )
    details = {
        "writing": m.WritingAttempt,
        "reading": m.ReadingAttempt,
        "listening": m.ListeningAttempt,
        "speaking": m.ConversationSession,
    }
    add(conn, details[skill], attempt_id=aid)
    return aid


def question(conn, eid):
    qid = conn.execute(
        select(m.Question.question_id).where(m.Question.exercise_id == eid)
    ).scalar_one()
    option = conn.execute(
        select(m.QuestionOption.option_id).where(
            m.QuestionOption.question_id == qid, m.QuestionOption.is_correct
        )
    ).scalar_one()
    return qid, option


def submit(conn, aid):
    change(
        conn,
        m.Attempt,
        aid,
        status="submitted",
        current_stage="evaluation",
        submitted_at=datetime.now(UTC),
    )


@pytest.mark.parametrize("skill", ["writing", "reading", "listening", "speaking"])
def test_four_skill_attempts(conn, skill):
    eid, owner = exercise(conn, skill)
    attempt(conn, eid, owner, skill)
    validate(conn)


def test_ready_exercise_requires_matching_detail(conn):
    eid, _ = exercise(conn, ready=False)
    conn.execute(delete(m.WritingExercise).where(m.WritingExercise.exercise_id == eid))
    with rejected(conn, "requires exactly one skill detail"):
        change(conn, m.Exercise, eid, generation_status="ready")
    with rejected(conn, "detail does not match skill"):
        add(conn, m.ReadingExercise, exercise_id=eid, passage="Some text", question_count=1)


def test_attempt_ownership_and_required_detail(conn):
    eid, owner = exercise(conn)
    stranger = user(conn)
    with rejected(conn, "owned ready exercise"):
        attempt(conn, eid, stranger)
    with rejected(conn, "exactly one matching skill detail"):
        add(
            conn,
            m.Attempt,
            user_id=owner,
            exercise_id=eid,
            attempt_number=1,
            current_stage="writing",
        )


def test_writing_long_draft_freezes_and_can_be_revised_as_new_attempt(conn):
    eid, owner = exercise(conn)
    aid = attempt(conn, eid, owner)
    response = "A long English response. " * 100
    change(conn, m.WritingAttempt, aid, response_text=response)
    submit(conn, aid)
    validate(conn)
    assert (
        conn.execute(
            select(m.WritingAttempt.response_text).where(m.WritingAttempt.attempt_id == aid)
        ).scalar_one()
        == response
    )
    with rejected(conn, "content is immutable"):
        change(conn, m.WritingAttempt, aid, response_text="Replacement")
    with rejected(conn, "content is immutable"):
        change(conn, m.Exercise, eid, instructions="Changed question")
    copied = attempt(conn, eid, owner, number=2, source=aid)
    change(conn, m.WritingAttempt, copied, response_text=response + " Revised.")
    validate(conn)


def test_writing_source_must_be_submitted_on_same_exercise(conn):
    eid, owner = exercise(conn)
    original = attempt(conn, eid, owner)
    with rejected(conn, "Invalid Writing source attempt"):
        attempt(conn, eid, owner, number=2, source=original)


def test_quiz_cross_exercise_answer_option_and_progress(conn):
    eid, owner = exercise(conn, "reading")
    other, _ = exercise(conn, "reading", owner)
    aid = attempt(conn, eid, owner, "reading")
    qid, option = question(conn, eid)
    other_qid, other_option = question(conn, other)
    with rejected(conn, "Answer question, option"):
        add(conn, m.Answer, attempt_id=aid, question_id=other_qid, selected_option_id=other_option)
    with rejected(conn, "Answer question, option"):
        add(conn, m.Answer, attempt_id=aid, question_id=qid, selected_option_id=other_option)
    with rejected(conn, "Progress question belongs"):
        change(conn, m.ReadingAttempt, aid, current_question_id=other_qid)
    add(conn, m.Answer, attempt_id=aid, question_id=qid, selected_option_id=option)
    validate(conn)


def test_reading_submission_locks_answer_and_requires_grading(conn):
    eid, owner = exercise(conn, "reading")
    aid = attempt(conn, eid, owner, "reading")
    qid, option = question(conn, eid)
    ans = add(
        conn,
        m.Answer,
        attempt_id=aid,
        question_id=qid,
        selected_option_id=option,
        submitted_at=datetime.now(UTC),
    )
    with rejected(conn, "Submitted answers are immutable"):
        change(conn, m.Answer, ans, selected_option_id=None)
    with rejected(conn, "before grading finishes"):
        submit(conn, aid)
    with rejected(conn, "Answer question, option"):
        change(conn, m.Answer, ans, grading_status="graded", awarded_points=2)
    change(conn, m.Answer, ans, grading_status="graded", awarded_points=1)
    submit(conn, aid)
    validate(conn)
    with rejected(conn, "grades are immutable"):
        change(conn, m.Answer, ans, awarded_points=0)


def test_listening_requires_all_locked_answers_but_can_wait_for_grading(conn):
    eid, owner = exercise(conn, "listening")
    aid = attempt(conn, eid, owner, "listening")
    with rejected(conn, "requires all answers"):
        submit(conn, aid)
    qid, option = question(conn, eid)
    add(
        conn,
        m.Answer,
        attempt_id=aid,
        question_id=qid,
        selected_option_id=option,
        submitted_at=datetime.now(UTC),
    )
    submit(conn, aid)
    validate(conn)


def test_ready_mcq_requires_exactly_one_key(conn):
    eid, _ = exercise(conn, "reading", ready=False)
    qid, option = question(conn, eid)
    change(conn, m.QuestionOption, option, is_correct=False)
    with rejected(conn, "exactly one correct choice"):
        change(conn, m.Exercise, eid, generation_status="ready")
    conn.execute(
        update(m.QuestionOption).where(m.QuestionOption.question_id == qid).values(is_correct=True)
    )
    with rejected(conn, "exactly one correct choice"):
        change(conn, m.Exercise, eid, generation_status="ready")


def test_vocabulary_unicode_spans_available_before_attempt(conn):
    eid, _ = exercise(conn, "reading")
    vocab = add(
        conn,
        m.ExerciseVocabulary,
        exercise_id=eid,
        word_or_phrase="world",
        meaning="Earth",
        example_sentence="Our world.",
        example_from_passage="Hi 🌍.",
        occurrences=[{"start": 3, "end": 4, "original": "🌍"}],
        position=1,
    )
    validate(conn)
    with rejected(conn, "does not match immutable source"):
        change(
            conn,
            m.ExerciseVocabulary,
            vocab,
            occurrences=[{"start": 3, "end": 5, "original": "🌍"}],
        )


def test_listening_audio_readiness_and_owner(conn):
    eid, _ = exercise(conn, "listening", ready=False)
    mid = conn.execute(
        select(m.ListeningExercise.audio_media_id).where(m.ListeningExercise.exercise_id == eid)
    ).scalar_one()
    change(conn, m.MediaAsset, mid, status="pending")
    with rejected(conn, "requires ready audio"):
        change(conn, m.Exercise, eid, generation_status="ready")
    wrong_audio = media(conn, user(conn))
    with rejected(conn, "Invalid Listening media ownership"):
        change(conn, m.ListeningExercise, eid, audio_media_id=wrong_audio)
    change(conn, m.MediaAsset, mid, status="ready")
    change(conn, m.Exercise, eid, generation_status="ready")
    with rejected(conn, "requires ready audio"):
        change(conn, m.MediaAsset, mid, status="failed")


def test_writing_feedback_spans_and_missing_required_score(conn):
    eid, owner = exercise(conn)
    aid = attempt(conn, eid, owner)
    change(conn, m.WritingAttempt, aid, response_text="I 🌍 go.")
    submit(conn, aid)
    ev = add(
        conn,
        m.Evaluation,
        attempt_id=aid,
        rubric_version="v1",
        rubric_snapshot={"criteria": [{"code": "grammar", "required": True}]},
    )
    correction = {
        "correction_id": "c1",
        "start": 4,
        "end": 6,
        "original": "go",
        "replacement": "went",
        "category": "grammar",
        "title": "Past tense",
        "explanation": "Use the past tense.",
        "example": "I went.",
    }
    payload = {"schema_version": 1, "corrections": [correction], "limitations": []}
    change(conn, m.Evaluation, ev, feedback_payload=payload)
    validate(conn)
    with rejected(conn, "does not match immutable source"):
        change(
            conn,
            m.Evaluation,
            ev,
            feedback_payload={**payload, "corrections": [{**correction, "start": 3}]},
        )
    add(
        conn,
        m.CriterionResult,
        evaluation_id=ev,
        criterion_code="grammar",
        assessment_status="not_assessed",
        feedback="Assessment unavailable.",
    )
    completed = datetime.now(UTC)
    change(
        conn, m.Attempt, aid, status="completed", current_stage="results", completed_at=completed
    )
    change(conn, m.Evaluation, ev, status="completed", completed_at=completed)
    validate(conn)  # Feedback can finish without inventing a score.
    with rejected(conn, "unassessed required criterion"):
        change(conn, m.Evaluation, ev, overall_score=80, max_score=100)


def test_job_deduplication_ownership_and_cancellation(conn):
    eid, owner = exercise(conn, ready=False)
    job = add(
        conn,
        m.AIJob,
        requested_by=owner,
        exercise_id=eid,
        job_type="generate_exercise",
        max_attempts=3,
    )
    with rejected(conn, "uq_ai_jobs_active_exercise_id"):
        add(
            conn,
            m.AIJob,
            requested_by=owner,
            exercise_id=eid,
            job_type="generate_exercise",
            max_attempts=3,
        )
    other, _ = exercise(conn, ready=False)
    with rejected(conn, "AI job owner or target"):
        add(
            conn,
            m.AIJob,
            requested_by=owner,
            exercise_id=other,
            job_type="generate_exercise",
            max_attempts=3,
        )
    now = datetime.now(UTC)
    change(
        conn,
        m.AIJob,
        job,
        status="running",
        started_at=now,
        lease_expires_at=now + timedelta(minutes=1),
        attempt_count=1,
    )
    with rejected(conn, "Cancellation must invalidate"):
        change(conn, m.AIJob, job, status="cancel_requested", cancel_requested_at=now)
    change(
        conn, m.AIJob, job, status="cancel_requested", cancel_requested_at=now, execution_version=2
    )
    with rejected(conn, "Cancelled execution cannot commit"):
        change(conn, m.AIJob, job, status="succeeded", finished_at=now)
    change(conn, m.AIJob, job, status="cancelled", finished_at=now)
    with rejected(conn, "Retry requires a fresh execution"):
        change(conn, m.AIJob, job, status="queued", finished_at=None)
    change(
        conn,
        m.AIJob,
        job,
        status="queued",
        execution_version=3,
        attempt_count=0,
        finished_at=None,
        lease_expires_at=None,
        cancel_requested_at=None,
    )
    validate(conn)


def test_voice_session_serializes_turn_jobs(conn):
    eid, owner = exercise(conn, "speaking")
    aid = attempt(conn, eid, owner, "speaking")
    sid = conn.execute(
        select(m.ConversationSession.conversation_session_id).where(
            m.ConversationSession.attempt_id == aid
        )
    ).scalar_one()
    messages = [
        add(
            conn,
            m.ConversationMessage,
            conversation_session_id=sid,
            client_message_key=uuid4(),
            sender="user",
            position=position,
            transcription_status="pending",
        )
        for position in (1, 2)
    ]
    change(conn, m.ConversationSession, sid, next_position=3)
    add(
        conn,
        m.AIJob,
        requested_by=owner,
        message_id=messages[0],
        job_type="process_voice_turn",
        max_attempts=3,
    )
    with rejected(conn, "one active voice job"):
        add(
            conn,
            m.AIJob,
            requested_by=owner,
            message_id=messages[1],
            job_type="process_voice_turn",
            max_attempts=3,
        )
    with rejected(conn, "one active voice job"):
        add(
            conn,
            m.AIJob,
            requested_by=owner,
            attempt_id=aid,
            job_type="start_conversation",
            max_attempts=3,
        )


def test_speaking_successful_turn_and_optional_transcription_stream(conn):
    eid, owner = exercise(conn, "speaking")
    aid = attempt(conn, eid, owner, "speaking")
    sid = conn.execute(
        select(m.ConversationSession.conversation_session_id).where(
            m.ConversationSession.attempt_id == aid
        )
    ).scalar_one()
    mid = add(
        conn,
        m.ConversationMessage,
        conversation_session_id=sid,
        client_message_key=uuid4(),
        sender="user",
        position=1,
        transcription_status="completed",
        transcript="Hello.",
        audio_media_id=media(conn, owner, "speaking_user_audio"),
        delivery_status="ready",
    )
    add(
        conn,
        m.ConversationMessage,
        conversation_session_id=sid,
        client_message_key=uuid4(),
        sender="assistant",
        position=2,
        reply_to_message_id=mid,
        transcription_status="not_applicable",
        transcript="Hi!",
        audio_media_id=media(conn, owner, "speaking_ai_audio"),
        delivery_status="ready",
    )
    change(conn, m.ConversationSession, sid, next_position=3)
    validate(conn)
    with rejected(conn, "Ready messages are immutable"):
        change(conn, m.ConversationMessage, mid, transcript="Different text.")
    submit(conn, aid)
    change(conn, m.ConversationSession, sid, status="ended", ended_at=datetime.now(UTC))
    validate(conn)


def test_expiring_tokens_and_request_idempotency(conn):
    owner = user(conn)
    now = datetime.now(UTC)
    with rejected(conn, "valid_times"):
        add(
            conn,
            m.PasswordResetToken,
            user_id=owner,
            token_hash="test-token-hash",
            expires_at=now - timedelta(days=1),
        )
    key = uuid4()
    values = dict(
        user_id=owner,
        idempotency_key=key,
        operation="create_exercise",
        request_hash="a" * 64,
        expires_at=now + timedelta(days=1),
    )
    add(conn, m.APIIdempotencyKey, **values)
    with rejected(conn, "uq_api_idempotency_keys"):
        add(conn, m.APIIdempotencyKey, **values)


def test_submitted_attempt_cannot_reopen(conn):
    eid, owner = exercise(conn)
    aid = attempt(conn, eid, owner)
    change(conn, m.WritingAttempt, aid, response_text="My response.")
    submit(conn, aid)
    with rejected(conn, "cannot return to draft"):
        change(conn, m.Attempt, aid, status="in_progress", current_stage="writing")


def test_missing_required_criterion_also_prevents_overall_score(conn):
    eid, owner = exercise(conn)
    aid = attempt(conn, eid, owner)
    change(conn, m.WritingAttempt, aid, response_text="My response.")
    submit(conn, aid)
    now = datetime.now(UTC)
    ev = add(
        conn,
        m.Evaluation,
        attempt_id=aid,
        rubric_version="v1",
        rubric_snapshot={"criteria": [{"code": "grammar", "required": True}]},
        status="completed",
        completed_at=now,
    )
    change(conn, m.Attempt, aid, status="completed", current_stage="results", completed_at=now)
    with rejected(conn, "unassessed required criterion"):
        change(conn, m.Evaluation, ev, overall_score=80, max_score=100)


def test_conversation_reply_must_target_same_session(conn):
    eid, owner = exercise(conn, "speaking")
    aid = attempt(conn, eid, owner, "speaking")
    other = attempt(conn, eid, owner, "speaking", number=2)
    sessions = dict(
        conn.execute(
            select(m.ConversationSession.attempt_id, m.ConversationSession.conversation_session_id)
        ).all()
    )
    first, second = sessions[aid], sessions[other]
    mid = add(
        conn,
        m.ConversationMessage,
        conversation_session_id=first,
        client_message_key=uuid4(),
        sender="user",
        position=1,
        transcription_status="pending",
    )
    change(conn, m.ConversationSession, first, next_position=2)
    change(conn, m.ConversationSession, second, next_position=3)
    with rejected(conn, "Invalid conversation reply"):
        add(
            conn,
            m.ConversationMessage,
            conversation_session_id=second,
            client_message_key=uuid4(),
            sender="assistant",
            position=1,
            reply_to_message_id=mid,
            transcription_status="not_applicable",
        )
    add(
        conn,
        m.ConversationMessage,
        conversation_session_id=second,
        client_message_key=uuid4(),
        sender="assistant",
        position=1,
        transcription_status="not_applicable",
    )
    with rejected(conn, "uq_conversation_messages_greeting"):
        add(
            conn,
            m.ConversationMessage,
            conversation_session_id=second,
            client_message_key=uuid4(),
            sender="assistant",
            position=2,
            transcription_status="not_applicable",
        )


def test_concurrent_voice_jobs_cannot_both_commit(engine):
    """Different messages bypass per-target uniqueness; the session rule must serialize them."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with engine.begin() as setup:
        eid, owner = exercise(setup, "speaking")
        aid = attempt(setup, eid, owner, "speaking")
        sid = setup.execute(
            select(m.ConversationSession.conversation_session_id).where(
                m.ConversationSession.attempt_id == aid
            )
        ).scalar_one()
        persona = setup.execute(
            select(m.SpeakingExercise.persona_id).where(m.SpeakingExercise.exercise_id == eid)
        ).scalar_one()
        messages = [
            add(
                setup,
                m.ConversationMessage,
                conversation_session_id=sid,
                client_message_key=uuid4(),
                sender="user",
                position=position,
                transcription_status="pending",
            )
            for position in (1, 2)
        ]
        change(setup, m.ConversationSession, sid, next_position=3)
    barrier = Barrier(2)

    def accept_turn(mid):
        try:
            with engine.begin() as concurrent:
                concurrent.execute(text("SET LOCAL statement_timeout = '5s'"))
                barrier.wait(timeout=5)
                add(
                    concurrent,
                    m.AIJob,
                    requested_by=owner,
                    message_id=mid,
                    job_type="process_voice_turn",
                    max_attempts=3,
                )
            return "committed"
        except IntegrityError as exc:
            assert "one active voice job" in str(exc)
            return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(accept_turn, messages))
        assert sorted(results) == ["committed", "rejected"]
    finally:
        # Remove only this test's committed fixtures in foreign-key dependency order.
        with engine.begin() as cleanup:
            for model, predicate in [
                (m.AIJob, m.AIJob.message_id.in_(messages)),
                (m.ConversationMessage, m.ConversationMessage.conversation_session_id == sid),
                (m.ConversationSession, m.ConversationSession.conversation_session_id == sid),
                (m.Attempt, m.Attempt.attempt_id == aid),
                (m.SpeakingExercise, m.SpeakingExercise.exercise_id == eid),
                (m.Exercise, m.Exercise.exercise_id == eid),
                (m.AIPersona, m.AIPersona.persona_id == persona),
                (m.User, m.User.user_id == owner),
            ]:
                cleanup.execute(delete(model).where(predicate))
