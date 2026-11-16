"""Durable AI job lifecycle shared by the API and the worker.

Lock order everywhere: the job's exercise row first, then the job row. Database
triggers lock the exercise on every write to its descendants, so taking it first
avoids deadlocks between API requests and the worker.

Domain effects by job type:
- generate_exercise: cancel -> exercise cancelled; final failure -> exercise failed;
  retry -> exercise pending.
- evaluate_attempt: cancel -> evaluation cancelled, attempt failed (retryable, submission
  kept); final failure -> evaluation and attempt failed; retry -> evaluation pending,
  attempt submitted. A cancelled attempt never comes back.
- grade_answer: cancel -> answer cancelled; final failure -> answer failed; retry ->
  answer pending. Only while the attempt is still open; graded answers never change.
  Any outcome wakes a waiting Listening coordinator.

- start_conversation / process_voice_turn: cancel -> message cancelled; final failure ->
  message failed (a pending transcription too); retry -> message pending, only while the
  attempt and its session are open and no other voice job is active in that session.
  Ready messages never change.

Listening coordinator (evaluate_attempt over grade_answer children): its cancellation
cancels outstanding children; its retry requeues only failed/cancelled children and keeps
completed grades. Listening children are retried through the coordinator, not directly.
"""

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.modules.assessment.models import Evaluation
from app.modules.exercises.models import Exercise
from app.modules.jobs.models import AIJob
from app.modules.jobs.schemas import RESULT_REF_KEYS, JobError, JobOut, JobTarget
from app.modules.practice.models import Attempt
from app.modules.quiz.models import Answer
from app.modules.speaking.models import ConversationMessage, ConversationSession

ACTIVE = ("queued", "running", "cancel_requested")


def not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Resource not found.")


async def _message_attempt_id(db: AsyncSession, message_id: UUID) -> UUID | None:
    return await db.scalar(
        select(ConversationSession.attempt_id)
        .join(
            ConversationMessage,
            ConversationMessage.conversation_session_id
            == ConversationSession.conversation_session_id,
        )
        .where(ConversationMessage.message_id == message_id)
    )


async def _exercise_id(
    db: AsyncSession,
    exercise_id: UUID | None,
    attempt_id: UUID | None,
    answer_id: UUID | None,
    message_id: UUID | None = None,
) -> UUID | None:
    if exercise_id is not None:
        return exercise_id
    if answer_id is not None:
        attempt_id = await db.scalar(select(Answer.attempt_id).where(Answer.answer_id == answer_id))
    elif message_id is not None:
        attempt_id = await _message_attempt_id(db, message_id)
    return await db.scalar(select(Attempt.exercise_id).where(Attempt.attempt_id == attempt_id))


async def exercise_id_for(db: AsyncSession, job: AIJob) -> UUID:
    return await _exercise_id(db, job.exercise_id, job.attempt_id, job.answer_id, job.message_id)


async def attempt_id_for(db: AsyncSession, job: AIJob) -> UUID | None:
    if job.answer_id is not None:
        return await db.scalar(select(Answer.attempt_id).where(Answer.answer_id == job.answer_id))
    if job.message_id is not None:
        return await _message_attempt_id(db, job.message_id)
    return job.attempt_id


async def voice_message_id(db: AsyncSession, job: AIJob) -> UUID:
    """The message a voice job produces: the greeting, or the user turn it answers."""
    if job.job_type == "process_voice_turn":
        return job.message_id
    return await db.scalar(
        select(ConversationMessage.message_id)
        .join(
            ConversationSession,
            ConversationSession.conversation_session_id
            == ConversationMessage.conversation_session_id,
        )
        .where(
            ConversationSession.attempt_id == job.attempt_id,
            ConversationMessage.sender == "assistant",
            ConversationMessage.reply_to_message_id.is_(None),
        )
    )


async def lock_exercise(db: AsyncSession, exercise_id: UUID) -> None:
    await db.execute(
        select(Exercise.exercise_id).where(Exercise.exercise_id == exercise_id).with_for_update()
    )


