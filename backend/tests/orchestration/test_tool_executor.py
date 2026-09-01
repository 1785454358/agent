from deeptrace.orchestration.tool_executor import (
    ToolCallResult,
    build_tool_messages,
    select_fetch_tool_calls,
)


def test_external_results_keep_original_tool_order() -> None:
    calls = [
        {"id": "a", "name": "fetch_webpage", "args": {"url": "https://a"}},
        {"id": "b", "name": "fetch_webpage", "args": {"url": "https://b"}},
    ]
    results = [
        ToolCallResult("b", 1, {"ok": True, "title": "B"}),
        ToolCallResult("a", 0, {"ok": True, "title": "A"}),
    ]

    messages = build_tool_messages(calls, results)

    assert [message.tool_call_id for message in messages] == ["a", "b"]


def test_supplement_fetch_limit_preserves_every_tool_call_mapping() -> None:
    calls = [
        {
            "id": f"fetch-{index}",
            "name": "fetch_webpage",
            "args": {"url": f"https://example.com/{index}"},
        }
        for index in range(5)
    ]
    accepted, rejected = select_fetch_tool_calls(calls, max_fetches=3)
    successful = [
        ToolCallResult(
            str(call["id"]),
            order,
            {"ok": True},
        )
        for order, call in accepted
    ]

    messages = build_tool_messages(calls, [*successful, *rejected])

    assert len(accepted) == 3
    assert [message.tool_call_id for message in messages] == [
        f"fetch-{index}" for index in range(5)
    ]
    assert "deferred_batch_limit" in str(messages[-1].content)
