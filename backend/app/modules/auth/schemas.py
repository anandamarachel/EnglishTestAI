from typing import Annotated, Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field, StringConstraints

from app.modules.users.schemas import DisplayName, StrictModel, UserOut, UserRole


def normalize_email(value: str) -> str:
    value = value.strip()
    try:
        # Syntax only (no DNS). test_environment permits reserved *.test example domains.
        validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError:
        raise ValueError("Enter a valid email address.") from None
    # The database requires lowercase emails; this is the single normalization point.
    return value.lower()


Email = Annotated[str, Field(max_length=254), AfterValidator(normalize_email)]
# Never trimmed. Policy (length bounds) is enforced by the service from settings.
Password = Annotated[str, Field(min_length=1)]
RefreshToken = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"\S")]


class RegisterRequest(StrictModel):
    email: Email
    display_name: DisplayName
    password: Password
    password_confirmation: Password
    user_role: UserRole


class LoginRequest(StrictModel):
    email: Email
    password: Password


class RefreshRequest(StrictModel):
    refresh_token: RefreshToken


class TokensOut(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_token: str
    user: UserOut


ResetToken = Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"\S")]


class ForgotPasswordRequest(StrictModel):
    email: Email


class ResetPasswordRequest(StrictModel):
    token: ResetToken
    new_password: Password
    password_confirmation: Password


class ChangePasswordRequest(StrictModel):
    current_password: Password
    new_password: Password
    password_confirmation: Password


class MessageOut(StrictModel):
    message: str
