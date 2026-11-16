"""Auth/profile flows against a real, disposable PostgreSQL database (name must end _test)."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from test_database_integration import alembic

from app.core.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]

PASSWORD = "correct horse battery"


def make_settings(**overrides) -> Settings:
    settings = Settings(
        allowed_hosts=["testserver"],
        argon2_memory_kib=8_192,
        argon2_time_cost=1,
        **overrides,
    )
    if not settings.postgres_db.endswith("_test"):
        pytest.fail("Refusing auth tests: POSTGRES_DB must end with _test")
    return settings


@pytest.fixture(scope="module")
def engine():
    settings = make_settings()
    alembic("upgrade", "head")
    db = create_engine(settings.database_url, hide_parameters=True)
    yield db
    db.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(make_settings())) as test_client:
        yield test_client


def sql(engine, statement: str, **params):
    with engine.begin() as connection:
        return connection.execute(text(statement), params)


def register(client, email: str | None = None, **changes):
    email = email or f"{uuid4()}@example.test"
    payload = {
        "email": email,
        "display_name": "Rina Amelia",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
        "user_role": "student",
        **changes,
    }
    return client.post("/api/v1/auth/register", json=payload)


def login(client, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def new_account(client) -> tuple[str, dict]:
    email = register(client).json()["email"]
    return email, login(client, email).json()


def test_full_session_lifecycle(client, engine) -> None:
    email = f"  Rina.{uuid4()}@SMAN10Gowa.sch.id "
    created = register(client, email, display_name="  Rina Amelia  ", user_role="teacher")
    assert created.status_code == 201
    user = created.json()
    assert set(user) == {"user_id", "email", "display_name", "user_role", "created_at"}
    assert user["email"] == email.strip().lower()
    assert user["display_name"] == "Rina Amelia"
    assert user["user_role"] == "teacher"

    logged_in = login(client, email.upper())
    assert logged_in.status_code == 200
    tokens = logged_in.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900
    assert tokens["user"] == user

    assert client.get("/api/v1/users/me", headers=bearer(tokens)).json() == user

    stored = sql(
        engine,
        "SELECT u.password_hash, s.refresh_token_hash FROM users u "
        "JOIN auth_sessions s USING (user_id) WHERE u.user_id = :id",
        id=user["user_id"],
    ).one()
    assert stored.password_hash.startswith("$argon2id$")
    assert PASSWORD not in stored.password_hash
    assert stored.refresh_token_hash != tokens["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    assert rotated["user"] == user

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["code"] == "INVALID_REFRESH_TOKEN"

    assert client.get("/api/v1/users/me", headers=bearer(rotated)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=bearer(rotated)).status_code == 204

    # Revoked before the access token's natural expiry.
    assert client.get("/api/v1/users/me", headers=bearer(rotated)).status_code == 401
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=bearer(rotated)).status_code == 401
    after_logout = {"refresh_token": rotated["refresh_token"]}
    assert client.post("/api/v1/auth/refresh", json=after_logout).status_code == 401


def test_logout_only_revokes_current_session(client) -> None:
    email, phone = new_account(client)
    tablet = login(client, email).json()
    assert client.post("/api/v1/auth/logout", headers=bearer(phone)).status_code == 204
    assert client.get("/api/v1/users/me", headers=bearer(tablet)).status_code == 200


def test_duplicate_email_any_case_is_409(client) -> None:
    email = f"dup.{uuid4()}@example.test"
    assert register(client, email).status_code == 201
    response = register(client, email.upper())
    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"password_confirmation": PASSWORD + "!"}, "password_confirmation"),
        ({"password": "short", "password_confirmation": "short"}, "password"),
        ({"password": "x" * 257, "password_confirmation": "x" * 257}, "password"),
    ],
)
def test_password_policy(client, changes: dict, field: str) -> None:
    response = register(client, **changes)
    assert response.status_code == 422
    assert [detail["field"] for detail in response.json()["details"]] == [field]


def test_passwords_are_not_trimmed(client) -> None:
    padded = f"  {PASSWORD}  "
    email = register(client, password=padded, password_confirmation=padded).json()["email"]
    assert login(client, email, PASSWORD).status_code == 401
    assert login(client, email, padded).status_code == 200


def test_login_failures_are_indistinguishable(client, engine) -> None:
    email, _ = new_account(client)
    inactive, _ = new_account(client)
    sql(engine, "UPDATE users SET is_active = false WHERE email = :e", e=inactive)
    responses = [
        login(client, email, "wrong password"),
        login(client, f"nobody.{uuid4()}@example.test"),
        login(client, inactive),
    ]
    bodies = [{k: v for k, v in r.json().items() if k != "request_id"} for r in responses]
    assert {r.status_code for r in responses} == {401}
    assert bodies[0]["code"] == "INVALID_CREDENTIALS"
    assert bodies[0] == bodies[1] == bodies[2]


def test_deactivated_user_loses_access_and_refresh(client, engine) -> None:
    email, tokens = new_account(client)
    sql(engine, "UPDATE users SET is_active = false WHERE email = :e", e=email)
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401
    refresh = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/auth/refresh", json=refresh).status_code == 401


def test_expired_session_rejects_access_and_refresh(client, engine) -> None:
    email, tokens = new_account(client)
    sql(
        engine,
        "UPDATE auth_sessions SET created_at = now() - interval '2 days', "
        "expires_at = now() - interval '1 second' "
        "WHERE user_id = (SELECT user_id FROM users WHERE email = :e)",
        e=email,
    )
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401
    refresh = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/auth/refresh", json=refresh).status_code == 401


def test_token_must_match_its_session_owner(client) -> None:
    _, alice = new_account(client)
    _, bob = new_account(client)
    tokens = client.app.state.tokens
    alice_claims = tokens.decode_access_token(alice["access_token"])
    bob_claims = tokens.decode_access_token(bob["access_token"])
    # Validly signed, but Bob's user id paired with Alice's session.
    forged = tokens.issue_access_token(bob_claims.user_id, alice_claims.session_id)
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code
        == 401
    )


def test_update_profile(client) -> None:
    _, tokens = new_account(client)
    response = client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"display_name": "  Rina A.  "}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Rina A."
    me = client.get("/api/v1/users/me", headers=bearer(tokens)).json()
    assert me["display_name"] == "Rina A."
    for payload in (
        {"display_name": "   "},
        {"display_name": "Ok", "user_role": "teacher"},
        {"display_name": "Ok", "email": "x@example.test"},
    ):
        bad = client.patch("/api/v1/users/me", headers=bearer(tokens), json=payload)
        assert bad.status_code == 422
    assert client.get("/api/v1/users/me", headers=bearer(tokens)).json()["user_role"] == "student"
    assert client.patch("/api/v1/users/me", json={"display_name": "X"}).status_code == 401


def test_login_rate_limit(engine) -> None:
    settings = make_settings(login_attempts_per_window=3)
    with TestClient(create_app(settings)) as client:
        email = f"limit.{uuid4()}@example.test"
        for _ in range(3):
            assert login(client, email, "wrong").status_code == 401
        limited = login(client, email, "wrong")
        assert limited.status_code == 429
        assert limited.json()["code"] == "RATE_LIMITED"
        assert int(limited.headers["Retry-After"]) > 0
        # Another account from the same client is not locked out.
        assert login(client, f"other.{uuid4()}@example.test", "wrong").status_code == 401


async def _concurrently(requests):
    application = create_app(make_settings(auth_rate_limit_enabled=False))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            return await asyncio.gather(*(send(http) for send in requests))


def test_concurrent_refresh_with_one_token_succeeds_once(client) -> None:
    _, tokens = new_account(client)
    payload = {"refresh_token": tokens["refresh_token"]}
    responses = asyncio.run(
        _concurrently([lambda http: http.post("/api/v1/auth/refresh", json=payload)] * 8)
    )
    assert sorted(r.status_code for r in responses) == [200] + [401] * 7


def test_concurrent_registration_creates_one_account(client, engine) -> None:
    email = f"race.{uuid4()}@example.test"
    payload = {
        "email": email,
        "display_name": "Racer",
        "password": PASSWORD,
        "password_confirmation": PASSWORD,
        "user_role": "student",
    }
    responses = asyncio.run(
        _concurrently([lambda http: http.post("/api/v1/auth/register", json=payload)] * 6)
    )
    assert sorted(r.status_code for r in responses) == [201] + [409] * 5
    assert sql(engine, "SELECT count(*) FROM users WHERE email = :e", e=email).scalar() == 1


# --- Password change, forgot and reset ---------------------------------------------

NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture
def mail_client(engine):
    with TestClient(create_app(make_settings(password_reset_delivery="memory"))) as test_client:
        yield test_client


def change(client, tokens, current=PASSWORD, new=NEW_PASSWORD, confirmation=None):
    return client.post(
        "/api/v1/auth/password/change",
        headers=bearer(tokens),
        json={
            "current_password": current,
            "new_password": new,
            "password_confirmation": new if confirmation is None else confirmation,
        },
    )


def forgot(client, email):
    return client.post("/api/v1/auth/password/forgot", json={"email": email})


def reset(client, token, new=NEW_PASSWORD):
    return client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": new, "password_confirmation": new},
    )


def sent(client):
    return client.app.state.reset_delivery.sent


def test_change_password_revokes_every_session(client) -> None:
    email, phone = new_account(client)
    tablet = login(client, email).json()

    wrong = change(client, phone, current="not my password")
    assert wrong.status_code == 422
    assert [d["field"] for d in wrong.json()["details"]] == ["current_password"]
    assert client.get("/api/v1/users/me", headers=bearer(phone)).status_code == 200

    assert change(client, phone).status_code == 204
    for tokens in (phone, tablet):
        assert client.get("/api/v1/users/me", headers=bearer(tokens)).status_code == 401
        refresh = {"refresh_token": tokens["refresh_token"]}
        assert client.post("/api/v1/auth/refresh", json=refresh).status_code == 401
    assert login(client, email).status_code == 401
    assert login(client, email, NEW_PASSWORD).status_code == 200


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [({"new": "short"}, "new_password"), ({"confirmation": "different"}, "password_confirmation")],
)
def test_change_password_validation(client, kwargs: dict, field: str) -> None:
    email, tokens = new_account(client)
    response = change(client, tokens, **kwargs)
    assert response.status_code == 422
    assert [d["field"] for d in response.json()["details"]] == [field]
    assert login(client, email).status_code == 200


def test_change_password_requires_session(client) -> None:
    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "x", "new_password": "y" * 8, "password_confirmation": "y" * 8},
    )
    assert response.status_code == 401


def test_forgot_password_is_identical_for_known_and_unknown(mail_client, engine) -> None:
    known, _ = new_account(mail_client)
    inactive, _ = new_account(mail_client)
    sql(engine, "UPDATE users SET is_active = false WHERE email = :e", e=inactive)
    responses = [
        forgot(mail_client, known.upper()),
        forgot(mail_client, f"nobody.{uuid4()}@example.test"),
        forgot(mail_client, inactive),
    ]
    assert {r.status_code for r in responses} == {202}
    assert len({r.text.replace(r.json()["message"], "") for r in responses}) == 1
    assert len({r.json()["message"] for r in responses}) == 1
    messages = sent(mail_client)
    assert [m.email for m in messages] == [known]
    assert all(messages[0].token not in r.text for r in responses)
    stored = sql(
        engine,
        "SELECT token_hash FROM password_reset_tokens t JOIN users u "
        "USING (user_id) WHERE u.email = :e",
        e=known,
    ).scalar_one()
    assert stored != messages[0].token


def test_reset_password_flow(mail_client) -> None:
    email, phone = new_account(mail_client)
    assert forgot(mail_client, email).status_code == 202
    token = sent(mail_client)[-1].token

    # A rejected new password leaves the token usable.
    weak = reset(mail_client, token, new="short")
    assert weak.status_code == 422
    assert [d["field"] for d in weak.json()["details"]] == ["new_password"]

    assert reset(mail_client, token).status_code == 204
    assert mail_client.get("/api/v1/users/me", headers=bearer(phone)).status_code == 401
    assert login(mail_client, email).status_code == 401
    assert login(mail_client, email, NEW_PASSWORD).status_code == 200

    reused = reset(mail_client, token, new="yet another passphrase")
    assert reused.status_code == 422
    assert reused.json()["code"] == "INVALID_RESET_TOKEN"
    assert reset(mail_client, "not-a-real-token").json()["code"] == "INVALID_RESET_TOKEN"


def test_new_reset_request_voids_older_token(mail_client) -> None:
    email, _ = new_account(mail_client)
    forgot(mail_client, email)
    forgot(mail_client, email)
    older, newer = (m.token for m in sent(mail_client)[-2:])
    assert reset(mail_client, older).status_code == 422
    assert reset(mail_client, newer).status_code == 204


def test_password_change_voids_pending_reset_token(mail_client) -> None:
    email, tokens = new_account(mail_client)
    forgot(mail_client, email)
    token = sent(mail_client)[-1].token
    assert change(mail_client, tokens).status_code == 204
    assert reset(mail_client, token, new="third passphrase here").status_code == 422


def test_expired_reset_token(mail_client, engine) -> None:
    email, _ = new_account(mail_client)
    forgot(mail_client, email)
    sql(
        engine,
        "UPDATE password_reset_tokens SET created_at = now() - interval '2 hours', "
        "expires_at = now() - interval '1 second' "
        "WHERE user_id = (SELECT user_id FROM users WHERE email = :e)",
        e=email,
    )
    assert reset(mail_client, sent(mail_client)[-1].token).status_code == 422


def test_forgot_password_rate_limit_per_email(engine) -> None:
    settings = make_settings(password_reset_delivery="memory", forgot_password_per_window=2)
    with TestClient(create_app(settings)) as client:
        email = f"flood.{uuid4()}@example.test"
        assert [forgot(client, email).status_code for _ in range(3)] == [202, 202, 429]
        assert forgot(client, f"other.{uuid4()}@example.test").status_code == 202


def test_concurrent_reset_with_one_token_succeeds_once(mail_client) -> None:
    email, _ = new_account(mail_client)
    forgot(mail_client, email)
    token = sent(mail_client)[-1].token
    body = {"token": token, "new_password": NEW_PASSWORD, "password_confirmation": NEW_PASSWORD}
    responses = asyncio.run(
        _concurrently([lambda http: http.post("/api/v1/auth/password/reset", json=body)] * 6)
    )
    assert sorted(r.status_code for r in responses) == [204] + [422] * 5
