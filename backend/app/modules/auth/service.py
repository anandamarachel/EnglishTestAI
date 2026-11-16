"""Account registration and session lifecycle.

Session model: one auth_sessions row per login. The refresh token is opaque and stored
only as a SHA-256 hash. Refresh rotates that hash in place with a single conditional
UPDATE, so of two concurrent refreshes with the same token exactly one succeeds.
Replaying an already-rotated token returns 401; there is no token-family history, so
replay does not additionally revoke the session (that would need a schema change).
Each refresh slides the session's expiry forward by refresh_token_ttl_days.
Access tokens carry the session id and are rejected as soon as the session is revoked.

Password reset: tokens are random, stored as SHA-256 hashes, expire after
password_reset_ttl_minutes and are consumed with one conditional UPDATE (single use,
race-safe). Requesting a new token invalidates older unused ones. Changing or resetting a
password revokes every session and every outstanding reset token in the same transaction.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError, unauthorized, validation_error
from app.core.security import (
    PasswordService,
    TokenService,
    hash_refresh_token,
    new_refresh_token,
)
from app.modules.auth.delivery import ResetDelivery, ResetMessage
from app.modules.auth.models import AuthSession, PasswordResetToken
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokensOut,
)
from app.modules.users.models import User
from app.modules.users.service import to_user_out

INVALID_CREDENTIALS = "Email or password is incorrect."


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session_id: UUID


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        passwords: PasswordService,
        tokens: TokenService,
        delivery: ResetDelivery,
    ) -> None:
        self.db = session
        self.settings = settings
        self.passwords = passwords
        self.tokens = tokens
        self.delivery = delivery

    def _check_password_policy(self, password: str, field: str = "password") -> None:
        if len(password) < self.settings.password_min_length:
            raise validation_error(
                field, f"Use at least {self.settings.password_min_length} characters."
            )
        if len(password) > self.settings.password_max_length:
            raise validation_error(
                field, f"Use at most {self.settings.password_max_length} characters."
            )

    async def register(self, data: RegisterRequest) -> User:
        self._check_password_policy(data.password)
        if data.password_confirmation != data.password:
            raise validation_error("password_confirmation", "Passwords do not match.")
        if await self.db.scalar(select(User.user_id).where(User.email == data.email)):
            raise _email_taken()
        user = User(
            email=data.email,
            display_name=data.display_name,
            password_hash=await self.passwords.hash(data.password),
            user_role=data.user_role,
        )
        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError:
            # A concurrent registration with the same email won the unique constraint.
            await self.db.rollback()
            raise _email_taken() from None
        await self.db.refresh(user)
        return user

    async def login(self, data: LoginRequest) -> TokensOut:
        user = await self.db.scalar(select(User).where(User.email == data.email))
        # Always verify (against a dummy hash if needed) so timing does not reveal accounts.
        verified = await self.passwords.verify(user.password_hash if user else None, data.password)
        if user is None or not verified or not user.is_active:
            raise unauthorized(INVALID_CREDENTIALS, code="INVALID_CREDENTIALS")
        if self.passwords.needs_rehash(user.password_hash):
            user.password_hash = await self.passwords.hash(data.password)
        refresh_token = new_refresh_token()
        auth_session = AuthSession(
            user_id=user.user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + self.tokens.refresh_ttl,
        )
        self.db.add(auth_session)
        await self.db.commit()
        return self._tokens(user, auth_session.session_id, refresh_token)

    async def refresh(self, refresh_token: str) -> TokensOut:
        new_token = new_refresh_token()
        rotated = await self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.refresh_token_hash == hash_refresh_token(refresh_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > func.now(),
            )
            .values(
                refresh_token_hash=hash_refresh_token(new_token),
                expires_at=datetime.now(UTC) + self.tokens.refresh_ttl,
            )
            .returning(AuthSession.session_id, AuthSession.user_id)
        )
        row = rotated.one_or_none()
        if row is None:
            await self.db.rollback()
            raise unauthorized("Session expired. Log in again.", code="INVALID_REFRESH_TOKEN")
        session_id, user_id = row
        user = await self.db.get(User, user_id)
        if user is None or not user.is_active:
            await self._revoke(session_id)
            await self.db.commit()
            raise unauthorized("Session expired. Log in again.", code="INVALID_REFRESH_TOKEN")
        await self.db.commit()
        return self._tokens(user, session_id, new_token)

    async def logout(self, current: CurrentUser) -> None:
        await self._revoke(current.session_id)
        await self.db.commit()

    async def authenticate(self, access_token: str) -> CurrentUser:
        claims = self.tokens.decode_access_token(access_token)
        if claims is None:
            raise unauthorized()
        user = await self.db.scalar(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.user_id)
            .where(
                AuthSession.session_id == claims.session_id,
                AuthSession.user_id == claims.user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > func.now(),
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise unauthorized()
        return CurrentUser(user=user, session_id=claims.session_id)

    async def change_password(self, current: CurrentUser, data: ChangePasswordRequest) -> None:
        self._check_new_password(data.new_password, data.password_confirmation)
        if not await self.passwords.verify(current.user.password_hash, data.current_password):
            raise validation_error("current_password", "Current password is incorrect.")
        new_hash = await self.passwords.hash(data.new_password)
        await self._replace_password(current.user.user_id, new_hash)
        await self.db.commit()

    async def request_password_reset(self, email: str) -> ResetMessage | None:
        """Create a reset token for an active account; None for unknown/inactive emails.

        The caller returns the same response either way and delivers the message after
        responding, so neither the body nor delivery latency reveals whether it exists.
        """
        if not self.delivery.enabled:
            raise ApiError(
                503,
                "SERVICE_UNAVAILABLE",
                "Password reset is not available yet. Contact your teacher or administrator.",
            )
        user = await self.db.scalar(
            select(User).where(User.email == email, User.is_active.is_(True)).with_for_update()
        )
        if user is None:
            return None
        await self._invalidate_reset_tokens(user.user_id)
        token = new_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=self.settings.password_reset_ttl_minutes)
        self.db.add(
            PasswordResetToken(
                user_id=user.user_id, token_hash=hash_refresh_token(token), expires_at=expires_at
            )
        )
        await self.db.commit()
        return ResetMessage(user.email, user.display_name, token, expires_at)

    async def reset_password(self, data: ResetPasswordRequest) -> None:
        # Validate and hash first so a weak password does not burn the single-use token.
        new_hash = await self._new_password_hash(data.new_password, data.password_confirmation)
        consumed = await self.db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == hash_refresh_token(data.token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(PasswordResetToken.user_id)
        )
        user_id = consumed.scalar_one_or_none()
        user = await self.db.get(User, user_id, with_for_update=True) if user_id else None
        if user is None or not user.is_active:
            await self.db.rollback()
            raise ApiError(
                422,
                "INVALID_RESET_TOKEN",
                "This reset link is invalid or has expired. Request a new one.",
                details=[{"field": "token", "message": "Invalid or expired token."}],
            )
        await self._replace_password(user.user_id, new_hash)
        await self.db.commit()

    def _check_new_password(self, password: str, confirmation: str) -> None:
        self._check_password_policy(password, "new_password")
        if confirmation != password:
            raise validation_error("password_confirmation", "Passwords do not match.")

    async def _new_password_hash(self, password: str, confirmation: str) -> str:
        self._check_new_password(password, confirmation)
        return await self.passwords.hash(password)

    async def _replace_password(self, user_id: UUID, password_hash: str) -> None:
        """New hash, every session revoked and pending reset tokens voided, atomically."""
        await self.db.execute(
            update(User)
            .where(User.user_id == user_id)
            .values(password_hash=password_hash, password_changed_at=func.now())
        )
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        await self._invalidate_reset_tokens(user_id)

    async def _invalidate_reset_tokens(self, user_id: UUID) -> None:
        await self.db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=func.now())
        )

    async def _revoke(self, session_id: UUID) -> None:
        await self.db.execute(
            update(AuthSession)
            .where(AuthSession.session_id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )

    def _tokens(self, user: User, session_id: UUID, refresh_token: str) -> TokensOut:
        return TokensOut(
            access_token=self.tokens.issue_access_token(user.user_id, session_id),
            expires_in=int(self.tokens.access_ttl.total_seconds()),
            refresh_token=refresh_token,
            user=to_user_out(user),
        )


def _email_taken() -> ApiError:
    return ApiError(
        409,
        "EMAIL_ALREADY_REGISTERED",
        "An account with this email already exists.",
        details=[{"field": "email", "message": "Email is already registered."}],
    )
