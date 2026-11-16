from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.quiz.schemas import QuizSummary


class Correction(BaseModel):
    correction_id: str
    start: int
    end: int
    original: str
    replacement: str
    category: Literal["grammar", "spelling", "vocabulary", "style"]
    title: str
    explanation: str
    example: str


class FeedbackPayload(BaseModel):
    schema_version: Literal[1] = 1
    corrections: list[Correction]
    limitations: list[str]


class CriterionOut(BaseModel):
    criterion_code: str
    assessment_status: Literal["assessed", "not_assessed"]
    score: float | None
    max_score: float | None
    feedback: str


class EvaluationOut(BaseModel):
    evaluation_id: UUID
    attempt_id: UUID
    status: Literal["pending", "processing", "completed", "failed", "cancelled"]
    overall_score: float | None
    max_score: float | None
    rubric_version: str
    summary: str | None
    corrected_text: str | None
    feedback_payload: FeedbackPayload
    criteria: list[CriterionOut]
    quiz_summary: QuizSummary | None = None
    created_at: datetime
    completed_at: datetime | None
