from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.assessment.schemas import EvaluationOut
from app.modules.exercises.schemas import ExerciseOut
from app.modules.jobs.schemas import JobOut
from app.modules.listening.schemas import ListeningDraft, ListeningDraftOut
from app.modules.quiz.schemas import AnswerOut
from app.modules.reading.schemas import ReadingDraft, ReadingDraftOut
from app.modules.speaking.schemas import ConversationOut
from app.modules.users.schemas import UserOut

Skill = Literal["writing", "reading", "listening", "speaking"]
AttemptStatus = Literal[
    "in_progress", "submitted", "evaluating", "completed", "failed", "cancelled"
]
AttemptStage = Literal[
    "writing", "reading", "quiz", "listening", "conversation", "evaluation", "results"
]


class Score(BaseModel):
    """Practice score only, not an official IELTS score."""

    value: float
    max: float


class AttemptSummary(BaseModel):
    attempt_id: UUID
    exercise_id: UUID
    skill: Skill
    title: str
    attempt_number: int
    source_attempt_id: UUID | None
    status: AttemptStatus
    current_stage: AttemptStage
    revision: int
    last_activity_at: datetime
    last_saved_at: datetime | None
    started_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None
    score: Score | None


class AttemptSummaryPage(BaseModel):
    items: list[AttemptSummary]
    next_cursor: str | None


class Dashboard(BaseModel):
    user: UserOut
    resume_attempt: AttemptSummary | None
    pending_attempts: list[AttemptSummary]
    has_more_pending: bool


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateAttemptRequest(Strict):
    # Writing only: copy the original text of one of your submitted attempts.
    source_attempt_id: UUID | None = None


class WritingDraft(Strict):
    skill: Literal["writing"]
    # No length limit: long drafts are saved as-is (the request size limit still applies).
    response_text: str


class SaveDraftRequest(Strict):
    revision: int = Field(ge=1)
    draft: Annotated[WritingDraft | ReadingDraft | ListeningDraft, Field(discriminator="skill")]


class SubmitAttemptRequest(Strict):
    revision: int = Field(ge=1)


class WritingDraftOut(BaseModel):
    skill: Literal["writing"]
    response_text: str


class SavedDraft(BaseModel):
    attempt_id: UUID
    revision: int
    last_saved_at: datetime
    last_activity_at: datetime


class CreateAttemptResult(BaseModel):
    attempt: AttemptSummary
    # Speaking only: the new conversation and its queued greeting job.
    conversation: ConversationOut | None = None
    job: JobOut | None = None


class AttemptQueuedResult(BaseModel):
    attempt: AttemptSummary
    job: JobOut


class AttemptResult(BaseModel):
    attempt: AttemptSummary


class AttemptGradedResult(BaseModel):
    attempt: AttemptSummary
    evaluation: EvaluationOut


class AttemptDetail(BaseModel):
    attempt: AttemptSummary
    exercise: ExerciseOut
    draft: WritingDraftOut | ReadingDraftOut | ListeningDraftOut | None
    answers: list[AnswerOut]
    conversation: ConversationOut | None = None
    active_jobs: list[JobOut]
    evaluation: EvaluationOut | None
