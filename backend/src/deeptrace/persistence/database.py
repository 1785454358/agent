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
    if engine.dialect.name == "sqlite":
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(connection, _):
            cursor = connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=10000")
            finally:
                cursor.close()

    return engine, async_sessionmaker(engine, expire_on_commit=False)
