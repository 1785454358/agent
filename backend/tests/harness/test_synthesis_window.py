import json

from deeptrace.domain import ResearchMode, ResearchTopicInput
from deeptrace.harness.batch_synthesis import SUBMIT_TOOL, synthesis_messages
from deeptrace.harness.policies.agent_context import message_tokens
from deeptrace.harness.token_budget import TokenBudgetConfig


def preview(source, ref, text):
    return {
        "evidence_id": source,
        "version": 1,
        "content_hash": "hash",
        "url": f"https://example.com/{source}",
        "title": source,
        "passages": [{"ref": ref, "start": 0, "end": len(text), "text": text}],
    }


def task():
    return ResearchTopicInput(
        run_id="run-1",
        thread_id="thread-1",
        query="Compare two implementations",
        mode=ResearchMode.PLAN_EXECUTE,
        caller_id="plan-execute-executor",
    )


def test_later_source_is_not_starved_by_repeated_reads_of_first_source():
    previews = [preview("first", f"n{i}", (f"detail{i} " * 500)) for i in range(1, 8)]
    previews.append(
        preview("second", "n8", "Independent cancellation exception. " * 100)
    )
    messages, refs = synthesis_messages(
        {"topic_input": task(), "batch_read_previews": previews},
        TokenBudgetConfig(),
    )
    assert "n8" in refs
    payload = json.loads(str(messages[-1].content).split("BATCH_EVIDENCE_JSON:\n")[1])
    assert len(payload["sources"]) == len(
        {s["evidence_id"] for s in payload["sources"]}
    )
    assert payload["selection"]["omitted_passage_count"] > 0
    assert message_tokens(messages, [SUBMIT_TOOL]) <= 6000
    for passage in payload["passages"]:
        original = next(
            p
            for item in previews
            for p in item["passages"]
            if p["ref"] == passage["ref"]
        )
        assert passage == original  # do not slice a condition to fit the window


def test_duplicate_read_refs_do_not_consume_the_window_twice():
    original = preview("first", "n1", "Exact conditional original." * 30)
    messages, refs = synthesis_messages(
        {"topic_input": task(), "batch_read_previews": [original, original]},
        TokenBudgetConfig(),
    )
    payload = json.loads(str(messages[-1].content).split("BATCH_EVIDENCE_JSON:\n")[1])
    assert refs == {"n1"}
    assert len(payload["passages"]) == 1
