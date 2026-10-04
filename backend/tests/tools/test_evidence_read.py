"""Read authorization, ledger replay, and complete verbatim previews."""

import asyncio
import importlib
import importlib.util
import json

import pytest
from pydantic import ValidationError
from strategies.fixtures import FIXED_NOW, TENANT_ID, build_gateway_fixture

from deeptrace.domain import ResearchMode, ToolName, ToolRequest
from deeptrace.tools.budget import BudgetScopeKey
from deeptrace.tools.evidence_store import EvidenceDraft, InMemoryEvidenceStore
from deeptrace.tools.execution_store import InMemoryToolExecutionStore
from deeptrace.tools.policy import CallerRole, EvidenceAuthorization, ToolCaller


def _module():
    assert importlib.util.find_spec("deeptrace.tools.evidence_read") is not None
    return importlib.import_module("deeptrace.tools.evidence_read")


def _draft(body="Store keeps cross-thread facts."):
    return EvidenceDraft(
        canonical_url="https://example.com/store",
        title="Store",
        body=body,
        media_type="text/plain",
        fetched_at=FIXED_NOW,
        source_quality=0.9,
    )


async def _read(
    fixture,
    evidence_id,
    *,
    grants=None,
    tenant=TENANT_ID,
    call_id="read-1",
    arguments=None,
    mode=ResearchMode.WORKFLOW,
):
    _module()
    roles = {
        ResearchMode.WORKFLOW: (CallerRole.WORKFLOW_GRAPH, "workflow-graph"),
        ResearchMode.PLAN_EXECUTE: (
            CallerRole.PLAN_EXECUTE_EXECUTOR,
            "plan-execute-executor",
        ),
        ResearchMode.MULTI_AGENT: (CallerRole.MULTI_AGENT_RESEARCHER, "researcher-0"),
    }
    role, caller_id = roles[mode]
    request = ToolRequest(
        request_id="request-read",
        run_id="run-1",
        thread_id="thread-1",
        call_id=call_id,
        tool=ToolName("read_evidence"),
        arguments={"evidence_id": evidence_id, **(arguments or {})},
    )
    return await fixture.gateway.execute(
        tenant_id=tenant,
        caller=ToolCaller(caller_id, role, mode),
        request=request,
        evidence_authorization=grants,
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"query": "Store", "start": 0},
        {"start": -1},
        {"start": True},
        {"limit": 3001},
        {"limit": True},
        {"limit": 0},
        {"limit": "20"},
        {"tenant_id": "other"},
        {"query": "x" * 1001},
        {"evidence_id": "x" * 129},
    ],
)
def test_read_rejects_invalid_selectors_and_model_identity(extra):
    arguments = _module().ReadEvidenceArguments
    with pytest.raises(ValidationError):
        arguments.model_validate({"evidence_id": "e-1", **extra})


@pytest.mark.asyncio
async def test_find_returns_match_advances_and_never_falls_back_to_prefix():
    fixture = build_gateway_fixture()
    body = "标题🙂\n" + "背景。" * 600 + "API_x(v)\n条件甲。\nAPI_x(w)"
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    grants = EvidenceAuthorization(frozenset([record.id]))
    first = await _read(
        fixture, record.id, grants=grants, arguments={"find": "API_x", "limit": 200}
    )
    assert first.ok
    payload = json.loads(first.preview)
    assert payload["selection"]["found"] is True
    assert payload["selection"]["next_start"] == body.index("API_x") + 5
    assert any("API_x(v)" in p["text"] for p in payload["passages"])
    second = await _read(
        fixture,
        record.id,
        grants=grants,
        call_id="next",
        arguments={
            "find": "API_x",
            "after": payload["selection"]["next_start"],
            "limit": 100,
        },
    )
    assert second.ok
    assert (
        json.loads(second.preview)["selection"]["next_start"]
        == body.rindex("API_x") + 5
    )
    for p in json.loads(second.preview)["passages"]:
        assert p["text"] == body[p["start"] : p["end"]]
    missing = await _read(
        fixture,
        record.id,
        grants=grants,
        call_id="missing",
        arguments={"find": "not-in-page"},
    )
    assert missing.ok
    empty = json.loads(missing.preview)
    assert empty["passages"] == []
    assert empty["selection"]["found"] is False
    assert empty["selection"]["next_start"] is None


