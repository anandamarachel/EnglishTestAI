from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

UserRole = Literal["student", "teacher"]
# Trimmed before length checks, so whitespace-only names are rejected.
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserOut(BaseModel):
    """Public profile. Built field by field; never includes hashes or tokens."""

    user_id: UUID
    email: str
    display_name: str
    user_role: UserRole
    created_at: datetime


class UpdateProfileRequest(StrictModel):
    display_name: DisplayName = Field(description="Only the display name can change.")
