"""PostgreSQL repository for user entities."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import User


class UserRepository:
    """PostgreSQL access for users. Callers commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        id: str,
        email: str,
        password_hash: str,
        role: str,
        is_active: bool = True,
    ) -> User:
        user = User(
            id=id,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
        )
        self.session.add(user)
        return user

    async def list_by_role(self, role: str) -> list[User]:
        statement = select(User).where(User.role == role)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
