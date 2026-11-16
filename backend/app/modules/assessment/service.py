from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import CriterionResult, Evaluation
from app.modules.assessment.schemas import CriterionOut, EvaluationOut, FeedbackPayload
from app.modules.quiz import service as quiz


def _num(value) -> float | None:
    return None if value is None else float(value)


async def get_for_attempt(db: AsyncSession, attempt_id: UUID) -> Evaluation | None:
    return await db.scalar(select(Evaluation).where(Evaluation.attempt_id == attempt_id))


async def to_out(db: AsyncSession, evaluation: Evaluation) -> EvaluationOut:
    order = [c["code"] for c in evaluation.rubric_snapshot.get("criteria", [])]
    rows = list(
        await db.scalars(
            select(CriterionResult).where(CriterionResult.evaluation_id == evaluation.evaluation_id)
        )
    )
    rows.sort(key=lambda r: order.index(r.criterion_code) if r.criterion_code in order else 99)
    payload = evaluation.feedback_payload or {}
    return EvaluationOut(
        evaluation_id=evaluation.evaluation_id,
        attempt_id=evaluation.attempt_id,
        status=evaluation.status,
        overall_score=_num(evaluation.overall_score),
        max_score=_num(evaluation.max_score),
        rubric_version=evaluation.rubric_version,
        summary=evaluation.summary,
        corrected_text=evaluation.corrected_text,
        feedback_payload=FeedbackPayload(
            corrections=payload.get("corrections", []),
            limitations=payload.get("limitations", []),
        ),
        criteria=[
            CriterionOut(
                criterion_code=r.criterion_code,
                assessment_status=r.assessment_status,
                score=_num(r.score),
                max_score=_num(r.max_score),
                feedback=r.feedback,
            )
            for r in rows
        ],
        quiz_summary=await quiz.quiz_summary(db, evaluation.attempt_id),
        created_at=evaluation.created_at,
        completed_at=evaluation.completed_at,
    )
