from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.modules.exercises.schemas import Difficulty, RandomTopic, Strict, TopicSelection
from app.modules.quiz.schemas import DraftAnswer, Span

QuestionType = Literal["multiple_choice", "short_answer"]


class CreateReadingExerciseRequest(Strict):
    difficulty: Difficulty
    topic: TopicSelection = Field(default_factory=lambda: RandomTopic(mode="random"))
    question_count: int = Field(default=5, ge=1)
    question_types: list[QuestionType] = Field(
        default_factory=lambda: ["multiple_choice"], min_length=1
    )
    requested_word_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _unique_types(self) -> CreateReadingExerciseRequest:
        if len(set(self.question_types)) != len(self.question_types):
            raise ValueError("question_types must not repeat")
        return self


class ReadingDraft(Strict):
    skill: Literal["reading"]
    paragraph_index: int = Field(ge=0)
    offset_in_paragraph: int = Field(ge=0)
    current_question_id: UUID | None
    answers: list[DraftAnswer] = Field(max_length=100)


class ReadingDraftOut(BaseModel):
    skill: Literal["reading"]
    paragraph_index: int
    offset_in_paragraph: int
    current_question_id: UUID | None
    answers: list[DraftAnswer]


class VocabularyItemOut(BaseModel):
    vocabulary_item_id: UUID
    word_or_phrase: str
    meaning: str
    example_sentence: str
    example_from_passage: str
    occurrences: list[Span]
    position: int


class VocabularyList(BaseModel):
    items: list[VocabularyItemOut]
