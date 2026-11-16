"""Listening: script + TTS generation, whole-quiz submission and the grading coordinator.

Generation is one job: the model writes a script and questions, the TTS engine renders
the script, and the audio bytes are validated and stored privately before anything is
published. The exercise only becomes ready together with its ready, owned audio.

Submission locks every answer at once. Multiple choice is graded on the spot; each short
answer gets a grade_answer job, and one evaluate_attempt job (the coordinator) waits for
them and stores the aggregate. The coordinator never grades anything itself.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import ListeningPackage, ListeningRequest, SpeechRequest, SpeechSegment
from app.ai.engine import AIEngine, AIError
from app.core.config import Settings
from app.core.errors import ApiError, validation_error
from app.modules.assessment.models import Evaluation
from app.modules.exercises import service as exercises
from app.modules.exercises.models import Exercise
from app.modules.exercises.schemas import CEFR_FOR_DIFFICULTY
from app.modules.jobs import service as jobs
from app.modules.jobs.models import AIJob
from app.modules.listening.models import ListeningAttempt, ListeningExercise
from app.modules.listening.schemas import (
    CreateListeningExerciseRequest,
    ListeningDraft,
    TranscriptEvidence,
    TranscriptOut,
)
from app.modules.media import service as media
from app.modules.media.audio import AudioInfo, InvalidAudio, inspect_wav
from app.modules.media.models import MediaAsset
from app.modules.media.storage import MediaStore
from app.modules.practice.models import Attempt
from app.modules.quiz import service as quiz
from app.modules.quiz.models import Answer, Question

DEFAULT_WORDS = {"beginner": 80, "intermediate": 120, "advanced": 180}
MAX_SPEAKERS = 4
QUIZ_RUBRIC_VERSION = "listening-quiz-v1"
QUIZ_RUBRIC = {
    "version": QUIZ_RUBRIC_VERSION,
    "scoring": "sum(awarded_points) / sum(max_points) * 100 once every question is graded",
    "criteria": [],
}


# --- Exercise creation -------------------------------------------------------------------


def plan(settings: Settings, data: CreateListeningExerciseRequest) -> tuple[list[str], int]:
    count = data.question_count
    if count > settings.listening_max_questions:
        raise ApiError(
            413,
            "CAPACITY_EXCEEDED",
            f"At most {settings.listening_max_questions} questions can be generated.",
        )
    minimum = count * settings.listening_min_words_per_question
    if minimum > settings.listening_max_word_count:
        raise ApiError(413, "CAPACITY_EXCEEDED", "That many questions do not fit in one recording.")
    target = min(max(DEFAULT_WORDS[data.difficulty], minimum), settings.listening_max_word_count)
    types = [data.question_types[i % len(data.question_types)] for i in range(count)]
    return types, target


async def create_exercise(
    db: AsyncSession, settings: Settings, user_id: UUID, data: CreateListeningExerciseRequest
) -> tuple[Exercise, AIJob]:
    types, target = plan(settings, data)
    await exercises.check_generation_capacity(db, settings, user_id)
    topic_id, custom_topic = await exercises.resolve_topic_choice(db, data.topic)
    exercise = Exercise(
        created_by=user_id,
        topic_selection=data.topic.mode,
        topic_id=topic_id,
        custom_topic=custom_topic,
        skill="listening",
        difficulty=data.difficulty,
        content_cefr_level=CEFR_FOR_DIFFICULTY[data.difficulty],
        content_source="ai",
        generation_status="pending",
        generation_config={"question_types": types, "target_word_count": target},
    )
    db.add(exercise)
    await db.flush()
    job = await jobs.enqueue(
        db,
        requested_by=user_id,
        job_type="generate_exercise",
        max_attempts=settings.job_max_attempts,
        exercise_id=exercise.exercise_id,
    )
    return exercise, job


# --- Generation job -------------------------------------------------------------------------


@dataclass(frozen=True)
class GenerationInput:
    exercise_id: UUID
    owner_id: UUID
    topic_id: UUID | None
    tolerance: float
    max_audio_bytes: int
    max_audio_duration_ms: int
    request: ListeningRequest


@dataclass(frozen=True)
class GeneratedListening:
    package: ListeningPackage
    transcript: str
    evidence: list[list[dict]]
    storage_key: str
    audio: AudioInfo


async def prepare_generation(db: AsyncSession, job: AIJob, settings: Settings) -> GenerationInput:
    exercise = await db.get(Exercise, job.exercise_id)
    topic_id, topic_name = await exercises.resolve_generation_topic(db, exercise)
    config = exercise.generation_config
    exercise.generation_status = "generating"
    return GenerationInput(
        exercise_id=exercise.exercise_id,
        owner_id=exercise.created_by,
        topic_id=topic_id,
        tolerance=settings.listening_word_count_tolerance,
        max_audio_bytes=settings.tts_max_audio_bytes,
        max_audio_duration_ms=settings.tts_max_audio_duration_ms,
        request=ListeningRequest(
            topic=topic_name,
            difficulty=exercise.difficulty,
            cefr_level=exercise.content_cefr_level,
            target_word_count=config["target_word_count"],
            question_types=config["question_types"],
            voices=settings.listening_voices,
        ),
    )


def transcript_of(package: ListeningPackage) -> str:
    return "\n".join(f"{line.speaker.strip()}: {line.text.strip()}" for line in package.lines)


def validate_package(data: GenerationInput, package: ListeningPackage) -> tuple[str, list]:
    """Untrusted model output: speakers, voices, length, question types, keys and quotes."""
    request = data.request
    if not package.title.strip() or not package.instructions.strip():
        raise quiz.invalid_output()
    voice_of: dict[str, str] = {}
    for line in package.lines:
        speaker, text = line.speaker.strip(), line.text.strip()
        if not speaker or not text or ":" in speaker or "\n" in speaker or "\n" in text:
            raise quiz.invalid_output()
        if (
            line.voice not in request.voices
            or voice_of.setdefault(speaker, line.voice) != line.voice
        ):
            raise quiz.invalid_output()
    if len(voice_of) > MAX_SPEAKERS:
        raise quiz.invalid_output()
    words = sum(len(line.text.split()) for line in package.lines)
    if abs(words - request.target_word_count) > data.tolerance * request.target_word_count:
        raise quiz.invalid_output()
    if [q.question_type for q in package.questions] != request.question_types:
        raise quiz.invalid_output()
    transcript = transcript_of(package)
    return transcript, [quiz.check_question(q, transcript) for q in package.questions]


async def execute_generation(
    engine: AIEngine, data: GenerationInput, *, store: MediaStore
) -> GeneratedListening:
    package = await engine.generate_listening(data.request)
    transcript, evidence = validate_package(data, package)
    speech = await engine.synthesize_speech(
        SpeechRequest(
            segments=[
                SpeechSegment(voice=line.voice, text=line.text.strip()) for line in package.lines
            ]
        )
    )
    try:
        info = inspect_wav(
            speech.audio,
            max_bytes=data.max_audio_bytes,
            max_duration_ms=data.max_audio_duration_ms,
        )
    except InvalidAudio:
        raise AIError("TTS_OUTPUT_INVALID", retryable=True) from None
    key = store.new_key("listening_audio", info.extension)
    await asyncio.to_thread(store.write, key, speech.audio)
    return GeneratedListening(package, transcript, evidence, key, info)


def discard_generation(result: GeneratedListening, *, store: MediaStore) -> None:
    """The result was not published (cancelled, superseded or rejected): drop its file."""
    store.delete(result.storage_key)


async def publish_generation(
    db: AsyncSession, engine: AIEngine, data: GenerationInput, result: GeneratedListening
) -> dict:
    audio = MediaAsset(
        owner_user_id=data.owner_id,
        storage_key=result.storage_key,
        purpose="listening_audio",
        mime_type=result.audio.mime_type,
        size_bytes=result.audio.size_bytes,
        duration_ms=result.audio.duration_ms,
        status="ready",
    )
    db.add(audio)
    await db.flush()
    db.add(
        ListeningExercise(
            exercise_id=data.exercise_id,
            audio_media_id=audio.media_id,
            transcript=result.transcript,
            question_count=len(result.package.questions),
        )
    )
    await quiz.add_questions(db, data.exercise_id, result.package.questions, result.evidence)
    await db.execute(
        update(Exercise)
        .where(Exercise.exercise_id == data.exercise_id)
        .values(
            title=result.package.title.strip(),
            instructions=result.package.instructions.strip(),
            topic_id=data.topic_id,
            generation_status="ready",
            generator_version=engine.name,
        )
    )
    return {"exercise_id": data.exercise_id}


# --- Attempts ------------------------------------------------------------------------------


async def _audio(db: AsyncSession, exercise_id: UUID) -> MediaAsset:
    detail = await db.get(ListeningExercise, exercise_id)
    return await db.get(MediaAsset, detail.audio_media_id)


async def start_attempt(db: AsyncSession, user_id: UUID, exercise: Exercise) -> Attempt:
    if not media.is_available(await _audio(db, exercise.exercise_id)):
        raise ApiError(
            409, "MEDIA_UNAVAILABLE", "The audio for this exercise is no longer available."
        )
    attempt = Attempt(
        user_id=user_id,
        exercise_id=exercise.exercise_id,
        attempt_number=await exercises.next_attempt_number(db, user_id, exercise.exercise_id),
        current_stage="listening",
        status="in_progress",
    )
    db.add(attempt)
    await db.flush()
    db.add(ListeningAttempt(attempt_id=attempt.attempt_id))
    for question in await quiz.questions(db, exercise.exercise_id):
        db.add(Answer(attempt_id=attempt.attempt_id, question_id=question.question_id))
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def save_draft(db: AsyncSession, attempt: Attempt, draft: ListeningDraft) -> None:
    """Free navigation: any question may be current; nothing is locked before submit."""
    audio = await _audio(db, attempt.exercise_id)
    if audio.duration_ms is not None and draft.playback_position_ms > audio.duration_ms:
        raise validation_error("draft.playback_position_ms", "Position is beyond the audio.")
    await quiz.apply_draft_answers(db, attempt.attempt_id, attempt.exercise_id, draft.answers)
    if draft.current_question_id is not None:
        exists = await db.scalar(
            select(Question.question_id).where(
                Question.question_id == draft.current_question_id,
                Question.exercise_id == attempt.exercise_id,
            )
        )
        if exists is None:
            raise validation_error("draft.current_question_id", "Question is not in this quiz.")
    await db.execute(
        update(ListeningAttempt)
        .where(ListeningAttempt.attempt_id == attempt.attempt_id)
        .values(
            playback_position_ms=draft.playback_position_ms,
            current_question_id=draft.current_question_id,
        )
    )
    attempt.current_stage = "quiz" if draft.current_question_id else "listening"


def _is_blank(answer: Answer) -> bool:
    return answer.selected_option_id is None and not (answer.response_text or "").strip()


async def submit(
    db: AsyncSession, settings: Settings, user_id: UUID, attempt: Attempt
) -> tuple[AIJob | None, Evaluation | None]:
    """Locks every saved answer together. All multiple choice: final result now.
    Otherwise: one grading job per short answer plus the coordinator."""
    answers = await quiz.answers_for_attempt(db, attempt.attempt_id)
    missing = [a for a in answers if _is_blank(a)]
    if missing:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "Answer every question before submitting.",
            details=[
                {"field": f"answers.{a.question_id}", "message": "Answer this question."}
                for a in missing
            ],
        )
    children = []
    for saved in answers:
        answer, question = await quiz.lock_answer_for_submission(
            db,
            attempt.attempt_id,
            attempt.exercise_id,
            saved.question_id,
            saved.selected_option_id,
            saved.response_text,
        )
        if question.grading_method == "answer_key":
            await quiz.grade_choice(db, answer, question)
        else:
            children.append(answer)
    attempt.status = "submitted"
    attempt.submitted_at = func.now()
    attempt.current_stage = "evaluation"
    attempt.last_activity_at = func.now()
    attempt.revision = attempt.revision + 1
    evaluation = Evaluation(
        attempt_id=attempt.attempt_id,
        status="pending",
        rubric_version=QUIZ_RUBRIC_VERSION,
        rubric_snapshot=QUIZ_RUBRIC,
    )
    db.add(evaluation)
    await db.flush()
    if not children:
        quiz.complete(attempt, evaluation, await quiz.quiz_summary(db, attempt.attempt_id))
        await db.flush()
        await db.refresh(evaluation)
        return None, evaluation
    for answer in children:
        await jobs.enqueue(
            db,
            requested_by=user_id,
            job_type="grade_answer",
            max_attempts=settings.job_max_attempts,
            answer_id=answer.answer_id,
        )
    coordinator = await jobs.enqueue(
        db,
        requested_by=user_id,
        job_type="evaluate_attempt",
        max_attempts=settings.job_max_attempts,
        attempt_id=attempt.attempt_id,
    )
    return coordinator, None


# --- Coordinator job (evaluate_attempt) ------------------------------------------------------


async def _grading_statuses(db: AsyncSession, attempt_id: UUID) -> list[str]:
    return list(
        await db.scalars(select(Answer.grading_status).where(Answer.attempt_id == attempt_id))
    )


async def coordinator_ready(db: AsyncSession, job: AIJob) -> bool:
    """False while any grade is still pending; the worker then defers the coordinator."""
    statuses = await _grading_statuses(db, job.attempt_id)
    return not any(s in ("pending", "processing") for s in statuses)


@dataclass(frozen=True)
class CoordinationInput:
    attempt_id: UUID


async def prepare_coordination(db: AsyncSession, job: AIJob) -> CoordinationInput:
    statuses = await _grading_statuses(db, job.attempt_id)
    if any(s in ("failed", "cancelled") for s in statuses):
        # Retrying the coordinator requeues only the failed grades.
        raise AIError("GRADING_FAILED", retryable=False)
    await db.execute(
        update(Evaluation)
        .where(Evaluation.attempt_id == job.attempt_id)
        .values(status="processing")
    )
    await db.execute(
        update(Attempt).where(Attempt.attempt_id == job.attempt_id).values(status="evaluating")
    )
    return CoordinationInput(job.attempt_id)


async def execute_coordination(engine: AIEngine, data: CoordinationInput) -> None:
    return None  # no model call: the grades already exist


async def publish_coordination(
    db: AsyncSession, engine: AIEngine, data: CoordinationInput, _: None
) -> dict:
    summary = await quiz.quiz_summary(db, data.attempt_id)
    if summary is None:  # a grade changed since prepare (e.g. cancelled)
        raise AIError("GRADING_FAILED", retryable=False)
    attempt = await db.scalar(
        select(Attempt)
        .where(Attempt.attempt_id == data.attempt_id)
        .execution_options(populate_existing=True)
    )
    evaluation = await db.scalar(
        select(Evaluation)
        .where(Evaluation.attempt_id == data.attempt_id)
        .execution_options(populate_existing=True)
    )
    quiz.complete(attempt, evaluation, summary)
    return {"attempt_id": data.attempt_id, "evaluation_id": evaluation.evaluation_id}


# --- Read models ---------------------------------------------------------------------------


async def draft_out(db: AsyncSession, attempt_id: UUID) -> dict:
    progress = await db.get(ListeningAttempt, attempt_id)
    return {
        "skill": "listening",
        "playback_position_ms": progress.playback_position_ms,
        "current_question_id": progress.current_question_id,
        "answers": [
            {
                "question_id": a.question_id,
                "selected_option_id": a.selected_option_id,
                "response_text": a.response_text,
            }
            for a in await quiz.answers_for_attempt(db, attempt_id)
        ],
    }


async def transcript_out(db: AsyncSession, attempt: Attempt, exercise: Exercise) -> TranscriptOut:
    if exercise.skill != "listening":
        raise ApiError(409, "STATE_CONFLICT", "Transcripts are only available for Listening.")
    if attempt.submitted_at is None:
        raise ApiError(409, "TRANSCRIPT_LOCKED", "The transcript unlocks after you submit.")
    detail = await db.get(ListeningExercise, exercise.exercise_id)
    rows = (
        await db.execute(
            select(Question.question_id, Question.evidence_spans)
            .join(Answer, Answer.question_id == Question.question_id)
            .where(Answer.attempt_id == attempt.attempt_id, Answer.grading_status == "graded")
            .order_by(Question.position)
        )
    ).all()
    return TranscriptOut(
        exercise_id=exercise.exercise_id,
        transcript=detail.transcript,
        evidence=[TranscriptEvidence(question_id=qid, spans=spans) for qid, spans in rows],
    )
