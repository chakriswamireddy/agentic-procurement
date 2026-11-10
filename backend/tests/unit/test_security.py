"""Unit tests for Phase 5 security utilities: Argon2 and JWT handling."""

from datetime import timedelta

import pytest
from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        jwt_secret="super-secret-jwt-test-key-at-least-32-bytes-long",
        database_url="postgresql://procurement:procurement@localhost:5432/procurement",
        mongodb_url="mongodb://localhost:27017",
    )


def test_argon2_hashing_and_verification() -> None:
    raw = "MySecurePassword2026!"
    hashed = hash_password(raw)
    assert hashed.startswith("$argon2id$")
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_seed_placeholder_password_verification() -> None:
    placeholder = "placeholder-password-hash"
    assert verify_password("Password123!", placeholder) is True
    assert verify_password("password", placeholder) is True
    assert verify_password("wrong-pass", placeholder) is False


def test_jwt_create_and_decode(test_settings: Settings) -> None:
    token = create_access_token(
        user_id="USR0042",
        role="requester",
        settings=test_settings,
        expires_delta=timedelta(minutes=30),
    )
    assert isinstance(token, str)

    claims = decode_access_token(token, test_settings)
    assert claims["sub"] == "USR0042"
    assert claims["role"] == "requester"
    assert claims["iss"] == test_settings.jwt_issuer
    assert claims["aud"] == test_settings.jwt_audience
    assert "email" not in claims
    assert claims.get("jti")


def test_jwt_expired_token_raises_unauthorized(test_settings: Settings) -> None:
    token = create_access_token(
        user_id="USR0042",
        role="requester",
        settings=test_settings,
        expires_delta=timedelta(seconds=-10),  # Already expired
    )
    with pytest.raises(UnauthorizedError, match="token has expired"):
        decode_access_token(token, test_settings)


def test_jwt_tampered_token_raises_unauthorized(test_settings: Settings) -> None:
    token = create_access_token(
        user_id="USR0042",
        role="requester",
        settings=test_settings,
    )
    tampered = token[:-4] + "abcd"
    with pytest.raises(UnauthorizedError, match="invalid token"):
        decode_access_token(tampered, test_settings)


def test_jwt_alg_none_rejected(test_settings: Settings) -> None:
    import base64
    import json

    def b64(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64({"alg": "none", "typ": "JWT"})
    payload = b64(
        {
            "sub": "USR0042",
            "role": "admin",
            "iss": test_settings.jwt_issuer,
            "aud": test_settings.jwt_audience,
            "iat": 1,
            "exp": 9999999999,
            "jti": "x",
        }
    )
    token = f"{header}.{payload}."
    with pytest.raises(UnauthorizedError, match="invalid token"):
        decode_access_token(token, test_settings)


def test_jwt_wrong_issuer_rejected(test_settings: Settings) -> None:
    from datetime import UTC, datetime

    import jwt as pyjwt

    now = int(datetime.now(UTC).timestamp())
    token = pyjwt.encode(
        {
            "sub": "USR0042",
            "role": "requester",
            "iss": "someone-else",
            "aud": test_settings.jwt_audience,
            "iat": now,
            "exp": now + 600,
            "jti": "abc",
        },
        test_settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError, match="invalid token"):
        decode_access_token(token, test_settings)


def test_jwt_missing_role_rejected(test_settings: Settings) -> None:
    from datetime import UTC, datetime

    import jwt as pyjwt

    now = int(datetime.now(UTC).timestamp())
    token = pyjwt.encode(
        {
            "sub": "USR0042",
            "iss": test_settings.jwt_issuer,
            "aud": test_settings.jwt_audience,
            "iat": now,
            "exp": now + 600,
            "jti": "abc",
        },
        test_settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError, match="invalid token"):
        decode_access_token(token, test_settings)


def test_jwt_secret_must_be_32_bytes() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="too-short",
            database_url="postgresql://x/x",
            mongodb_url="mongodb://localhost:27017",
        )
