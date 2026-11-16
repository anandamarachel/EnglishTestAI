"""Attempt lifecycle shared by all skills; skill-specific steps are delegated.

Mutations lock the exercise row first (matching the
database triggers), then the attempt row, so concurrent saves/submits serialize.
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, validation_error
from app.modules.assessment import service as assessment
from app.modules.assessment.models import Evaluation
from app.modules.exercises import service as exercises
from app.modules.exercises.models import Exercise
from app.modules.jobs import service as jobs
from app.modules.listening import service as listening
from app.modules.listening.schemas import ListeningDraftOut
from app.modules.practice import service as read_models
from app.modules.practice.models import Attempt
from app.modules.practice.schemas import AttemptDetail, AttemptSummary, WritingDraftOut
from app.modules.quiz import service as quiz
from app.modules.quiz.models import Answer
from app.modules.reading import service as reading
from app.modules.reading.schemas import ReadingDraftOut
from app.modules.speaking import service as speaking
from app.modules.writing import service as writing


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Resource not found.")


def _state_conflict(message: str) -> ApiError:
    return ApiError(409, "STATE_CONFLICT", message)


async def lock_exercise_for_user(db: AsyncSession, user_id: UUID, exercise_id: UUID) -> Exercise:
    exercise = await db.scalar(
        select(Exercise)
        .where(Exercise.exercise_id == exercise_id, Exercise.created_by == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if exercise is None:
        raise _not_found()
    return exercise


async def lock_attempt(db: AsyncSession, user_id: UUID, attempt_id: UUID):
    exercise_id = await db.scalar(
        select(Attempt.exercise_id).where(
            Attempt.attempt_id == attempt_id, Attempt.user_id == user_id
        )
    )
    if exercise_id is None:
        raise _not_found()
    exercise = await lock_exercise_for_user(db, user_id, exercise_id)
    attempt = await db.scalar(
        select(Attempt)
        .where(Attempt.attempt_id == attempt_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return attempt, exercise


async def get_owned(db: AsyncSession, user_id: UUID, attempt_id: UUID) -> Attempt:
    attempt = await db.scalar(
        select(Attempt).where(Attempt.attempt_id == attempt_id, Attempt.user_id == user_id)
    )
    if attempt is None:
        raise _not_found()
    return attempt


async def summary(db: AsyncSession, attempt_id: UUID) -> AttemptSummary:
    return await read_models.summary_for_attempt(db, attempt_id)


async def create(
    db: AsyncSession, settings, user_id: UUID, exercise_id: UUID, source_attempt_id: UUID | None
):
    """Returns (attempt, job): Speaking also queues its greeting job."""
    exercise = await lock_exercise_for_user(db, user_id, exercise_id)
    if exercise.generation_status != "ready":
        raise _state_conflict("This exercise is not ready yet.")
    if exercise.skill == "writing":
        return await writing.start_attempt(db, user_id, exercise, source_attempt_id), None
    if source_attempt_id is not None:
        raise validation_error("source_attempt_id", "Only Writing attempts can copy a source.")
    if exercise.skill == "reading":
        return await reading.start_attempt(db, user_id, exercise), None
    if exercise.skill == "listening":
        return await listening.start_attempt(db, user_id, exercise), None
    return await speaking.start_attempt(db, settings, user_id, exercise)


def _check_revision(attempt: Attempt, revision: int) -> None:
    if attempt.revision != revision:
        raise ApiError(
            409,
            "REVISION_CONFLICT",
            "Reload the latest draft before saving.",
            extra={"current_revision": attempt.revision},
        )


async def save_draft(
    db: AsyncSession, user_id: UUID, attempt_id: UUID, revision: int, draft
) -> Attempt:
    attempt, exercise = await lock_attempt(db, user_id, attempt_id)
    if draft.skill != exercise.skill:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=[{"field": "draft.skill", "message": "Draft does not match this exercise."}],
        )
    if attempt.status != "in_progress":
        raise _state_conflict("This attempt can no longer be edited.")
    _check_revision(attempt, revision)
    if draft.skill == "writing":
        await writing.save_draft(db, attempt, draft.response_text)
    elif draft.skill == "reading":
        await reading.save_draft(db, attempt, draft)
    else:
        await listening.save_draft(db, attempt, draft)
    attempt.revision = Attempt.revision + 1
    attempt.last_saved_at = func.now()
    attempt.last_activity_at = func.now()
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def submit(db: AsyncSession, settings, user_id: UUID, attempt_id: UUID, revision: int):
    """Returns (attempt, job, evaluation): a queued job (AI) or a final evaluation."""
    attempt, exercise = await lock_attempt(db, user_id, attempt_id)
    if attempt.status != "in_progress":
        raise _state_conflict("This attempt has already been submitted or closed.")
    _check_revision(attempt, revision)
    if exercise.skill == "writing":
        return attempt, await writing.submit(db, settings, user_id, attempt), None
    if exercise.skill == "reading":
        return attempt, None, await reading.finish(db, attempt)
    if exercise.skill == "listening":
        job, evaluation = await listening.submit(db, settings, user_id, attempt)
        return attempt, job, evaluation
    raise _state_conflict("Speaking attempts are submitted with /finish.")


async def submit_answer(
    db: AsyncSession, settings, user_id: UUID, attempt_id: UUID, question_id: UUID, data
):
    """Reading per-question submit: checks and increments the attempt revision."""
    attempt, exercise = await lock_attempt(db, user_id, attempt_id)
    if exercise.skill != "reading":
        raise _state_conflict("Only Reading answers are submitted one at a time.")
    if attempt.status != "in_progress":
        raise _state_conflict("This attempt can no longer be changed.")
    _check_revision(attempt, data.revision)
    return await reading.submit_answer(
        db, settings, user_id, attempt, question_id, data.selected_option_id, data.response_text
    )


async def answer_feedback(db: AsyncSession, user_id: UUID, attempt_id: UUID, question_id: UUID):
    attempt = await get_owned(db, user_id, attempt_id)
    exercise = await db.get(Exercise, attempt.exercise_id)
    answer = await db.scalar(
        select(Answer).where(Answer.attempt_id == attempt_id, Answer.question_id == question_id)
    )
    if answer is None:
        raise _not_found()
    if not quiz.feedback_unlocked(exercise.skill, attempt, answer):
        raise quiz.locked_feedback_error(answer)
    return await quiz.feedback_out(db, answer)


async def cancel(db: AsyncSession, user_id: UUID, attempt_id: UUID) -> Attempt:
    attempt, exercise = await lock_attempt(db, user_id, attempt_id)
    if attempt.status == "completed":
        raise _state_conflict("Completed attempts cannot be cancelled.")
    if attempt.status == "cancelled":
        return attempt
    for active in await jobs.active_jobs_for_attempt(db, attempt.attempt_id):
        job = await jobs.lock_job(db, active.job_id)
        if job.status in ("queued", "running"):
            await jobs.cancel(db, job)
    await db.execute(
        update(Evaluation)
        .where(
            Evaluation.attempt_id == attempt.attempt_id,
            Evaluation.status.in_(("pending", "processing")),
        )
        .values(status="cancelled")
    )
    if exercise.skill == "speaking":
        await speaking.end_session(db, attempt.attempt_id)
    await db.execute(
        update(Attempt)
        .where(Attempt.attempt_id == attempt.attempt_id)
        .values(status="cancelled", last_activity_at=func.now())
    )
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def detail(db: AsyncSession, user_id: UUID, attempt_id: UUID) -> AttemptDetail:
    attempt = await get_owned(db, user_id, attempt_id)
    exercise = await db.get(Exercise, attempt.exercise_id)
    evaluation = await assessment.get_for_attempt(db, attempt_id)
    active = await jobs.active_jobs_for_attempt(db, attempt_id)
    if exercise.skill == "writing":
        draft = WritingDraftOut(
            skill="writing", response_text=await writing.draft_text(db, attempt_id)
        )
    elif exercise.skill == "reading":
        draft = ReadingDraftOut(**await reading.draft_out(db, attempt_id))
    elif exercise.skill == "listening":
        draft = ListeningDraftOut(**await listening.draft_out(db, attempt_id))
    else:
        draft = None
    answers = [
        quiz.answer_out(a, quiz.feedback_unlocked(exercise.skill, attempt, a))
        for a in await quiz.answers_for_attempt(db, attempt_id)
    ]
    return AttemptDetail(
        attempt=await summary(db, attempt_id),
        exercise=await exercises.to_out(db, exercise),
        draft=draft,
        answers=answers,
        conversation=await speaking.conversation_out(db, attempt_id),
        active_jobs=[await jobs.to_out(db, job) for job in active],
        evaluation=await assessment.to_out(db, evaluation) if evaluation else None,
    )
