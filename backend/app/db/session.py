from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=5,
            hide_parameters=True,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    # Services explicitly commit successful mutations; closing rolls back unfinished work.
    async with database.sessions() as session:
        yield session
