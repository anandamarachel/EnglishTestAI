import os

import pytest

from app.core.config import PROJECT_ROOT, Settings

# App import must work without a local .env, including on CI.
# Do not override credentials from .env when running local integration tests.
if not (PROJECT_ROOT / ".env").exists():
    os.environ.setdefault("POSTGRES_PASSWORD", "test-only-password")


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
        allowed_hosts=["testserver"],
        cors_origins=[],
    )
