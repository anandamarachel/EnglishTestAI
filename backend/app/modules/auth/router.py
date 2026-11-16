import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.core.config import Settings
from app.modules.auth.delivery import ResetDelivery, ResetMessage
from app.modules.auth.dependencies import Auth, CurrentUserDep
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageOut,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokensOut,
)
from app.modules.users.schemas import UserOut
from app.modules.users.service import to_user_out

router = APIRouter(prefix="/auth", tags=["Auth"])
logger = logging.getLogger(__name__)

FORGOT_MESSAGE = "If an account exists, password reset instructions will be sent."

ERRORS = {code: {"description": "Error envelope"} for code in (401, 409, 422, 429, 503)}


def _limit(request: Request, bucket: str, limit_attr: str, key: str = "") -> None:
    settings: Settings = request.app.state.settings
    if not settings.auth_rate_limit_enabled:
        return
    # Behind a reverse proxy, run Uvicorn with --proxy-headers and trusted
    # --forwarded-allow-ips so this is the real client address, not the proxy's.
    client = request.client.host if request.client else "unknown"
    request.app.state.rate_limiter.hit(
        f"{bucket}:{client}:{key}",
        getattr(settings, limit_attr),
        settings.auth_rate_limit_window_seconds,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserOut,
    responses=ERRORS,
    summary="Register account",
)
async def register(data: RegisterRequest, request: Request, auth: Auth) -> UserOut:
    _limit(request, "register", "register_attempts_per_window")
    return to_user_out(await auth.register(data))


@router.post("/login", response_model=TokensOut, responses=ERRORS, summary="Log in")
async def login(data: LoginRequest, request: Request, auth: Auth) -> TokensOut:
    # Keyed by client and email: slows guessing one account without locking it for others.
    _limit(request, "login", "login_attempts_per_window", data.email)
    tokens = await auth.login(data)
    client = request.client.host if request.client else "unknown"
    request.app.state.rate_limiter.reset(f"login:{client}:{data.email}")
    return tokens


@router.post("/refresh", response_model=TokensOut, responses=ERRORS, summary="Rotate refresh token")
async def refresh(data: RefreshRequest, request: Request, auth: Auth) -> TokensOut:
    _limit(request, "refresh", "refresh_attempts_per_window")
    return await auth.refresh(data.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Log out current session",
)
async def logout(current: CurrentUserDep, auth: Auth) -> Response:
    await auth.logout(current)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _deliver(delivery: ResetDelivery, message: ResetMessage) -> None:
    try:
        await delivery.send(message)
    except Exception:
        # Never log the token or address; the user can simply request another reset.
        logger.exception("Password reset delivery failed")


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageOut,
    responses=ERRORS,
    summary="Request password reset",
)
async def forgot_password(
    data: ForgotPasswordRequest, request: Request, auth: Auth, background: BackgroundTasks
) -> MessageOut:
    _limit(request, "forgot", "login_attempts_per_window")
    # Keyed by email alone, identically for known and unknown addresses.
    settings: Settings = request.app.state.settings
    if settings.auth_rate_limit_enabled:
        request.app.state.rate_limiter.hit(
            f"forgot-email:{data.email}",
            settings.forgot_password_per_window,
            settings.auth_rate_limit_window_seconds,
        )
    message = await auth.request_password_reset(data.email)
    if message is not None:
        # Sent after the response so timing does not reveal whether the account exists.
        background.add_task(_deliver, auth.delivery, message)
    return MessageOut(message=FORGOT_MESSAGE)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Reset password with token",
)
async def reset_password(data: ResetPasswordRequest, request: Request, auth: Auth) -> Response:
    _limit(request, "reset", "login_attempts_per_window")
    await auth.reset_password(data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=ERRORS,
    summary="Change password",
)
async def change_password(
    data: ChangePasswordRequest, request: Request, current: CurrentUserDep, auth: Auth
) -> Response:
    _limit(request, "change", "login_attempts_per_window", str(current.user.user_id))
    await auth.change_password(current, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