async def lock_job(db: AsyncSession, job_id: UUID, user_id: UUID | None = None) -> AIJob:
    """Exercise lock, then job lock. Raises 404 if missing or not owned."""
    query = select(AIJob.exercise_id, AIJob.attempt_id, AIJob.answer_id, AIJob.message_id).where(
        AIJob.job_id == job_id
    )
    if user_id is not None:
        query = query.where(AIJob.requested_by == user_id)
    row = (await db.execute(query)).one_or_none()
    if row is None:
        raise not_found()
    exercise_id = await _exercise_id(
        db, row.exercise_id, row.attempt_id, row.answer_id, row.message_id
    )
    await lock_exercise(db, exercise_id)
    job = await db.scalar(
        select(AIJob)
        .where(AIJob.job_id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return job


async def enqueue(
    db: AsyncSession,
    *,
    requested_by: UUID,
    job_type: str,
    max_attempts: int,
    exercise_id: UUID | None = None,
    attempt_id: UUID | None = None,
    answer_id: UUID | None = None,
    message_id: UUID | None = None,
) -> AIJob:
    job = AIJob(
        requested_by=requested_by,
        job_type=job_type,
        max_attempts=max_attempts,
        exercise_id=exercise_id,
        attempt_id=attempt_id,
        answer_id=answer_id,
        message_id=message_id,
        status="queued",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


async def can_retry(db: AsyncSession, job: AIJob) -> bool:
    if job.status not in ("failed", "cancelled"):
        return False
    if job.job_type == "generate_exercise":
        status = await db.scalar(
            select(Exercise.generation_status).where(Exercise.exercise_id == job.exercise_id)
        )
        return status in ("failed", "cancelled")
    if job.job_type == "evaluate_attempt":
        status = await db.scalar(select(Attempt.status).where(Attempt.attempt_id == job.attempt_id))
        return status == "failed"
    if job.job_type == "grade_answer":
        row = (
            await db.execute(
                select(Answer.grading_status, Attempt.status, Exercise.skill)
                .join(Attempt, Attempt.attempt_id == Answer.attempt_id)
                .join(Exercise, Exercise.exercise_id == Attempt.exercise_id)
                .where(Answer.answer_id == job.answer_id)
            )
        ).one()
        if row.skill == "listening":
            return False  # retried with its coordinator
        return row[0] in ("failed", "cancelled") and row[1] not in ("cancelled", "completed")
    if job.job_type in VOICE_JOBS:
        return await _voice_retryable(db, job)
    return False


VOICE_JOBS = ("start_conversation", "process_voice_turn")


async def _voice_retryable(db: AsyncSession, job: AIJob) -> bool:
    message = await db.get(ConversationMessage, await voice_message_id(db, job))
    session = await db.get(ConversationSession, message.conversation_session_id)
    attempt_status = await db.scalar(
        select(Attempt.status).where(Attempt.attempt_id == session.attempt_id)
    )
    if message.delivery_status not in ("failed", "cancelled"):
        return False
    if attempt_status != "in_progress" or session.status == "ended":
        return False
    session_messages = select(ConversationMessage.message_id).where(
        ConversationMessage.conversation_session_id == session.conversation_session_id
    )
    busy = await db.scalar(
        select(func.count())
        .select_from(AIJob)
        .where(
            AIJob.status.in_(ACTIVE),
            AIJob.job_id != job.job_id,
            ((AIJob.job_type == "start_conversation") & (AIJob.attempt_id == session.attempt_id))
            | ((AIJob.job_type == "process_voice_turn") & AIJob.message_id.in_(session_messages)),
        )
    )
    return busy == 0


async def to_out(db: AsyncSession, job: AIJob) -> JobOut:
    retryable = await can_retry(db, job)
    target_type, target_id = next(
        (kind, value)
        for kind, value in (
            ("exercise", job.exercise_id),
            ("attempt", job.attempt_id),
            ("answer", job.answer_id),
            ("message", job.message_id),
        )
        if value is not None
    )
    refs = {k: UUID(str(v)) for k, v in (job.result_refs or {}).items() if k in RESULT_REF_KEYS}
    return JobOut(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        target=JobTarget(type=target_type, id=target_id),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=JobError(code=job.error_code or "FAILED", retryable=retryable)
        if job.status == "failed"
        else None,
        result_refs=refs,
        can_cancel=job.status in ("queued", "running"),
        can_retry=retryable,
    )


async def get_owned(db: AsyncSession, user_id: UUID, job_id: UUID) -> AIJob:
    job = await db.scalar(
        select(AIJob).where(AIJob.job_id == job_id, AIJob.requested_by == user_id)
    )
    if job is None:
        raise not_found()
    return job


async def active_jobs_for_attempt(db: AsyncSession, attempt_id: UUID) -> list[AIJob]:
    messages = (
        select(ConversationMessage.message_id)
        .join(
            ConversationSession,
            ConversationSession.conversation_session_id
            == ConversationMessage.conversation_session_id,
        )
        .where(ConversationSession.attempt_id == attempt_id)
    )
    return list(
        await db.scalars(
            select(AIJob)
            .where(
                (AIJob.attempt_id == attempt_id)
                | AIJob.answer_id.in_(
                    select(Answer.answer_id).where(Answer.attempt_id == attempt_id)
                )
                | AIJob.message_id.in_(messages),
                AIJob.status.in_(ACTIVE),
            )
            .order_by(AIJob.created_at)
        )
    )


# --- Transitions (caller holds the exercise and job locks and commits) -------------


async def cancel(db: AsyncSession, job: AIJob) -> int:
    """Returns 200 when cancelled now, 202 when a running execution must stop."""
    if job.status == "succeeded":
        raise ApiError(409, "ALREADY_COMPLETED", "This job has already completed.")
    if job.status in ("failed", "cancelled"):
        raise ApiError(409, "STATE_CONFLICT", "This job is not running.")
    if job.status == "cancel_requested":
        return 202
    if job.status == "queued":
        job.status = "cancelled"
        job.finished_at = func.now()
        job.next_retry_at = None
        code = 200
    else:  # running: invalidate the execution; its late result will be discarded.
        job.status = "cancel_requested"
        job.cancel_requested_at = func.now()
        job.execution_version = AIJob.execution_version + 1
        code = 202
    await _on_cancelled(db, job)
    return code


def _reset(job: AIJob) -> None:
    job.status = "queued"
    job.execution_version = AIJob.execution_version + 1
    job.attempt_count = 0
    job.error_code = None
    job.finished_at = None
    job.started_at = None
    job.next_retry_at = None
    job.lease_expires_at = None


async def retry(db: AsyncSession, job: AIJob) -> None:
    if not await can_retry(db, job):
        raise ApiError(409, "STATE_CONFLICT", "This job cannot be retried.")
    _reset(job)
    if job.job_type == "generate_exercise":
        await db.execute(
            update(Exercise)
            .where(Exercise.exercise_id == job.exercise_id)
            .values(generation_status="pending")
        )
    elif job.job_type == "evaluate_attempt":
        await _requeue_failed_children(db, job.attempt_id)
        await db.execute(
            update(Evaluation)
            .where(Evaluation.attempt_id == job.attempt_id)
            .values(status="pending", completed_at=None)
        )
        await db.execute(
            update(Attempt)
            .where(Attempt.attempt_id == job.attempt_id)
            .values(status="submitted", last_activity_at=func.now())
        )
    elif job.job_type == "grade_answer":
        await _set_grading(db, job.answer_id, "pending")
    elif job.job_type in VOICE_JOBS:
        await _set_delivery(db, job, "pending")


async def _child_jobs(db: AsyncSession, attempt_id: UUID, statuses: tuple[str, ...]):
    """Latest grade_answer job per answer of the attempt, locked, filtered by status."""
    latest = (
        select(AIJob.job_id)
        .join(Answer, Answer.answer_id == AIJob.answer_id)
        .where(Answer.attempt_id == attempt_id, AIJob.job_type == "grade_answer")
        .distinct(AIJob.answer_id)
        .order_by(AIJob.answer_id, AIJob.created_at.desc())
    )
    return list(
        await db.scalars(
            select(AIJob)
            .where(AIJob.job_id.in_(latest), AIJob.status.in_(statuses))
            .order_by(AIJob.job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


async def _requeue_failed_children(db: AsyncSession, attempt_id: UUID) -> None:
    """Graded answers are kept; only failed or cancelled grading runs again."""
    for child in await _child_jobs(db, attempt_id, ("failed", "cancelled")):
        _reset(child)
        await _set_grading(db, child.answer_id, "pending")


async def wake_coordinator(db: AsyncSession, attempt_id: UUID) -> None:
    """Make a waiting coordinator due now instead of at its next poll."""
    await db.execute(
        update(AIJob)
        .where(
            AIJob.attempt_id == attempt_id,
            AIJob.job_type == "evaluate_attempt",
            AIJob.status == "queued",
        )
        .values(next_retry_at=None)
    )


async def fail(db: AsyncSession, job: AIJob, error_code: str) -> None:
    job.status = "failed"
    job.error_code = error_code[:64]
    job.finished_at = func.now()
    job.lease_expires_at = None
    job.next_retry_at = None
    if job.job_type == "generate_exercise":
        await db.execute(
            update(Exercise)
            .where(Exercise.exercise_id == job.exercise_id)
            .values(generation_status="failed")
        )
    elif job.job_type == "evaluate_attempt":
        await _fail_evaluation(db, job.attempt_id, "failed")
    elif job.job_type == "grade_answer":
        await _set_grading(db, job.answer_id, "failed")
    elif job.job_type in VOICE_JOBS:
        await _set_delivery(db, job, "failed")


async def _on_cancelled(db: AsyncSession, job: AIJob) -> None:
    if job.job_type == "generate_exercise":
        await db.execute(
            update(Exercise)
            .where(Exercise.exercise_id == job.exercise_id)
            .values(generation_status="cancelled")
        )
    elif job.job_type == "evaluate_attempt":
        await _fail_evaluation(db, job.attempt_id, "cancelled")
        for child in await _child_jobs(db, job.attempt_id, ("queued", "running")):
            await cancel(db, child)
    elif job.job_type == "grade_answer":
        await _set_grading(db, job.answer_id, "cancelled")
    elif job.job_type in VOICE_JOBS:
        await _set_delivery(db, job, "cancelled")


async def _set_delivery(db: AsyncSession, job: AIJob, status: str) -> None:
    """Ready messages are final; a failed turn keeps its recording for history."""
    message_id = await voice_message_id(db, job)
    transcription = {"failed": "failed", "pending": "pending"}.get(status)
    values = {"delivery_status": status}
    await db.execute(
        update(ConversationMessage)
        .where(
            ConversationMessage.message_id == message_id,
            ConversationMessage.delivery_status != "ready",
        )
        .values(**values)
    )
    if transcription is not None:
        await db.execute(
            update(ConversationMessage)
            .where(
                ConversationMessage.message_id == message_id,
                ConversationMessage.sender == "user",
                ConversationMessage.delivery_status != "ready",
                ConversationMessage.transcription_status.in_(("pending", "failed")),
            )
            .values(transcription_status=transcription)
        )


async def _set_grading(db: AsyncSession, answer_id: UUID, status: str) -> None:
    # Graded answers are final; only unfinished grading changes state.
    await db.execute(
        update(Answer)
        .where(Answer.answer_id == answer_id, Answer.grading_status != "graded")
        .values(grading_status=status)
    )
    attempt_id = await db.scalar(select(Answer.attempt_id).where(Answer.answer_id == answer_id))
    await wake_coordinator(db, attempt_id)


async def _fail_evaluation(db: AsyncSession, attempt_id: UUID, evaluation_status: str) -> None:
    await db.execute(
        update(Evaluation)
        .where(
            Evaluation.attempt_id == attempt_id, Evaluation.status.in_(("pending", "processing"))
        )
        .values(status=evaluation_status)
    )
    await db.execute(
        update(Attempt)
        .where(Attempt.attempt_id == attempt_id, Attempt.status.in_(("submitted", "evaluating")))
        .values(status="failed", last_activity_at=func.now())
    )
