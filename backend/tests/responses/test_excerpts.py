"""Regression: relevant source tails must reach the real shared responder."""

import json

import pytest
from strategies.fixtures import TENANT_ID, build_gateway_fixture

from deeptrace.responses.graph import build_answer_graph
from deeptrace.tools.evidence_store import InMemoryEvidenceStore
from responses.test_graph import ScriptedModelGateway, _response_input, _seed_evidence


@pytest.mark.asyncio
async def test_query_relevant_tail_reaches_responder_without_changing_evidence():
    body = "Unrelated introduction.\n\n" * 500 + (
        "## Checkpoint recovery limits\n\n"
        "Checkpoint recovery does not restore external side effects in v2.\n"
    )
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [("https://example.com/doc", "Doc", body)])
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    result = await build_answer_graph().ainvoke(
        {
            "response_input": _response_input(
                ids, question="Checkpoint recovery limits in v2?"
            )
        },
        context=fixture.context,
    )
    prompt = model.calls[0][1]
    assert "Checkpoint recovery does not restore external side effects in v2." in prompt
    assert "## Checkpoint recovery limits" in prompt
    assert await store.read_body(TENANT_ID, ids[0]) == body
    assert result["outcome"].cited_evidence_ids == ids


def select(body, question, limit):
    from deeptrace.responses.excerpts import select_source_excerpt

    return select_source_excerpt(body, question, limit)


def test_short_source_is_preserved_exactly():
    body = "# v2\n\nRecovery does not repeat side effects.\n"
    excerpt = select(body, "recovery", 3000)
    assert excerpt.text == body
    assert [(r.start, r.end, r.start_line, r.end_line) for r in excerpt.ranges] == [
        (0, len(body), 1, 3)
    ]


@pytest.mark.parametrize(
    "prefix",
    ["Filler text.\n\n" * 600, "x" * 12000],
    ids=["paragraphs", "single-paragraph"],
)
def test_tail_groups_are_whole_or_explicitly_omitted(prefix):
    fact = "Checkpoint recovery does not restore external side effects in v2."
    body = prefix + fact
    excerpt = select(body, "Checkpoint recovery limits in v2", 3000)
    if prefix == "x" * 12000:
        assert excerpt.strategy == "budget_omitted"
        assert excerpt.ranges == ()
    else:
        assert fact in excerpt.text
    assert len(excerpt.text) <= 3000
    for span in excerpt.ranges:
        assert body[span.start : span.end] in excerpt.text
        assert span.start_line == body.count("\n", 0, span.start) + 1
        assert span.end_line == body.count("\n", 0, span.end - 1) + 1
    assert select(body, "Checkpoint recovery limits in v2", 3000) == excerpt


def test_chinese_question_selects_tail_with_negation():
    body = "无关的正文。\n\n" * 1000 + "## 记忆隔离\n\n跨线程记忆不能跨租户共享。"
    excerpt = select(body, "跨线程记忆如何隔离租户？", 3000)
    assert "跨线程记忆不能跨租户共享。" in excerpt.text
    assert "## 记忆隔离" in excerpt.text


def test_no_match_is_explicit_and_does_not_fabricate_a_read():
    body = "ordinary text " * 1000
    excerpt = select(body, "quasar", 3000)
    assert excerpt.strategy == "no_match"
    assert excerpt.ranges == ()
    assert len(excerpt.text) <= 3000
    assert "quasar" not in excerpt.text
    assert excerpt.omitted_ranges == ((0, len(body)),)


@pytest.mark.parametrize("limit", [1, 40, 150, 3000])
def test_all_metadata_is_inside_character_budget(limit):
    excerpt = select("irrelevant " * 1000 + "Checkpoint recovery.", "checkpoint", limit)
    assert len(excerpt.text) <= limit


def test_separated_matches_keep_original_order_and_report_omissions():
    body = (
        "intro\n\n" * 500
        + "Recovery checkpoint.\n\n"
        + "filler\n\n" * 500
        + "Recovery namespace."
    )
    excerpt = select(body, "recovery checkpoint namespace", 3000)
    assert "Recovery checkpoint." in excerpt.text
    assert "Recovery namespace." in excerpt.text
    assert excerpt.text.index("Recovery checkpoint.") < excerpt.text.index(
        "Recovery namespace."
    )
    assert all(a.end < b.start for a, b in zip(excerpt.ranges, excerpt.ranges[1:]))
    assert excerpt.omitted_ranges


