from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core import idempotency
from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.exercises.models import Exercise
from app.modules.exercises.schemas import CreateExerciseResult
from app.modules.jobs import service as jobs
from app.modules.listening import service
from app.modules.listening.schemas import CreateListeningExerciseRequest, TranscriptOut
from app.modules.practice import attempts

router = APIRouter(tags=["Listening"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 409, 413, 422, 429, 503)}


@router.post(
    "/listening/exercises",
    status_code=202,
    response_model=CreateExerciseResult,
    responses=ERRORS,
    summary="Create Listening exercise",
)
async def create_listening_exercise(
    data: CreateListeningExerciseRequest,
    request: Request,
    key: idempotency.IdempotencyKey,
    current: CurrentUserDep,
    session: Session,
) -> JSONResponse:
    """Queues script generation and TTS; the exercise is ready only with its audio."""
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
    "/attempts/{attempt_id}/transcript",
    response_model=TranscriptOut,
    responses=ERRORS,
    summary="Get unlocked Listening transcript",
)
async def get_transcript(
    attempt_id: UUID, current: CurrentUserDep, session: Session
) -> TranscriptOut:
    """409 TRANSCRIPT_LOCKED before submission; evidence only for graded questions."""
    attempt = await attempts.get_owned(session, current.user.user_id, attempt_id)
    exercise = await session.get(Exercise, attempt.exercise_id)
    return await service.transcript_out(session, attempt, exercise)
