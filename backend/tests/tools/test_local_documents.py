import pytest

from deeptrace.domain import ToolRequest
from deeptrace.observability.events import HarnessEventRecorder
from deeptrace.tools.budget import BudgetScopeKey, BudgetUnits, InMemoryBudgetManager
from deeptrace.tools.cache import InMemorySuccessCache, SuccessCacheSingleflight
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.gateway import AgentToolGateway
from deeptrace.tools.policy import (
    CallerRole,
    DeterministicUrlSecurityPolicy,
    StaticToolAllowlist,
    ToolCaller,
)
from deeptrace.tools.registry import ToolRegistry


def build_gateway(root, *, grant=True):
    from deeptrace.tools.contracts import ToolCapability
    from deeptrace.tools.local_documents import local_document_tool

    registry = ToolRegistry()
    registry.register(local_document_tool(root))
    allowlist = (
        StaticToolAllowlist(
            extra_capabilities={CallerRole.AGENT: {ToolCapability.FILE_READ}}
        )
        if grant
        else StaticToolAllowlist()
    )
    return AgentToolGateway(
        registry=registry,
        allowlist=allowlist,
        security=DeterministicUrlSecurityPolicy(),
        budgets=InMemoryBudgetManager(
            {BudgetScopeKey.for_run("run-1"): BudgetUnits(tool_calls=2)}
        ),
        executions=InMemoryToolExecutionStore(),
        cache=SuccessCacheSingleflight(InMemorySuccessCache()),
        evidence_store=InMemoryEvidenceStore(),
        event_sink=HarnessEventRecorder(),
    )


async def read(gateway, path, *, name="read_local_document", call_id="call-1"):
    return await gateway.execute(
        tenant_id="workspace",
        caller=ToolCaller(caller_id="document-reader", role=CallerRole.AGENT),
        request=ToolRequest(
            run_id="run-1",
            thread_id="thread-1",
            request_id="request-1",
            call_id=call_id,
            tool=name,
            arguments={"path": path},
        ),
    )


@pytest.mark.asyncio
async def test_registered_document_tool_uses_gateway_and_replays_its_result(tmp_path):
    (tmp_path / "notes.md").write_text(
        "Harness execution and context.", encoding="utf-8"
    )
    gateway = build_gateway(tmp_path)
    first = await read(gateway, "notes.md")
    assert first.ok
    assert "Harness execution and context." in first.preview
    (tmp_path / "notes.md").write_text("Changed", encoding="utf-8")
    replay = await read(gateway, "notes.md")
    assert replay.preview == first.preview


@pytest.mark.asyncio
async def test_document_tool_requires_explicit_host_grant(tmp_path):
    (tmp_path / "notes.md").write_text("private document", encoding="utf-8")
    result = await read(build_gateway(tmp_path, grant=False), "notes.md")
    assert not result.ok
    assert "private document" not in result.preview


@pytest.mark.asyncio
async def test_document_tool_rejects_paths_outside_workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (tmp_path / "secret.md").write_text("outside secret", encoding="utf-8")
    result = await read(build_gateway(root), "../secret.md")
    assert not result.ok
    assert "outside secret" not in result.preview


@pytest.mark.asyncio
async def test_unknown_tool_cannot_execute_through_gateway(tmp_path):
    result = await read(build_gateway(tmp_path), "notes.md", name="unregistered_reader")
    assert not result.ok
    assert result.error_code == "tool_not_registered"
