"""Local evidence readers must not block independent checkpoint writes."""

import asyncio

import pytest
from sqlalchemy import text

from deeptrace.persistence.database import create_session_factory


@pytest.mark.asyncio
async def test_reader_snapshot_and_independent_writer_can_coexist(tmp_path):
    engine, _ = create_session_factory(
        f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}"
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE observations (id INTEGER PRIMARY KEY)")
            )
            await connection.execute(text("INSERT INTO observations VALUES (1)"))
        async with engine.connect() as reader:
            await reader.execute(text("BEGIN"))
            assert (
                await reader.execute(text("SELECT COUNT(*) FROM observations"))
            ).scalar() == 1
            async with asyncio.timeout(1):
                async with engine.begin() as writer:
                    await writer.execute(text("INSERT INTO observations VALUES (2)"))
            assert (
                await reader.execute(text("SELECT COUNT(*) FROM observations"))
            ).scalar() == 1
            await reader.rollback()
        async with engine.connect() as reader:
            assert (
                await reader.execute(text("SELECT COUNT(*) FROM observations"))
            ).scalar() == 2
    finally:
        await engine.dispose()
