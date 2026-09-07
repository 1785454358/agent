"""SQLAlchemy async engine construction."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_session_factory(
    dsn: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create the engine and short-lived session factory owned by the app."""

    engine = create_async_engine(dsn, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
