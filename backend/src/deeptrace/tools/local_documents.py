"""Bounded read-only document tool, explicitly scoped by its host."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.domain.tools import CustomToolName
from deeptrace.tools.contracts import (
    CachePolicy,
    ToolAdapterResult,
    ToolCapability,
    ToolSpec,
)


class ReadDocumentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1024)


def local_document_tool(root: Path | str) -> ToolSpec:
    workspace = Path(root).resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("document workspace must be a directory")

    def resolve(path):
        target = (workspace / path).resolve()
        if not target.is_relative_to(workspace):
            raise PermissionError("document_outside_workspace")
        if target.suffix.lower() not in {".md", ".txt", ".py", ".json", ".toml"}:
            raise PermissionError("document_type_not_allowed")
        return target

    async def preflight(arguments, context):
        resolve(arguments.path)

    def read(path):
        target = resolve(path)
        if not target.is_file() or target.stat().st_size > 1_000_000:
            return ToolAdapterResult.failure("invalid_arguments")
        with target.open(encoding="utf-8") as document:
            return ToolAdapterResult(preview=document.read(4000))

    async def handler(arguments, context):
        return await asyncio.to_thread(read, arguments.path)

    return ToolSpec(
        name=CustomToolName("read_local_document"),
        argument_model=ReadDocumentArguments,
        handler=handler,
        capability=ToolCapability.FILE_READ,
        cache_policy=CachePolicy.NONE,
        timeout_seconds=10,
        preview_limit=4000,
        stores_evidence=False,
        preflight=preflight,
    )
