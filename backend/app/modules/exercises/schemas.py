from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.jobs.schemas import JobOut
from app.modules.media.schemas import MediaOut
from app.modules.quiz.schemas import QuestionOut

Difficulty = Literal["beginner", "intermediate", "advanced"]
CEFR_FOR_DIFFICULTY = {"beginner": "A2", "intermediate": "B1", "advanced": "B2"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogTopic(Strict):
    mode: Literal["catalog"]
    topic_id: UUID


class CustomTopic(Strict):
    mode: Literal["custom"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class RandomTopic(Strict):
    mode: Literal["random"]


TopicSelection = Annotated[CatalogTopic | CustomTopic | RandomTopic, Field(discriminator="mode")]


class CreateWritingExerciseRequest(Strict):
    difficulty: Difficulty
    topic: TopicSelection = Field(default_factory=lambda: RandomTopic(mode="random"))
    # Learning target only; it never limits how much the student may write.
    target_word_count: int | None = Field(default=None, ge=1, le=10_000)


class CreateExerciseResult(BaseModel):
    exercise_id: UUID
    job: JobOut


class ExerciseTopic(BaseModel):
    mode: Literal["catalog", "custom", "random"]
    topic_id: UUID | None
    name: str | None


class WritingContent(BaseModel):
    target_word_count: int | None
    rubric_version: str


class ExerciseBase(BaseModel):
    """Public view: no rubric prompts, answer keys, generator details or internal config."""

    exercise_id: UUID
    difficulty: Difficulty
    content_cefr_level: Literal["A2", "B1", "B2"]
    topic: ExerciseTopic
    title: str | None
    instructions: str | None
    generation_status: Literal["pending", "generating", "ready", "failed", "cancelled"]
    created_at: datetime


class WritingExerciseOut(ExerciseBase):
    skill: Literal["writing"]
    content: WritingContent | None
    questions: list[QuestionOut] = Field(default_factory=list)


class ReadingContent(BaseModel):
    passage: str
    requested_word_count: int | None
    question_count: int
    feedback_mode: Literal["per_question"]


class ReadingExerciseOut(ExerciseBase):
    skill: Literal["reading"]
    content: ReadingContent | None
    questions: list[QuestionOut]


class ListeningContent(BaseModel):
    # The transcript is never part of this view; it unlocks after submission.
    audio: MediaOut
    question_count: int
    feedback_mode: Literal["after_submission"]
    transcript_policy: Literal["after_submission"]


class ListeningExerciseOut(ExerciseBase):
    skill: Literal["listening"]
    content: ListeningContent | None
    questions: list[QuestionOut]


class PersonaSummary(BaseModel):
    # Public fields only; behaviour instructions are never returned.
    persona_id: UUID
    name: str
    role_description: str


class SpeakingContent(BaseModel):
    persona: PersonaSummary
    rubric_version: str


class SpeakingExerciseOut(ExerciseBase):
    skill: Literal["speaking"]
    content: SpeakingContent | None
    questions: list[QuestionOut] = Field(default_factory=list)


ExerciseOut = Annotated[
    WritingExerciseOut | ReadingExerciseOut | ListeningExerciseOut | SpeakingExerciseOut,
    Field(discriminator="skill"),
]
