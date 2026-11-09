"""Only run against a dedicated disposable database whose name ends with _test."""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.core.config import PROJECT_ROOT, Settings
from app.db import models  # noqa: F401 -- register the expected tables
from app.db.base import Base
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]


def alembic(*arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        timeout=60,
    )


def test_migration_roundtrip_and_real_readiness() -> None:
    settings = Settings()
    if not settings.postgres_db.endswith("_test"):
        pytest.fail("Refusing migration test: POSTGRES_DB must end with _test")
    settings.allowed_hosts = ["testserver"]
    alembic("upgrade", "head")
    alembic("check")
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0002"
            )
            assert set(inspect(connection).get_table_names()) == {
                "alembic_version",
                *Base.metadata.tables,
            }
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
        alembic("downgrade", "base")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 0
            assert inspect(connection).get_table_names() == ["alembic_version"]
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'public' AND p.proname LIKE 'ep_%'"
                    )
                ).scalar()
                == 0
            )
        alembic("upgrade", "head")
        alembic("check")
    finally:
        engine.dispose()
