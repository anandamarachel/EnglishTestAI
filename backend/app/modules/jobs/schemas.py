from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

JobType = Literal[
    "generate_exercise",
    "evaluate_attempt",
    "grade_answer",
    "start_conversation",
    "process_voice_turn",
]
JobStatus = Literal["queued", "running", "cancel_requested", "succeeded", "failed", "cancelled"]


class JobTarget(BaseModel):
    type: Literal["exercise", "attempt", "answer", "message"]
    id: UUID


class JobError(BaseModel):
    code: str
    retryable: bool


RESULT_REF_KEYS = (
    "exercise_id",
    "attempt_id",
    "answer_id",
    "evaluation_id",
    "message_id",
    "assistant_message_id",
)


class JobOut(BaseModel):
    job_id: UUID
    job_type: JobType
    status: JobStatus
    target: JobTarget
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: JobError | None
    # Allowlisted public IDs only (RESULT_REF_KEYS); absent keys are omitted, not null.
    result_refs: dict[str, UUID]
    can_cancel: bool
    can_retry: bool
