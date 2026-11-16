"""Auth behavior that needs no database: envelopes, token checks, limiter, hashing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.rate_limit import RateLimiter
from app.core.security import ALGORITHM, PasswordService, TokenService, hash_refresh_token
from app.main import create_app

REGISTER = {
    "email": "learner@example.test",
    "display_name": "Learner",
    "password": "correct horse battery",
    "password_confirmation": "correct horse battery",
    "user_role": "student",
}


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def assert_envelope(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"code", "message", "request_id", "retryable", "details"}
    assert body["code"] == code
    assert body["request_id"] == response.headers["X-Request-ID"]
    UUID(body["request_id"])
    return body


def test_unknown_field_is_rejected_without_echoing_secrets(client) -> None:
    response = client.post("/api/v1/auth/register", json={**REGISTER, "is_active": False})
    body = assert_envelope(response, 422, "VALIDATION_ERROR")
    assert {"field": "is_active", "message": "Extra inputs are not permitted"} in body["details"]
    assert "correct horse" not in response.text


@pytest.mark.parametrize("field", ["user_role", "email", "password"])
def test_missing_required_field(client, field: str) -> None:
    payload = {k: v for k, v in REGISTER.items() if k != field}
    body = assert_envelope(
        client.post("/api/v1/auth/register", json=payload), 422, "VALIDATION_ERROR"
    )
    assert [detail["field"] for detail in body["details"]] == [field]


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "not-an-email"},
        {"display_name": "   "},
        {"display_name": "x" * 101},
        {"user_role": "admin"},
    ],
)
def test_invalid_register_values(client, changes: dict) -> None:
    response = client.post("/api/v1/auth/register", json={**REGISTER, **changes})
    assert_envelope(response, 422, "VALIDATION_ERROR")


def test_malformed_json_is_400(client) -> None:
    response = client.post(
        "/api/v1/auth/login", content=b"{bad", headers={"Content-Type": "application/json"}
    )
    assert_envelope(response, 400, "BAD_REQUEST")


def test_unknown_route_uses_envelope(client) -> None:
    assert_envelope(client.get("/api/v1/nope"), 404, "NOT_FOUND")


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer not-a-jwt"}, {"Authorization": "Basic dXNlcjpwYXNz"}],
)
def test_protected_route_requires_valid_bearer(client, headers: dict) -> None:
    response = client.get("/api/v1/users/me", headers=headers)
    assert_envelope(response, 401, "UNAUTHORIZED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_client_request_id_is_reused_only_when_uuid(client) -> None:
    supplied = str(uuid4())
    assert (
        client.get("/api/v1/nope", headers={"X-Request-ID": supplied}).json()["request_id"]
        == supplied
    )
    returned = client.get("/api/v1/nope", headers={"X-Request-ID": "<script>"}).json()
    assert returned["request_id"] != "<script>"
    UUID(returned["request_id"])


def test_health_keeps_its_own_shape(client) -> None:
    response = client.get("/api/v1/health/live")
    assert response.json() == {"status": "ok"}
    UUID(response.headers["X-Request-ID"])


class TestTokens:
    def test_roundtrip(self, settings: Settings) -> None:
        tokens = TokenService(settings)
        user_id, session_id = uuid4(), uuid4()
        claims = tokens.decode_access_token(tokens.issue_access_token(user_id, session_id))
        assert (claims.user_id, claims.session_id) == (user_id, session_id)

    def _forge(self, settings: Settings, **overrides) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "sid": str(uuid4()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            **overrides,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"exp": datetime.now(UTC) - timedelta(seconds=1)},
            {"aud": "someone-else"},
            {"iss": "someone-else"},
            {"sid": None},
            {"sub": "not-a-uuid"},
        ],
    )
    def test_rejects_invalid_claims(self, settings: Settings, overrides: dict) -> None:
        assert (
            TokenService(settings).decode_access_token(self._forge(settings, **overrides)) is None
        )

    def test_rejects_other_key_and_unsigned_tokens(self, settings: Settings) -> None:
        tokens = TokenService(settings)
        valid = self._forge(settings)
        header, payload, _ = valid.split(".")
        assert tokens.decode_access_token(f"{header}.{payload}.") is None
        other = jwt.encode(
            jwt.decode(valid, options={"verify_signature": False}), "k" * 40, ALGORITHM
        )
        assert tokens.decode_access_token(other) is None
        unsigned = jwt.encode(jwt.decode(valid, options={"verify_signature": False}), None, "none")
        assert tokens.decode_access_token(unsigned) is None


@pytest.mark.anyio
async def test_password_hashing(settings: Settings) -> None:
    passwords = PasswordService(settings)
    hashed = await passwords.hash("  spaces matter  ")
    assert hashed.startswith("$argon2id$")
    assert await passwords.verify(hashed, "  spaces matter  ")
    assert not await passwords.verify(hashed, "spaces matter")
    assert not await passwords.verify(None, "anything")
    assert not await passwords.verify("not-a-hash", "anything")


def test_refresh_token_hash_is_stable_and_not_the_token() -> None:
    assert hash_refresh_token("abc") == hash_refresh_token("abc") != "abc"


def test_rate_limiter_window_and_retry_after() -> None:
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    for _ in range(3):
        limiter.hit("k", limit=3, window_seconds=60)
    with pytest.raises(ApiError) as error:
        limiter.hit("k", limit=3, window_seconds=60)
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "60"}
    limiter.hit("other", limit=3, window_seconds=60)
    now[0] = 60.0
    limiter.hit("k", limit=3, window_seconds=60)
    limiter.reset("k")


def test_rate_limiter_memory_is_bounded() -> None:
    limiter = RateLimiter(clock=lambda: 0.0, max_keys=100)
    for index in range(1_000):
        limiter.hit(str(index), limit=1, window_seconds=60)
    assert len(limiter._windows) <= 100


def test_production_refuses_local_reset_delivery() -> None:
    base = {"_env_file": None, "postgres_password": "p", "jwt_secret": "j" * 32}
    assert Settings(**base, app_env="production").password_reset_delivery == "disabled"
    assert Settings(**base, app_env="development").password_reset_delivery == "outbox"
    with pytest.raises(ValueError):
        Settings(**base, app_env="production", password_reset_delivery="outbox")


def test_forgot_password_is_503_when_delivery_disabled(settings: Settings) -> None:
    settings.password_reset_delivery = "disabled"
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/auth/password/forgot", json={"email": "a@example.test"})
    assert_envelope(response, 503, "SERVICE_UNAVAILABLE")


@pytest.mark.anyio
async def test_outbox_writes_private_file(tmp_path) -> None:
    from app.modules.auth.delivery import OutboxDelivery, ResetMessage

    outbox = OutboxDelivery(tmp_path / "outbox")
    await outbox.send(ResetMessage("a@example.test", "Rina", "secret-token", datetime.now(UTC)))
    (path,) = (tmp_path / "outbox").iterdir()
    assert "secret-token" in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
