from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app


def test_liveness_does_not_need_database(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_database(settings: Settings) -> None:
    session = AsyncMock()
    application = create_app(settings)

    async def override_session():
        yield session

    application.dependency_overrides[get_session] = override_session
    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    session.execute.assert_awaited_once()


def test_database_failure_is_503_without_sensitive_details(settings: Settings) -> None:
    session = AsyncMock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret-password"))
    application = create_app(settings)

    async def override_session():
        yield session

    application.dependency_overrides[get_session] = override_session
    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "secret-password" not in response.text


def test_unknown_host_is_rejected(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health/live", headers={"Host": "untrusted.example"})
    assert response.status_code == 400


def test_production_hides_openapi_and_docs(settings: Settings) -> None:
    settings.app_env = "production"
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_development_exposes_docs(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 200
        assert "/api/v1/health/ready" in client.get("/openapi.json").json()["paths"]
