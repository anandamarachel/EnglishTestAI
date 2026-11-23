import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_password_is_not_exposed_and_special_characters_work(settings: Settings) -> None:
    settings.postgres_password = Settings(
        _env_file=None, postgres_password="p@ss:/%#word", jwt_secret="j" * 32
    ).postgres_password
    assert settings.database_url.password == "p@ss:/%#word"
    assert "p@ss" not in str(settings.database_url)
    assert "p@ss" not in repr(settings)


def test_empty_database_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="", jwt_secret="j" * 32)


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="prodution", postgres_password="test", jwt_secret="j" * 32)


@pytest.mark.parametrize("secret", [None, "too-short"])
def test_missing_or_weak_jwt_secret_is_rejected(secret) -> None:
    values = {"postgres_password": "test"}
    if secret is not None:
        values["jwt_secret"] = secret
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def _ai(**values) -> str:
    base = {"_env_file": None, "postgres_password": "x", "jwt_secret": "j" * 32}
    return Settings(**base, ai_provider=None, **values).ai_provider


def test_real_ai_is_used_automatically_when_a_key_is_set() -> None:
    assert _ai(router_api_key="sk-test") == "router"
    assert _ai(router_api_key="sk-test", app_env="production") == "router"


def test_without_a_key_development_falls_back_to_the_stand_in() -> None:
    assert _ai() == "fake"
    assert _ai(router_api_key="") == "fake"  # blank ROUTER_API_KEY= means no key
    assert _ai(router_api_key="   ") == "fake"
    assert _ai(app_env="production") == "none"  # never the stand-in in production


def test_explicit_provider_wins_over_the_key() -> None:
    base = {"_env_file": None, "postgres_password": "x", "jwt_secret": "j" * 32}
    settings = Settings(**base, ai_provider="fake", router_api_key="sk-test")
    assert settings.ai_provider == "fake"
