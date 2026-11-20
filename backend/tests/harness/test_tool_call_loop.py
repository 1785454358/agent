from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages


class DocumentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration: int
    stop_reason: str
    outcome: str


@pytest.mark.asyncio
async def test_loop_accepts_a_nonresearch_state_and_returns_after_tool_feedback():
    from deeptrace.harness.loop import LoopNodes, build_tool_call_loop

    def model(state):
        iteration = state.get("iteration", 0) + 1
        message = (
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_local_document",
                        "args": {"path": "README.md"},
                        "id": "call-1",
                    }
                ],
            )
            if iteration == 1
            else AIMessage(content="Document describes a harness.")
        )
        return {"messages": [message], "iteration": iteration}

    def tools(state):
        return {
            "messages": [
                ToolMessage(content="A modular harness", tool_call_id="call-1")
            ]
        }

    def observe(state):
        return {
            "stop_reason": "completed" if state["messages"][-1].type == "ai" else ""
        }

    graph = build_tool_call_loop(
        state_schema=DocumentState,
        nodes=LoopNodes(
            prepare_context=lambda s: {},
            call_model=model,
            execute_tools=tools,
            observe=observe,
            nudge=lambda s: {},
            finalize=lambda s: {"outcome": s["messages"][-1].content},
        ),
        max_iterations=3,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Read the document")]}
    )
    assert result["outcome"] == "Document describes a harness."
    assert result["iteration"] == 2
    assert [m.type for m in result["messages"]] == ["human", "ai", "tool", "ai"]
