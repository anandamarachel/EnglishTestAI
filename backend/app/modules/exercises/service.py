from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.engine import AIError
from app.core.errors import ApiError, validation_error
from app.modules.catalog.models import Topic
from app.modules.exercises.models import Exercise
from app.modules.exercises.schemas import (
    ExerciseTopic,
    ListeningContent,
    ListeningExerciseOut,
    PersonaSummary,
    ReadingContent,
    ReadingExerciseOut,
    SpeakingContent,
    SpeakingExerciseOut,
    WritingContent,
    WritingExerciseOut,
)
from app.modules.jobs.models import AIJob
from app.modules.listening.models import ListeningExercise
from app.modules.media import service as media
from app.modules.media.models import MediaAsset
from app.modules.practice.models import Attempt
from app.modules.quiz import service as quiz
from app.modules.reading.models import ReadingExercise
from app.modules.speaking.models import SpeakingExercise
from app.modules.writing.models import WritingExercise


async def get_owned(db: AsyncSession, user_id: UUID, exercise_id: UUID) -> Exercise:
    exercise = await db.scalar(
        select(Exercise).where(Exercise.exercise_id == exercise_id, Exercise.created_by == user_id)
    )
    if exercise is None:
        raise ApiError(404, "NOT_FOUND", "Resource not found.")
    return exercise


async def to_out(db: AsyncSession, exercise: Exercise):
    if exercise.topic_selection == "custom":
        name = exercise.custom_topic
    elif exercise.topic_id is not None:
        name = await db.scalar(select(Topic.name).where(Topic.topic_id == exercise.topic_id))
    else:
        name = None  # random topic not resolved yet
    common = {
        "exercise_id": exercise.exercise_id,
        "difficulty": exercise.difficulty,
        "content_cefr_level": exercise.content_cefr_level,
        "topic": ExerciseTopic(
            mode=exercise.topic_selection, topic_id=exercise.topic_id, name=name
        ),
        "title": exercise.title,
        "instructions": exercise.instructions,
        "generation_status": exercise.generation_status,
        "created_at": exercise.created_at,
    }
    ready = exercise.generation_status == "ready"
    if exercise.skill == "writing":
        content = None
        if ready:
            detail = await db.get(WritingExercise, exercise.exercise_id)
            content = WritingContent(
                target_word_count=detail.target_word_count, rubric_version=detail.rubric_version
            )
        return WritingExerciseOut(**common, skill="writing", content=content, questions=[])
    if exercise.skill == "reading":
        content, questions = None, []
        if ready:
            detail = await db.get(ReadingExercise, exercise.exercise_id)
            content = ReadingContent(
                passage=detail.passage,
                requested_word_count=detail.requested_word_count,
                question_count=detail.question_count,
                feedback_mode="per_question",
            )
            questions = await quiz.questions_out(db, exercise.exercise_id)
        return ReadingExerciseOut(**common, skill="reading", content=content, questions=questions)
    if exercise.skill == "listening":
        content, questions = None, []
        if ready:
            detail = await db.get(ListeningExercise, exercise.exercise_id)
            audio = await db.get(MediaAsset, detail.audio_media_id)
            content = ListeningContent(
                audio=media.to_out(audio),
                question_count=detail.question_count,
                feedback_mode=detail.feedback_mode,
                transcript_policy=detail.transcript_policy,
            )
            questions = await quiz.questions_out(db, exercise.exercise_id)
        return ListeningExerciseOut(
            **common, skill="listening", content=content, questions=questions
        )
    content = None
    if ready:
        detail = await db.get(SpeakingExercise, exercise.exercise_id)
        content = SpeakingContent(
            persona=PersonaSummary(
                persona_id=detail.persona_id,
                name=detail.persona_snapshot["name"],
                role_description=detail.persona_snapshot["role_description"],
            ),
            rubric_version=detail.rubric_version,
        )
    return SpeakingExerciseOut(**common, skill="speaking", content=content, questions=[])


# --- Shared by every skill's creation, generation and attempt steps -----------------------


async def check_generation_capacity(db: AsyncSession, settings, user_id: UUID) -> None:
    active = await db.scalar(
        select(func.count())
        .select_from(AIJob)
        .where(
            AIJob.requested_by == user_id,
            AIJob.job_type == "generate_exercise",
            AIJob.status.in_(("queued", "running", "cancel_requested")),
        )
    )
    if active >= settings.max_active_generation_jobs_per_user:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "You already have exercises being prepared. Wait for them to finish.",
            retryable=True,
            headers={"Retry-After": "10"},
        )


async def resolve_topic_choice(db: AsyncSession, topic) -> tuple[UUID | None, str | None]:
    """(topic_id, custom_topic) for a request; random stays unresolved until generation."""
    if topic.mode == "catalog":
        exists = await db.scalar(
            select(Topic.topic_id).where(Topic.topic_id == topic.topic_id, Topic.is_active)
        )
        if exists is None:
            raise validation_error("topic.topic_id", "Topic does not exist or is inactive.")
        return topic.topic_id, None
    if topic.mode == "custom":
        return None, topic.text
    return None, None


async def resolve_generation_topic(db: AsyncSession, exercise: Exercise) -> tuple[UUID | None, str]:
    """(topic_id, name) for generation; random picks a real active catalog topic."""
    if exercise.topic_selection == "custom":
        return None, exercise.custom_topic
    topic_id = exercise.topic_id
    if topic_id is None:
        topic_id = await db.scalar(
            select(Topic.topic_id).where(Topic.is_active).order_by(func.random()).limit(1)
        )
        if topic_id is None:
            raise AIError("NO_ACTIVE_TOPICS", retryable=False)
    return topic_id, await db.scalar(select(Topic.name).where(Topic.topic_id == topic_id))


async def next_attempt_number(db: AsyncSession, user_id: UUID, exercise_id: UUID) -> int:
    """Caller holds the exercise lock, so numbering cannot race."""
    current = await db.scalar(
        select(func.max(Attempt.attempt_number)).where(
            Attempt.exercise_id == exercise_id, Attempt.user_id == user_id
        )
    )
    return (current or 0) + 1
