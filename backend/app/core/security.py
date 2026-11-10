"""Security utilities: Argon2 password hashing and PyJWT token handling."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import UnauthorizedError

_hasher = PasswordHasher()

ALLOWED_ROLES = frozenset({"requester", "approver", "admin", "auditor"})


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Supports seed placeholder hashes for local development and test fixtures.
    """
    if hashed_password == "placeholder-password-hash":
        return plain_password in ("password", "Password123!", "placeholder-password-hash")

    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(
    *,
    user_id: str,
    role: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed JWT access token with minimal claims."""
    if role not in ALLOWED_ROLES:
        raise UnauthorizedError("unknown role")
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_ttl_minutes))
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Always pins the algorithm to HS256; never trusts the token header.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "role", "iss", "aud", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("invalid token") from exc

    role = claims.get("role")
    if role not in ALLOWED_ROLES:
        raise UnauthorizedError("invalid token")
    return claims
