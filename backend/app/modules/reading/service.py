"""Reading: exercise generation, per-question quiz and final scoring.

The model returns exact quotes for evidence and vocabulary; the backend locates them
in the passage to produce code-point spans, so offsets never depend on model counting.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.contracts import ReadingPackage, ReadingRequest
from app.ai.engine import AIEngine, AIError
from app.core.config import Settings
from app.core.errors import ApiError, validation_error
from app.modules.assessment.models import Evaluation
from app.modules.exercises import service as exercises
from app.modules.exercises.models import Exercise
from app.modules.exercises.schemas import CEFR_FOR_DIFFICULTY
from app.modules.jobs import service as jobs
from app.modules.jobs.models import AIJob
from app.modules.practice.models import Attempt
from app.modules.quiz import service as quiz
from app.modules.quiz.models import Answer, Question
from app.modules.reading.models import ExerciseVocabulary, ReadingAttempt, ReadingExercise
from app.modules.reading.schemas import CreateReadingExerciseRequest, ReadingDraft

DEFAULT_WORDS = {"beginner": 150, "intermediate": 200, "advanced": 300}
QUIZ_RUBRIC_VERSION = "reading-quiz-v1"
QUIZ_RUBRIC = {
    "version": QUIZ_RUBRIC_VERSION,
    "scoring": "sum(awarded_points) / sum(max_points) * 100 once every question is graded",
    "criteria": [],
}


def paragraphs(passage: str) -> list[str]:
    return passage.split("\n\n")


# --- Exercise creation -------------------------------------------------------------------


def plan(settings: Settings, data: CreateReadingExerciseRequest) -> tuple[list[str], int]:
    """Question types per position and the target passage length; explicit errors only."""
    count = data.question_count
    if count > settings.reading_max_questions:
        raise ApiError(
            413,
            "CAPACITY_EXCEEDED",
            f"At most {settings.reading_max_questions} questions can be generated.",
        )
    if data.requested_word_count and data.requested_word_count > settings.reading_max_word_count:
        raise ApiError(
            413,
            "CAPACITY_EXCEEDED",
            f"Passages can be at most {settings.reading_max_word_count} words.",
        )
    minimum = count * settings.reading_min_words_per_question
    if data.requested_word_count is not None and data.requested_word_count < minimum:
        raise validation_error(
            "requested_word_count", f"{count} questions need a passage of at least {minimum} words."
        )
    target = data.requested_word_count or max(DEFAULT_WORDS[data.difficulty], minimum)
    target = min(target, settings.reading_max_word_count)
    types = [data.question_types[i % len(data.question_types)] for i in range(count)]
    return types, target


async def create_exercise(
    db: AsyncSession, settings: Settings, user_id: UUID, data: CreateReadingExerciseRequest
) -> tuple[Exercise, AIJob]:
    types, target = plan(settings, data)
    await exercises.check_generation_capacity(db, settings, user_id)
    topic_id, custom_topic = await exercises.resolve_topic_choice(db, data.topic)
    exercise = Exercise(
        created_by=user_id,
        topic_selection=data.topic.mode,
        topic_id=topic_id,
        custom_topic=custom_topic,
        skill="reading",
        difficulty=data.difficulty,
        content_cefr_level=CEFR_FOR_DIFFICULTY[data.difficulty],
        content_source="ai",
        generation_status="pending",
        generation_config={
            "question_types": types,
            "target_word_count": target,
            "requested_word_count": data.requested_word_count,
            "vocabulary_count": settings.reading_vocabulary_count,
        },
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
    topic_id: UUID | None
    requested_word_count: int | None
    tolerance: float
    request: ReadingRequest


async def prepare_generation(db: AsyncSession, job: AIJob, settings: Settings) -> GenerationInput:
    exercise = await db.get(Exercise, job.exercise_id)
    topic_id, topic_name = await exercises.resolve_generation_topic(db, exercise)
    config = exercise.generation_config
    exercise.generation_status = "generating"
    return GenerationInput(
        exercise_id=exercise.exercise_id,
        topic_id=topic_id,
        requested_word_count=config.get("requested_word_count"),
        tolerance=settings.reading_word_count_tolerance,
        request=ReadingRequest(
            topic=topic_name,
            difficulty=exercise.difficulty,
            cefr_level=exercise.content_cefr_level,
            target_word_count=config["target_word_count"],
            question_types=config["question_types"],
            vocabulary_count=config["vocabulary_count"],
        ),
    )


@dataclass(frozen=True)
class ValidatedPackage:
    package: ReadingPackage
    evidence: list[list[dict]]
    vocabulary: list[tuple[list[dict], str]]


def _invalid() -> AIError:
    return quiz.invalid_output()


def occurrences(passage: str, phrase: str) -> list[dict]:
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    return [
        {"start": m.start(), "end": m.end(), "original": m.group(0)}
        for m in pattern.finditer(passage)
    ]


def sentence_at(passage: str, index: int) -> str:
    start = max(passage.rfind(mark, 0, index) for mark in (". ", "! ", "? ", "\n"))
    start = 0 if start < 0 else start + 1
    ends = [e for e in (passage.find(mark, index) for mark in (".", "!", "?", "\n")) if e >= 0]
    end = min(ends) + 1 if ends else len(passage)
    return passage[start:end].strip()


def validate_package(data: GenerationInput, package: ReadingPackage) -> ValidatedPackage:
    """Untrusted model output: counts, types, keys, length and quotes must all hold."""
    request = data.request
    passage = package.passage
    if not passage.strip() or not package.title.strip() or not package.instructions.strip():
        raise _invalid()
    words = len(passage.split())
    if abs(words - request.target_word_count) > data.tolerance * request.target_word_count:
        raise _invalid()
    if [q.question_type for q in package.questions] != request.question_types:
        raise _invalid()
    evidence = [quiz.check_question(question, passage) for question in package.questions]
    if len(package.vocabulary) != request.vocabulary_count:
        raise _invalid()
    vocabulary = []
    seen = set()
    for item in package.vocabulary:
        key = item.word_or_phrase.strip().lower()
        found = occurrences(passage, item.word_or_phrase.strip())
        if not key or key in seen or not found:
            raise _invalid()
        seen.add(key)
        vocabulary.append((found, sentence_at(passage, found[0]["start"])))
    return ValidatedPackage(package, evidence, vocabulary)


async def execute_generation(engine: AIEngine, data: GenerationInput) -> ValidatedPackage:
    return validate_package(data, await engine.generate_reading(data.request))


async def publish_generation(
    db: AsyncSession, engine: AIEngine, data: GenerationInput, result: ValidatedPackage
) -> dict:
    package = result.package
    db.add(
        ReadingExercise(
            exercise_id=data.exercise_id,
            passage=package.passage,
            requested_word_count=data.requested_word_count,
            question_count=len(package.questions),
        )
    )
    await quiz.add_questions(db, data.exercise_id, package.questions, result.evidence)
    for position, (item, (found, sentence)) in enumerate(
        zip(package.vocabulary, result.vocabulary, strict=True), start=1
    ):
        db.add(
            ExerciseVocabulary(
                exercise_id=data.exercise_id,
                word_or_phrase=item.word_or_phrase.strip(),
                meaning=item.meaning.strip(),
                example_sentence=item.example_sentence.strip(),
                example_from_passage=sentence,
                occurrences=found,
                position=position,
            )
        )
    await db.execute(
        update(Exercise)
        .where(Exercise.exercise_id == data.exercise_id)
        .values(
            title=package.title.strip(),
            instructions=package.instructions.strip(),
            topic_id=data.topic_id,
            generation_status="ready",
            generator_version=engine.name,
        )
    )
    return {"exercise_id": data.exercise_id}


# --- Attempts ------------------------------------------------------------------------------


async def start_attempt(db: AsyncSession, user_id: UUID, exercise: Exercise) -> Attempt:
    attempt = Attempt(
        user_id=user_id,
        exercise_id=exercise.exercise_id,
        attempt_number=await exercises.next_attempt_number(db, user_id, exercise.exercise_id),
        current_stage="reading",
        status="in_progress",
    )
    db.add(attempt)
    await db.flush()
    db.add(ReadingAttempt(attempt_id=attempt.attempt_id))
    for question in await quiz.questions(db, exercise.exercise_id):
        db.add(Answer(attempt_id=attempt.attempt_id, question_id=question.question_id))
    await db.flush()
    await db.refresh(attempt)
    return attempt


async def _require_earlier_submitted(db: AsyncSession, attempt_id: UUID, question: Question):
    """Questions are answered in order; graded/earlier ones remain reviewable."""
    skipped = await db.scalar(
        select(func.count())
        .select_from(Answer)
        .join(Question, Question.question_id == Answer.question_id)
        .where(
            Answer.attempt_id == attempt_id,
            Question.position < question.position,
            Answer.submitted_at.is_(None),
        )
    )
    if skipped:
        raise ApiError(409, "STATE_CONFLICT", "Answer the earlier questions first.")


async def save_draft(db: AsyncSession, attempt: Attempt, draft: ReadingDraft) -> None:
    detail = await db.get(ReadingExercise, attempt.exercise_id)
    parts = paragraphs(detail.passage)
    if draft.paragraph_index >= len(parts):
        raise validation_error("draft.paragraph_index", "Paragraph does not exist.")
    if draft.offset_in_paragraph > len(parts[draft.paragraph_index]):
        raise validation_error("draft.offset_in_paragraph", "Offset is beyond the paragraph.")
    await quiz.apply_draft_answers(db, attempt.attempt_id, attempt.exercise_id, draft.answers)
    if draft.current_question_id is not None:
        question = await db.scalar(
            select(Question).where(
                Question.question_id == draft.current_question_id,
                Question.exercise_id == attempt.exercise_id,
            )
        )
        if question is None:
            raise validation_error("draft.current_question_id", "Question is not in this quiz.")
        await _require_earlier_submitted(db, attempt.attempt_id, question)
    await db.execute(
        update(ReadingAttempt)
        .where(ReadingAttempt.attempt_id == attempt.attempt_id)
        .values(
            paragraph_index=draft.paragraph_index,
            offset_in_paragraph=draft.offset_in_paragraph,
            current_question_id=draft.current_question_id,
        )
    )
    attempt.current_stage = "quiz" if draft.current_question_id else "reading"


async def submit_answer(
    db: AsyncSession,
    settings: Settings,
    user_id: UUID,
    attempt: Attempt,
    question_id: UUID,
    option_id: UUID | None,
    text: str | None,
) -> tuple[Answer, AIJob | None]:
    answer, question = await quiz.lock_answer_for_submission(
        db, attempt.attempt_id, attempt.exercise_id, question_id, option_id, text
    )
    await _require_earlier_submitted(db, attempt.attempt_id, question)
    job = None
    if question.grading_method == "answer_key":
        await quiz.grade_choice(db, answer, question)
    else:
        await db.flush()
        job = await jobs.enqueue(
            db,
            requested_by=user_id,
            job_type="grade_answer",
            max_attempts=settings.job_max_attempts,
            answer_id=answer.answer_id,
        )
    await db.execute(
        update(ReadingAttempt)
        .where(ReadingAttempt.attempt_id == attempt.attempt_id)
        .values(current_question_id=question.question_id)
    )
    attempt.current_stage = "quiz"
    attempt.revision = attempt.revision + 1
    attempt.last_activity_at = func.now()
    await db.flush()
    await db.refresh(answer)
    await db.refresh(attempt)
    return answer, job


async def finish(db: AsyncSession, attempt: Attempt) -> Evaluation:
    """Final submit: every answer locked and graded, then store the aggregate result."""
    answers = await quiz.answers_for_attempt(db, attempt.attempt_id)
    if any(a.submitted_at is None for a in answers):
        raise ApiError(409, "STATE_CONFLICT", "Answer every question before finishing.")
    if any(a.grading_status in ("pending", "processing") for a in answers):
        raise ApiError(
            409, "GRADING_PENDING", "Some answers are still being checked.", retryable=True
        )
    if any(a.grading_status != "graded" for a in answers):
        raise ApiError(409, "GRADING_FAILED", "Some answers could not be checked. Retry them.")
    evaluation = Evaluation(
        attempt_id=attempt.attempt_id,
        status="pending",
        rubric_version=QUIZ_RUBRIC_VERSION,
        rubric_snapshot=QUIZ_RUBRIC,
    )
    db.add(evaluation)
    attempt.submitted_at = func.now()
    quiz.complete(attempt, evaluation, await quiz.quiz_summary(db, attempt.attempt_id))
    attempt.revision = attempt.revision + 1
    await db.flush()
    await db.refresh(evaluation)
    return evaluation


async def vocabulary(db: AsyncSession, exercise_id: UUID) -> list[ExerciseVocabulary]:
    return list(
        await db.scalars(
            select(ExerciseVocabulary)
            .where(ExerciseVocabulary.exercise_id == exercise_id)
            .order_by(ExerciseVocabulary.position)
        )
    )


async def draft_out(db: AsyncSession, attempt_id: UUID) -> dict:
    progress = await db.get(ReadingAttempt, attempt_id)
    return {
        "skill": "reading",
        "paragraph_index": progress.paragraph_index,
        "offset_in_paragraph": progress.offset_in_paragraph,
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
