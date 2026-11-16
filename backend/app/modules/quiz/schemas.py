from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.jobs.schemas import JobOut

GradingStatus = Literal["pending", "processing", "graded", "failed", "cancelled"]


class Span(BaseModel):
    """Zero-based Unicode code points, end exclusive, against the stored source text."""

    start: int
    end: int
    original: str


class OptionOut(BaseModel):
    option_id: UUID
    option_text: str
    position: int


class QuestionOut(BaseModel):
    """No answer keys: is_correct, reference answers and explanations stay hidden."""

    question_id: UUID
    position: int
    question_type: Literal["multiple_choice", "short_answer"]
    question_text: str
    max_points: float
    options: list[OptionOut]


class AnswerOut(BaseModel):
    answer_id: UUID
    question_id: UUID
    selected_option_id: UUID | None
    response_text: str | None
    revision: int
    submitted_at: datetime | None
    grading_status: GradingStatus
    feedback_available: bool


class AnswerFeedbackOut(BaseModel):
    answer_id: UUID
    question_id: UUID
    grading_status: GradingStatus
    awarded_points: float | None
    max_points: float
    is_correct: bool | None
    correct_option_id: UUID | None
    reference_answer: str | None
    explanation: str | None
    evidence_spans: list[Span]


class QuizSummary(BaseModel):
    question_count: int
    graded_count: int
    correct_count: int | None
    awarded_points: float
    max_points: float


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DraftAnswer(Strict):
    """Both null clears an unlocked answer; otherwise exactly one matching the type."""

    question_id: UUID
    selected_option_id: UUID | None
    response_text: str | None

    @model_validator(mode="after")
    def _one_format(self) -> DraftAnswer:
        if self.selected_option_id is not None and self.response_text is not None:
            raise ValueError("Give either selected_option_id or response_text, not both.")
        return self


class SubmitAnswerRequest(Strict):
    revision: int = Field(ge=1)  # the attempt revision
    selected_option_id: UUID | None = None
    response_text: Annotated[str, StringConstraints(min_length=1, pattern=r"\S")] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> SubmitAnswerRequest:
        if (self.selected_option_id is None) == (self.response_text is None):
            raise ValueError("Give exactly one of selected_option_id or response_text.")
        return self


class AnswerGradedResult(BaseModel):
    answer: AnswerOut
    feedback: AnswerFeedbackOut
    attempt_revision: int


class AnswerQueuedResult(BaseModel):
    answer: AnswerOut
    job: JobOut
    attempt_revision: int
