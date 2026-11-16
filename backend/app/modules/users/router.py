from fastapi import APIRouter

from app.modules.auth.dependencies import CurrentUserDep, Session
from app.modules.users.schemas import UpdateProfileRequest, UserOut
from app.modules.users.service import to_user_out, update_profile

router = APIRouter(prefix="/users", tags=["Users"])

ERRORS = {code: {"description": "Error envelope"} for code in (401, 422, 429, 503)}


@router.get("/me", response_model=UserOut, responses=ERRORS, summary="Get current profile")
async def get_profile(current: CurrentUserDep) -> UserOut:
    return to_user_out(current.user)


@router.patch("/me", response_model=UserOut, responses=ERRORS, summary="Update display name")
async def patch_profile(
    data: UpdateProfileRequest, current: CurrentUserDep, session: Session
) -> UserOut:
    return to_user_out(await update_profile(session, current.user, data))
