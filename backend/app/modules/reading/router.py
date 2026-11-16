from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.core.errors import ApiError
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.exercises import service as exercises
from app.modules.exercises.schemas import CreateExerciseResult
from app.modules.jobs import service as jobs
from app.modules.reading import service
from app.modules.reading.schemas import (
    CreateReadingExerciseRequest,
    VocabularyItemOut,
    VocabularyList,
)

router = APIRouter(tags=["Reading"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 409, 413, 422, 429, 503)}


@router.post(
    "/reading/exercises",
    status_code=202,
    response_model=CreateExerciseResult,
    responses=ERRORS,
    summary="Create Reading exercise",
)
async def create_reading_exercise(
    data: CreateReadingExerciseRequest,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    settings = request.app.state.settings
    user_id = current.user.user_id

    async def work():
        exercise, job = await service.create_exercise(session, settings, user_id, data)
        return 202, {"exercise_id": exercise.exercise_id, "job_id": job.job_id}

    status, refs = await idempotency.run(
        session, request, user_id=user_id, key=key, payload=data.model_dump(mode="json"), work=work
    )
    job = await jobs.get_owned(session, user_id, UUID(refs["job_id"]))
    result = CreateExerciseResult(
        exercise_id=UUID(refs["exercise_id"]), job=await jobs.to_out(session, job)
    )
    return JSONResponse(status_code=status, content=result.model_dump(mode="json"))


@router.get(
    "/exercises/{exercise_id}/vocabulary",
    response_model=VocabularyList,
    responses=ERRORS,
    summary="Get Reading vocabulary",
)
async def get_vocabulary(
    exercise_id: UUID, current: CurrentUserDep, session: Session
) -> VocabularyList:
    """Available before a quiz starts; spans point into the immutable passage."""
    exercise = await exercises.get_owned(session, current.user.user_id, exercise_id)
    if exercise.skill != "reading":
        raise ApiError(409, "STATE_CONFLICT", "Vocabulary is only available for Reading.")
    if exercise.generation_status != "ready":
        raise ApiError(409, "STATE_CONFLICT", "This exercise is not ready yet.", retryable=True)
    items = await service.vocabulary(session, exercise_id)
    return VocabularyList(
        items=[
            VocabularyItemOut(
                vocabulary_item_id=v.vocabulary_item_id,
                word_or_phrase=v.word_or_phrase,
                meaning=v.meaning,
                example_sentence=v.example_sentence,
                example_from_passage=v.example_from_passage,
                occurrences=v.occurrences,
                position=v.position,
            )
            for v in items
        ]
    )
