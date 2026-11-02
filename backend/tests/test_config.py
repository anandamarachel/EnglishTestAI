import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_password_is_not_exposed_and_special_characters_work(settings: Settings) -> None:
    settings.postgres_password = Settings(
        _env_file=None, postgres_password="p@ss:/%#word"
    ).postgres_password
    assert settings.database_url.password == "p@ss:/%#word"
    assert "p@ss" not in str(settings.database_url)
    assert "p@ss" not in repr(settings)


def test_empty_database_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="")


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="prodution", postgres_password="test")
