from deeptrace.orchestration.tool_executor import (
    ToolCallResult,
    build_tool_messages,
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
