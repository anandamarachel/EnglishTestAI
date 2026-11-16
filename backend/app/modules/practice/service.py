"""Read models shared by the dashboard and history. History has no table of its own:
it is built from attempts, their exercise and (when completed) their evaluation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import validation_error
from app.core.pagination import decode_cursor, encode_cursor, scope_fingerprint
from app.modules.assessment.models import Evaluation
from app.modules.exercises.models import Exercise
from app.modules.practice.models import Attempt
from app.modules.practice.schemas import AttemptSummary, Score

# Waiting for an evaluation; shown on the dashboard separately from resumable drafts.
PENDING_STATUSES = ("submitted", "evaluating")
DASHBOARD_PENDING_LIMIT = 10


def _summary_query(user_id: UUID | None) -> Select:
    return (
        select(
            Attempt,
            Exercise.skill,
            Exercise.title,
            Evaluation.overall_score,
            Evaluation.max_score,
        )
        .join(Exercise, Exercise.exercise_id == Attempt.exercise_id)
        .outerjoin(
            Evaluation,
            and_(Evaluation.attempt_id == Attempt.attempt_id, Evaluation.status == "completed"),
        )
        .where(True if user_id is None else Attempt.user_id == user_id)
        .order_by(Attempt.last_activity_at.desc(), Attempt.attempt_id.desc())
    )


def _to_summary(row) -> AttemptSummary:
    attempt, skill, title, score, max_score = row
    return AttemptSummary(
        attempt_id=attempt.attempt_id,
        exercise_id=attempt.exercise_id,
        skill=skill,
        title=title or "",
        attempt_number=attempt.attempt_number,
        source_attempt_id=attempt.source_attempt_id,
        status=attempt.status,
        current_stage=attempt.current_stage,
        revision=attempt.revision,
        last_activity_at=attempt.last_activity_at,
        last_saved_at=attempt.last_saved_at,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        completed_at=attempt.completed_at,
        # Null until a completed evaluation has a valid score (unassessed criteria stay null).
        score=Score(value=float(score), max=float(max_score)) if score is not None else None,
    )


async def summary_for_attempt(db: AsyncSession, attempt_id: UUID) -> AttemptSummary:
    query = _summary_query(None).where(Attempt.attempt_id == attempt_id)
    return _to_summary((await db.execute(query)).one())


async def resume_attempt(db: AsyncSession, user_id: UUID) -> AttemptSummary | None:
    row = (
        await db.execute(_summary_query(user_id).where(Attempt.status == "in_progress").limit(1))
    ).first()
    return _to_summary(row) if row else None


async def pending_attempts(db: AsyncSession, user_id: UUID) -> tuple[list[AttemptSummary], bool]:
    query = _summary_query(user_id).where(Attempt.status.in_(PENDING_STATUSES))
    rows = (await db.execute(query.limit(DASHBOARD_PENDING_LIMIT + 1))).all()
    has_more = len(rows) > DASHBOARD_PENDING_LIMIT
    return [_to_summary(r) for r in rows[:DASHBOARD_PENDING_LIMIT]], has_more


async def list_attempts(
    db: AsyncSession,
    user_id: UUID,
    *,
    skill: str | None,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[AttemptSummary], str | None]:
    scope = scope_fingerprint("attempts", user_id, skill, status)
    query = _summary_query(user_id)
    if skill is not None:
        query = query.where(Exercise.skill == skill)
    if status is not None:
        query = query.where(Attempt.status == status)
    after = decode_cursor(cursor, scope, 2)
    if after is not None:
        try:
            last_activity, last_id = datetime.fromisoformat(after[0]), UUID(after[1])
        except ValueError, TypeError:
            raise validation_error("cursor", "Cursor is invalid.") from None
        query = query.where(
            tuple_(Attempt.last_activity_at, Attempt.attempt_id) < (last_activity, last_id)
        )
    rows = (await db.execute(query.limit(limit + 1))).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1][0]
        next_cursor = encode_cursor(
            scope, [last.last_activity_at.isoformat(), str(last.attempt_id)]
        )
    return [_to_summary(r) for r in rows], next_cursor
