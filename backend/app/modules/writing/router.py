from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.exercises.schemas import CreateExerciseResult, CreateWritingExerciseRequest
from app.modules.jobs import service as jobs
from app.modules.writing import service

router = APIRouter(tags=["Writing"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 409, 422, 429, 503)}


@router.post(
    "/writing/exercises",
    status_code=202,
    response_model=CreateExerciseResult,
    responses=ERRORS,
    summary="Create Writing exercise",
)
async def create_writing_exercise(
    data: CreateWritingExerciseRequest,
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
