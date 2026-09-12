"""SQLAlchemy-backed LangGraph checkpointer (MySQL in production, SQLite in tests)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.base import ChannelVersions
from langchain_core.runnables import RunnableConfig
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deeptrace.harness.checkpoint import create_harness_checkpoint_serializer
from deeptrace.persistence.orm import CheckpointRow, CheckpointWriteRow


def _config_parts(config: RunnableConfig) -> tuple[str, str]:
    configurable = (config or {}).get("configurable") or {}
    thread_id = configurable.get("thread_id")
    if not thread_id:
        raise ValueError("config.configurable.thread_id is required")
    return str(thread_id), str(configurable.get("checkpoint_ns") or "")


class SqlAlchemyCheckpointSaver(BaseCheckpointSaver):
    """Durable checkpointer sharing the harness strict serializer allowlist."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(serde=create_harness_checkpoint_serializer())
        self._sessions = sessions

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, namespace = _config_parts(config)
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(CheckpointRow)
                    .where(
                        CheckpointRow.thread_id == thread_id,
                        CheckpointRow.checkpoint_ns == namespace,
                    )
                    .order_by(CheckpointRow.checkpoint_id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            write_rows = (
                (
                    await session.execute(
                        select(CheckpointWriteRow)
                        .where(
                            CheckpointWriteRow.thread_id == thread_id,
                            CheckpointWriteRow.checkpoint_ns == namespace,
                            CheckpointWriteRow.checkpoint_id == row.checkpoint_id,
                        )
                        .order_by(CheckpointWriteRow.idx.asc())
                    )
                )
                .scalars()
                .all()
            )
            pending = [
                (
                    write_row.task_id,
                    write_row.channel,
                    self._load(write_row.type, write_row.blob),
                )
                for write_row in write_rows
            ]
            checkpoint = self.serde.loads_typed((row.type, row.checkpoint_blob))
            metadata = (
                self.serde.loads_typed((row.metadata_type, row.metadata_blob))
                if row.metadata_blob
                else {}
            )
            parent_config = None
            if row.parent_checkpoint_id:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": namespace,
                        "checkpoint_id": row.parent_checkpoint_id,
                    }
                }
            config_out = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": row.checkpoint_id,
                }
            }
            return CheckpointTuple(
                config_out, checkpoint, metadata, parent_config, pending
            )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, object] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        if config is None:
            return
        thread_id, namespace = _config_parts(config)
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(CheckpointRow)
                        .where(
                            CheckpointRow.thread_id == thread_id,
                            CheckpointRow.checkpoint_ns == namespace,
                        )
                        .order_by(CheckpointRow.checkpoint_id.desc())
                    )
                )
                .scalars()
                .all()
            )
        count = 0
        for row in reversed(rows):
            metadata = self.serde.loads_typed((row.metadata_type, row.metadata_blob))
            if filter and any(metadata.get(k) != v for k, v in filter.items()):
                continue
            config_out = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": row.checkpoint_id,
                }
            }
            checkpoint = self.serde.loads_typed((row.type, row.checkpoint_blob))
            yield CheckpointTuple(config_out, checkpoint, metadata, None, ())
            count += 1
            if limit is not None and count >= limit:
                break

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id, namespace = _config_parts(config)
        checkpoint_id = str(checkpoint["id"])
        parent_id = (config.get("configurable") or {}).get("checkpoint_id")
        checkpoint_type, checkpoint_blob = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_blob = self.serde.dumps_typed(dict(metadata or {}))
        async with self._sessions() as session:
            existing = (
                await session.execute(
                    select(CheckpointRow).where(
                        CheckpointRow.thread_id == thread_id,
                        CheckpointRow.checkpoint_ns == namespace,
                        CheckpointRow.checkpoint_id == checkpoint_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    CheckpointRow(
                        thread_id=thread_id,
                        checkpoint_ns=namespace,
                        checkpoint_id=checkpoint_id,
                        parent_checkpoint_id=str(parent_id) if parent_id else None,
                        type=checkpoint_type,
                        checkpoint_blob=checkpoint_blob,
                        metadata_blob=metadata_blob,
                        metadata_type=metadata_type,
                        created_at=datetime.now(UTC),
                    )
                )
            else:
                existing.checkpoint_blob = checkpoint_blob
                existing.type = checkpoint_type
            await session.commit()
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, object]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, namespace = _config_parts(config)
        checkpoint_id = (config.get("configurable") or {}).get("checkpoint_id")
        if not checkpoint_id:
            return
        async with self._sessions() as session:
            await session.execute(
                delete(CheckpointWriteRow).where(
                    CheckpointWriteRow.thread_id == thread_id,
                    CheckpointWriteRow.checkpoint_ns == namespace,
                    CheckpointWriteRow.checkpoint_id == checkpoint_id,
                    CheckpointWriteRow.task_id == task_id,
                )
            )
            for idx, (channel, value) in enumerate(writes):
                value_type, blob = self.serde.dumps_typed(value)
                session.add(
                    CheckpointWriteRow(
                        thread_id=thread_id,
                        checkpoint_ns=namespace,
                        checkpoint_id=checkpoint_id,
                        task_id=task_id,
                        task_path=task_path,
                        idx=idx,
                        channel=channel,
                        type=value_type,
                        blob=blob,
                    )
                )
            await session.commit()

    async def adelete_thread(self, thread_id: str) -> None:
        async with self._sessions() as session:
            await session.execute(
                delete(CheckpointWriteRow).where(
                    CheckpointWriteRow.thread_id == thread_id
                )
            )
            await session.execute(
                delete(CheckpointRow).where(CheckpointRow.thread_id == thread_id)
            )
            await session.commit()

    def _load(self, value_type: str | None, blob: bytes | None) -> object:
        if blob is None:
            return None
        return self.serde.loads_typed((value_type, blob))
