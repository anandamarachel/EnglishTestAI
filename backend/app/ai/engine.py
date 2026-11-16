from typing import Protocol

from app.ai.contracts import (
    ConversationReply,
    ConversationRequest,
    ListeningPackage,
    ListeningRequest,
    ReadingPackage,
    ReadingRequest,
    ShortAnswerGrade,
    ShortAnswerGradeRequest,
    SpeakingEvaluation,
    SpeakingEvaluationRequest,
    SpeakingPrompt,
    SpeakingPromptRequest,
    SpeechAudio,
    SpeechRequest,
    Transcription,
    TranscriptionRequest,
    WritingEvaluation,
    WritingEvaluationRequest,
    WritingPrompt,
    WritingPromptRequest,
)


class AIError(Exception):
    """Failure from a provider. code is safe to store and show; never provider text."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class AIEngine(Protocol):
    """One implementation per provider (fake, local PC over tunnel, external API...)."""

    name: str  # recorded as generator/model version; never a secret
    is_fake: bool
    # True only for an engine with a verified audio assessor (pronunciation, fluency).
    # Without it those criteria stay not_assessed; transcripts never stand in for audio.
    assesses_audio: bool

    async def generate_writing_prompt(self, request: WritingPromptRequest) -> WritingPrompt: ...

    async def evaluate_writing(self, request: WritingEvaluationRequest) -> WritingEvaluation: ...

    async def generate_reading(self, request: ReadingRequest) -> ReadingPackage: ...

    async def grade_short_answer(self, request: ShortAnswerGradeRequest) -> ShortAnswerGrade: ...

    async def generate_listening(self, request: ListeningRequest) -> ListeningPackage: ...

    async def synthesize_speech(self, request: SpeechRequest) -> SpeechAudio: ...

    async def generate_speaking_prompt(self, request: SpeakingPromptRequest) -> SpeakingPrompt: ...

    async def converse(self, request: ConversationRequest) -> ConversationReply: ...

    async def transcribe(self, request: TranscriptionRequest) -> Transcription: ...

    async def evaluate_speaking(self, request: SpeakingEvaluationRequest) -> SpeakingEvaluation: ...
