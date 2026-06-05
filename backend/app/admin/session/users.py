from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.admin.crud.crud_user import user_dao
from backend.app.admin.session.schemas import UserSessionUser


class UserSnapshotAdapter(Protocol):
    """Adapter for loading User session snapshots."""

    async def get(self, db: AsyncSession, user_id: int) -> UserSessionUser | None: ...


class SqlAlchemyUserSnapshotAdapter:
    """SQLAlchemy adapter for User session snapshots."""

    async def get(self, db: AsyncSession, user_id: int) -> UserSessionUser | None:
        user = await user_dao.get(db, user_id)
        return UserSessionUser.from_user(user) if user else None


class InMemoryUserSnapshotAdapter:
    """In-memory User snapshot adapter for tests."""

    def __init__(self, users: dict[int, UserSessionUser] | None = None) -> None:
        self.users = users or {}

    async def get(self, db: AsyncSession, user_id: int) -> UserSessionUser | None:
        return self.users.get(user_id)
