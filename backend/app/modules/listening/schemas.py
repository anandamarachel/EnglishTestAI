from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.exercises.schemas import Difficulty, RandomTopic, Strict, TopicSelection
from app.modules.quiz.schemas import DraftAnswer, Span

QuestionType = Literal["multiple_choice", "short_answer"]


class CreateListeningExerciseRequest(Strict):
    difficulty: Difficulty
    topic: TopicSelection = Field(default_factory=lambda: RandomTopic(mode="random"))
    question_count: int = Field(default=3, ge=1)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: ["multiple_choice"], min_length=1
    )

    @model_validator(mode="after")
    def _unique_types(self) -> CreateListeningExerciseRequest:
        if len(set(self.question_types)) != len(self.question_types):
            raise ValueError("question_types must not repeat")
        return self


class ListeningDraft(Strict):
    skill: Literal["listening"]
    playback_position_ms: int = Field(ge=0)
    current_question_id: UUID | None
    answers: list[DraftAnswer] = Field(max_length=100)


class ListeningDraftOut(BaseModel):
    skill: Literal["listening"]
    playback_position_ms: int
    current_question_id: UUID | None
    answers: list[DraftAnswer]


class TranscriptEvidence(BaseModel):
    question_id: UUID
    spans: list[Span]


class TranscriptOut(BaseModel):
    exercise_id: UUID
    transcript: str
    # Only for graded questions: may be empty while short answers are being checked.
    evidence: list[TranscriptEvidence]