@pytest.mark.parametrize(
    "extra",
    [
        {"find": "x", "query": "x"},
        {"find": "x", "start": 0},
        {"after": 0},
        {"find": "x", "after": True},
        {"find": "x", "after": -1},
        {"find": ""},
        {"find": "x" * 201},
        {"find": "long", "limit": 2},
    ],
)
def test_find_rejects_ambiguous_or_invalid_selectors(extra):
    with pytest.raises(ValidationError):
        _module().ReadEvidenceArguments.model_validate({"evidence_id": "e-1", **extra})


@pytest.mark.asyncio
async def test_find_preview_keeps_match_with_escaped_context_and_raw_unicode():
    fixture = build_gateway_fixture()
    body = '\\"\n' * 1200 + "中文🙂API_x" + '\\"\n' * 2000
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"find": "中文🙂API_x", "limit": 3000},
    )
    assert result.ok
    payload = json.loads(result.preview)
    assert len(result.preview) <= 4000
    assert any("中文🙂API_x" in p["text"] for p in payload["passages"])
    assert all(p["text"] == body[p["start"] : p["end"]] for p in payload["passages"])


@pytest.mark.asyncio
async def test_follower_revalidates_lifecycle_after_wait_before_replaying_body():
    release = asyncio.Event()

    class DelayedBodyStore(InMemoryEvidenceStore):
        async def read_body(self, tenant_id, evidence_id):
            await release.wait()
            return await super().read_body(tenant_id, evidence_id)

    store = DelayedBodyStore()

    class RevokingLedger(InMemoryToolExecutionStore):
        async def wait(self, claim):
            release.set()
            result = await super().wait(claim)
            await store.ingest(TENANT_ID, _draft("a newer version"))
            return result

    fixture = build_gateway_fixture(
        evidence_store=store, execution_store=RevokingLedger()
    )
    record = await store.ingest(TENANT_ID, _draft())
    grant = EvidenceAuthorization(frozenset([record.id]))
    async with asyncio.timeout(3):
        first, follower = await asyncio.gather(
            _read(fixture, record.id, grants=grant),
            _read(fixture, record.id, grants=grant),
        )
    assert first.ok and "Store keeps cross-thread facts." in first.preview
    assert not follower.ok and follower.error_code == "evidence_not_authorized"
    assert follower.preview == ""
    scope = (await fixture.budgets.snapshot()).for_scope(
        BudgetScopeKey.for_run("run-1")
    )
    assert scope.used.tool_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", list(ResearchMode))
async def test_each_research_role_reads_verbatim_without_fetching_new_evidence(mode):
    fixture = build_gateway_fixture()
    body = "prefix\n中文🙂\nStore keeps cross-thread facts."
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    result = await _read(
        fixture,
        record.id,
        mode=mode,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"start": 7, "limit": 3},
    )
    assert result.ok
    preview = json.loads(result.preview)
    assert preview["version"] == record.version
    assert preview["content_hash"] == record.content_hash
    assert preview["passages"][0]["text"] == "中文🙂"
    assert (preview["passages"][0]["start"], preview["passages"][0]["end"]) == (7, 10)
    assert preview["passages"][0]["start_line"] == 2
    assert result.evidence_ids == []
    assert result.data_ref == f"evidence://{record.id}/body"
    assert fixture.fetcher.calls == []
    assert await fixture.evidence_store.read_body(TENANT_ID, record.id) == body
    budget = (await fixture.budgets.snapshot()).for_scope(
        BudgetScopeKey.for_run("run-1")
    )
    assert budget.used.tool_calls == 1
    assert budget.used.network_requests == budget.used.fetched_pages == 0


