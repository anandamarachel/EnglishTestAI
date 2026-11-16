"""Typed requests and results exchanged with any AI provider.

Results are untrusted: providers return these shapes, and the domain validates them
again (spans, score ranges, criterion codes) before anything is persisted.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WritingPromptRequest(Contract):
    topic: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    cefr_level: Literal["A2", "B1", "B2"]
    target_word_count: int | None


class WritingPrompt(Contract):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=4_000)


class RubricCriterion(Contract):
    code: str
    name: str
    descriptor: str


class WritingEvaluationRequest(Contract):
    title: str
    instructions: str
    cefr_level: Literal["A2", "B1", "B2"]
    target_word_count: int | None
    response_text: str
    criteria: list[RubricCriterion]
    score_min: float
    score_max: float
    score_step: float


class CorrectionResult(Contract):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    original: str
    replacement: str
    category: Literal["grammar", "spelling", "vocabulary", "style"]
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=2_000)
    example: str = Field(max_length=1_000)


class CriterionScore(Contract):
    code: str
    score: float
    feedback: str = Field(min_length=1, max_length=2_000)


class WritingEvaluation(Contract):
    summary: str = Field(min_length=1, max_length=4_000)
    corrected_text: str
    criteria: list[CriterionScore]
    corrections: list[CorrectionResult]


# --- Reading -------------------------------------------------------------------------

QuestionKind = Literal["multiple_choice", "short_answer"]


class ReadingRequest(Contract):
    topic: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    cefr_level: Literal["A2", "B1", "B2"]
    target_word_count: int
    # One entry per question, in order; the result must match it exactly.
    question_types: list[QuestionKind]
    vocabulary_count: int


class GeneratedQuestion(Contract):
    question_type: QuestionKind
    question_text: str = Field(min_length=1, max_length=1_000)
    options: list[str] = Field(default_factory=list, max_length=6)  # multiple choice only
    correct_option: int | None = None  # index into options; multiple choice only
    reference_answer: str | None = Field(default=None, max_length=1_000)  # short answer only
    explanation: str = Field(min_length=1, max_length=2_000)
    # Exact quotes copied from the passage; the backend locates their offsets.
    evidence_quotes: list[str] = Field(min_length=1, max_length=5)


class GeneratedVocabulary(Contract):
    word_or_phrase: str = Field(min_length=1, max_length=200)
    meaning: str = Field(min_length=1, max_length=500)
    example_sentence: str = Field(min_length=1, max_length=500)


class ReadingPackage(Contract):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=2_000)
    passage: str = Field(min_length=1, max_length=20_000)
    questions: list[GeneratedQuestion]
    vocabulary: list[GeneratedVocabulary]


class ShortAnswerGradeRequest(Contract):
    question_text: str
    reference_answer: str
    evidence: list[str]
    response_text: str
    max_points: float
    point_step: float
    rubric: str


class ShortAnswerGrade(Contract):
    awarded_points: float = Field(ge=0)
    feedback: str = Field(min_length=1, max_length=2_000)


# --- Listening and speech -----------------------------------------------------------------


class ListeningRequest(Contract):
    topic: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    cefr_level: Literal["A2", "B1", "B2"]
    target_word_count: int
    question_types: list[QuestionKind]
    # Abstract voice keys the script may use; the TTS adapter maps them to real voices.
    voices: list[str]


class ScriptLine(Contract):
    speaker: str = Field(min_length=1, max_length=40)
    voice: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=2_000)


class ListeningPackage(Contract):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=2_000)
    lines: list[ScriptLine] = Field(min_length=1, max_length=80)
    # evidence_quotes are exact quotes from the transcript ("Speaker: text" lines).
    questions: list[GeneratedQuestion]


class SpeechSegment(Contract):
    voice: str
    text: str


class SpeechRequest(Contract):
    segments: list[SpeechSegment] = Field(min_length=1)


class SpeechAudio(Contract):
    # Untrusted: the backend checks the bytes themselves before storing them.
    audio: bytes


# --- Speaking ------------------------------------------------------------------------------


class SpeakingPromptRequest(Contract):
    topic: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    cefr_level: Literal["A2", "B1", "B2"]
    persona_name: str
    persona_role: str


class SpeakingPrompt(Contract):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=2_000)


class ConversationTurn(Contract):
    sender: Literal["user", "assistant"]
    text: str


class ConversationRequest(Contract):
    persona_name: str
    persona_role: str
    behavior_instructions: str
    topic: str
    title: str
    instructions: str
    cefr_level: Literal["A2", "B1", "B2"]
    # Successful messages only, oldest first. Empty history asks for the opening greeting.
    history: list[ConversationTurn]


class ConversationReply(Contract):
    text: str = Field(min_length=1, max_length=4_000)


class TranscriptionRequest(Contract):
    audio: bytes
    mime_type: str
    language: Literal["en"] = "en"


class Transcription(Contract):
    # Final transcript only; may be empty when no speech was detected.
    text: str = Field(max_length=20_000)


class SpeakingCriterion(Contract):
    code: str
    name: str
    descriptor: str
    # Needs the recordings themselves (e.g. pronunciation); never judged from text alone.
    requires_audio: bool


class SpeakingEvaluationRequest(Contract):
    title: str
    instructions: str
    cefr_level: Literal["A2", "B1", "B2"]
    turns: list[ConversationTurn]
    # The student's original recordings, in order. Empty unless the engine assesses audio.
    recordings: list[bytes]
    criteria: list[SpeakingCriterion]
    score_min: float
    score_max: float
    score_step: float


class SpeakingCriterionResult(Contract):
    code: str
    assessed: bool
    score: float | None = None
    feedback: str = Field(min_length=1, max_length=2_000)


class SpeakingEvaluation(Contract):
    summary: str = Field(min_length=1, max_length=4_000)
    criteria: list[SpeakingCriterionResult]