@pytest.mark.parametrize("limit", [0, -1, True, 1.2])
def test_invalid_budgets_are_rejected(limit):
    with pytest.raises(ValueError):
        select("fact", "fact", limit)


def test_empty_source_has_no_fake_location():
    excerpt = select("", "recovery", 3000)
    assert excerpt.text == ""
    assert excerpt.ranges == ()
    assert excerpt.omitted_ranges == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("tiny_budget", [False, True])
async def test_events_distinguish_selection_from_token_delivery(tiny_budget):
    from deeptrace.harness.token_budget import TokenBudgetConfig

    body = "filler\n\n" * 1000 + "Recovery does not replay side effects."
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [("https://example.com/a", "source", body)])
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    budget = (
        TokenBudgetConfig(
            context_tokens=800, output_reserve_tokens=600, safety_tokens=0
        )
        if tiny_budget
        else None
    )
    await build_answer_graph(budget).ainvoke(
        {
            "response_input": _response_input(
                ids, question="Recovery replay side effects?"
            )
        },
        context=fixture.context,
    )
    payload = next(
        p for name, p in fixture.events.events if name == "response.excerpts"
    )
    source = payload["sources"][0]
    assert source["evidence_id"] == ids[0]
    assert source["excerpt_chars"] <= 3000
    assert source["token_status"] == ("dropped" if tiny_budget else "full")
    assert body not in json.dumps(payload)
    assert all("body" not in s and "text" not in s for s in payload["sources"])
    assert source["omitted_ranges"]
    if not tiny_budget:
        for span in source["pre_token_ranges"]:
            assert body[span["start"] : span["end"]] in model.calls[0][1]


@pytest.mark.asyncio
async def test_excerpt_event_failure_does_not_break_response():
    from types import SimpleNamespace

    class FailingSink:
        async def emit(self, event_type, payload):
            raise RuntimeError("event storage unavailable")

    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(
        store, [("https://example.com/a", "source", "Recovery fact.")]
    )
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    context = SimpleNamespace(**{**vars(fixture.context), "event_sink": FailingSink()})
    result = await build_answer_graph().ainvoke(
        {"response_input": _response_input(ids, question="recovery")}, context=context
    )
    assert result["outcome"].partial_reason is None


@pytest.mark.asyncio
async def test_token_trimming_is_not_reported_as_full_excerpt_delivery():
    from deeptrace.harness.token_budget import TokenBudgetConfig

    body = "Recovery checkpoint. " * 1000
    store = InMemoryEvidenceStore()
    ids = await _seed_evidence(store, [("https://example.com/a", "source", body)])
    model = ScriptedModelGateway({"responder": json.dumps({"content": "结论 [1]。"})})
    fixture = build_gateway_fixture(model_gateway=model, evidence_store=store)
    await build_answer_graph(
        TokenBudgetConfig(
            context_tokens=1000, output_reserve_tokens=400, safety_tokens=0
        )
    ).ainvoke(
        {"response_input": _response_input(ids, question="Recovery checkpoint?")},
        context=fixture.context,
    )
    details = next(
        p for name, p in fixture.events.events if name == "response.excerpts"
    )
    assert details["sources"][0]["token_status"] == "truncated"
    allocation = next(
        p for name, p in fixture.events.events if name == "response.budget"
    )
    assert allocation["truncated"] == ["source_1"]
    assert allocation["used_tokens"] <= allocation["input_budget"]


@pytest.mark.parametrize("limit", [3000, 6000, 20000])
def test_each_existing_response_limit_selects_tail_without_budget_growth(limit):
    body = (
        "unrelated text\n\n" * 4000 + "Recovery does not replay external side effects."
    )
    excerpt = select(body, "Recovery external side effects", limit)
    assert "Recovery does not replay external side effects." in excerpt.text
    assert len(excerpt.text) <= limit
