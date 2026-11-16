"""Password hashing, access-token signing, and opaque refresh tokens."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from anyio import to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

ALGORITHM = "HS256"


class PasswordService:
    """Argon2id hashing kept off the event loop (hashing is deliberately slow)."""

    def __init__(self, settings: Settings) -> None:
        self._hasher = PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_kib,
            parallelism=settings.argon2_parallelism,
        )
        # Verified when an email is unknown so response timing does not reveal accounts.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(16))

    async def hash(self, password: str) -> str:
        return await to_thread.run_sync(self._hasher.hash, password)

    async def verify(self, password_hash: str | None, password: str) -> bool:
        def check() -> bool:
            try:
                return self._hasher.verify(password_hash or self._dummy_hash, password)
            except VerifyMismatchError, VerificationError, InvalidHashError:
                return False

        verified = await to_thread.run_sync(check)
        return verified and password_hash is not None

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self.access_ttl = timedelta(seconds=settings.access_token_ttl_seconds)
        self.refresh_ttl = timedelta(days=settings.refresh_token_ttl_days)

    def issue_access_token(self, user_id: UUID, session_id: UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "sid": str(session_id),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "exp": now + self.access_ttl,
        }
        return jwt.encode(payload, self._secret, algorithm=ALGORITHM)

    def decode_access_token(self, token: str) -> AccessClaims | None:
        """Signature, algorithm, issuer, audience and expiry; session checked by caller."""
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["sub", "sid", "iss", "aud", "iat", "exp"]},
            )
            return AccessClaims(UUID(payload["sub"]), UUID(payload["sid"]))
        except jwt.PyJWTError, ValueError, TypeError:
            return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    # 256-bit random tokens need no slow hash; SHA-256 makes the DB copy useless if leaked.
    return hashlib.sha256(token.encode()).hexdigest()
