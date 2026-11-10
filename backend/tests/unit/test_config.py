import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_missing_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_empty_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://procurement:procurement@localhost:5432/procurement",
    )
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("JWT_SECRET", "   ")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_safe_dict_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://procurement:super-secret@localhost:5432/procurement",
    )
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("JWT_SECRET", "jwt-super-secret-at-least-32-bytes-long!")

    settings = Settings(_env_file=None)
    safe = settings.safe_dict()

    assert safe["jwt_secret"] == "***"
    assert "super-secret" not in safe["database_url"]
    assert "***@" in safe["database_url"]
    assert "jwt-super-secret" not in repr(settings)
    assert "super-secret" not in repr(settings)
