"""Authentication service: credential validation and token lifecycle."""

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
)
from app.database.postgres.models import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthenticatedUser


class AuthService:
    def __init__(self, users: UserRepository, settings: Settings) -> None:
        self.users = users
        self.settings = settings

    async def authenticate(self, email: str, password: str) -> tuple[User, str]:
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            # Constant-shape failure: do not reveal whether the email exists.
            raise UnauthorizedError("invalid email or password")

        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("invalid email or password")

        token = create_access_token(
            user_id=user.id,
            role=user.role,
            settings=self.settings,
        )
        return user, token

    async def verify_token(self, token: str) -> AuthenticatedUser:
        """Validate JWT claims, then reload the user for active status and current role."""
        claims = decode_access_token(token, self.settings)
        user = await self.users.get_by_id(claims["sub"])
        if user is None or not user.is_active:
            raise UnauthorizedError("invalid token")
        return AuthenticatedUser(
            id=user.id,
            email=user.email,
            role=user.role,
        )

    async def get_user_by_id(self, user_id: str) -> User | None:
        return await self.users.get_by_id(user_id)
