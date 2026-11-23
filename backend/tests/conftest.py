import os

import pytest

from app.core.config import PROJECT_ROOT, Settings

# App import must work without a local .env, including on CI.
# Do not override credentials from .env when running local integration tests.
# Tests never call the real AI, even when the developer's .env holds a ROUTER_API_KEY:
# environment variables override .env, and a blank key counts as no key. Tests that need
# the router engine pass a key explicitly (and mock the gateway).
os.environ["ROUTER_API_KEY"] = ""
os.environ.pop("AI_PROVIDER", None)

if not (PROJECT_ROOT / ".env").exists():
    os.environ.setdefault("POSTGRES_PASSWORD", "test-only-password")
    os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret-" + "x" * 32)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        postgres_host="127.0.0.1",
        postgres_port=1,
        postgres_db="unit_test",
        postgres_user="test",
        postgres_password="test-only-password",
        jwt_secret="test-only-jwt-secret-" + "x" * 32,
        # Fast hashing for tests only; production uses the OWASP defaults.
        argon2_memory_kib=8_192,
        argon2_time_cost=1,
        allowed_hosts=["testserver"],
        cors_origins=[],
    )