@pytest.mark.asyncio
async def test_committed_read_replays_but_revoked_grant_does_not_replay_body():
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft())
    grants = EvidenceAuthorization(frozenset([record.id]))
    first = await _read(fixture, record.id, grants=grants)
    replay = await _read(fixture, record.id, grants=grants)
    assert first.ok and replay.ok and replay.replayed
    assert replay.preview == first.preview
    denied = await _read(fixture, record.id, grants=EvidenceAuthorization())
    assert denied.error_code == "evidence_not_authorized"
    assert denied.preview == ""
    budget = (await fixture.budgets.snapshot()).for_scope(
        BudgetScopeKey.for_run("run-1")
    )
    assert budget.used.tool_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["missing_grant", "same_workspace_ungranted", "other_workspace"]
)
async def test_workspace_existence_does_not_grant_read_access(kind):
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft("private body"))
    grants = None if kind == "missing_grant" else EvidenceAuthorization()
    tenant = TENANT_ID
    if kind == "other_workspace":
        grants = EvidenceAuthorization(frozenset([record.id]))
        tenant = "workspace-other"
    denied = await _read(fixture, record.id, grants=grants, tenant=tenant)
    assert denied.error_code == (
        "evidence_unavailable"
        if kind == "other_workspace"
        else "evidence_not_authorized"
    )
    assert denied.preview == ""


@pytest.mark.asyncio
async def test_preview_fits_complete_json_even_when_text_needs_escaping():
    fixture = build_gateway_fixture()
    body = '"\\\n🙂中文' * 1000
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft(body))
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"start": 0, "limit": 3000},
    )
    assert result.ok
    preview = json.loads(result.preview)
    assert len(result.preview) <= 4000
    assert preview["selection"]["omitted"] is True
    for passage in preview["passages"]:
        assert passage["text"] == body[passage["start"] : passage["end"]]
    assert await fixture.evidence_store.read_body(TENANT_ID, record.id) == body


@pytest.mark.asyncio
async def test_out_of_range_start_returns_explicit_empty_view():
    fixture = build_gateway_fixture()
    record = await fixture.evidence_store.ingest(TENANT_ID, _draft())
    result = await _read(
        fixture,
        record.id,
        grants=EvidenceAuthorization(frozenset([record.id])),
        arguments={"start": 10000},
    )
    assert result.ok
    preview = json.loads(result.preview)
    assert preview["passages"] == []
    assert preview["selection"]["omitted"] is True


@pytest.mark.asyncio
async def test_superseded_record_requires_explicit_historical_grant():
    fixture = build_gateway_fixture()
    old = await fixture.evidence_store.ingest(TENANT_ID, _draft("old body"))
    await fixture.evidence_store.ingest(TENANT_ID, _draft("new body"))
    denied = await _read(
        fixture, old.id, grants=EvidenceAuthorization(frozenset([old.id]))
    )
    assert denied.error_code == "evidence_not_authorized"
    historical = await _read(
        fixture,
        old.id,
        call_id="historical",
        grants=EvidenceAuthorization(frozenset([old.id]), frozenset([old.id])),
    )
    assert historical.ok
    assert json.loads(historical.preview)["historical"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("historical", [False, True])
async def test_deleted_sql_source_cannot_replay_committed_body(tmp_path, historical):
    _module()
    from sqlalchemy import update

    from deeptrace.persistence.database import create_session_factory
    from deeptrace.persistence.evidence_store import SqlAlchemyEvidenceStore
    from deeptrace.persistence.execution_ledger import SqlAlchemyToolExecutionStore
    from deeptrace.persistence.orm import Base, EvidenceRecordRow

    engine, sessions = create_session_factory(
        f"sqlite+aiosqlite:///{(tmp_path / 'read.db').as_posix()}"
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        store = SqlAlchemyEvidenceStore(sessions)
        fixture = build_gateway_fixture(
            evidence_store=store, execution_store=SqlAlchemyToolExecutionStore(sessions)
        )
        record = await store.ingest(TENANT_ID, _draft("body deleted later"))
        ids = frozenset([record.id])
        grants = EvidenceAuthorization(ids, ids if historical else frozenset())
        assert (await _read(fixture, record.id, grants=grants)).ok
        async with sessions() as session:
            await session.execute(
                update(EvidenceRecordRow)
                .where(
                    EvidenceRecordRow.tenant_id == TENANT_ID,
                    EvidenceRecordRow.evidence_id == record.id,
                )
                .values(status="deleted")
            )
            await session.commit()
        result = await _read(fixture, record.id, grants=grants)
        assert result.error_code == "evidence_unavailable"
        assert result.preview == ""
    finally:
        await engine.dispose()
