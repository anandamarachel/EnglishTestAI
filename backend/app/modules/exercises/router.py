from uuid import UUID

from fastapi import APIRouter

from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.exercises import service
from app.modules.exercises.schemas import ExerciseOut

router = APIRouter(tags=["Exercises"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 404, 422, 429, 503)}


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseOut,
    responses=ERRORS,
    summary="Get exercise",
)
async def get_exercise(exercise_id: UUID, current: CurrentUserDep, session: Session):
    exercise = await service.get_owned(session, current.user.user_id, exercise_id)
    return await service.to_out(session, exercise)
