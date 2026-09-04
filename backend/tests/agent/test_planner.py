import asyncio
from collections import deque

from langchain_core.messages import AIMessage

from deeptrace.agent import planner as planner_module


class ScriptedModel:
    def __init__(self, responses: list[AIMessage | Exception]) -> None:
        self._responses = deque(responses)

    async def ainvoke(self, _messages: object) -> AIMessage:
        response = self._responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def test_parse_search_queries_accepts_repaired_json() -> None:
    assert planner_module.parse_search_queries(
        '{"queries":["技术进展","商业动态"]}'
    ) == [
        "技术进展",
        "商业动态",
    ]


def test_planner_appends_original_query_once() -> None:
    model = ScriptedModel([AIMessage(content='["技术进展", "年度进展"]')])
    queries, _usage, fallback, error = asyncio.run(
        planner_module.PlannerAgent(model, query_count=3).aplan(
            "年度进展",
            [{"title": "背景", "url": "https://example.com", "snippet": "摘要"}],
        )
    )

    assert queries == ["技术进展", "年度进展"]
    assert fallback is False
    assert error == ""


def test_planner_failure_falls_back_to_original_query() -> None:
    model = ScriptedModel(
        [RuntimeError("provider down"), RuntimeError("provider down")]
    )
    queries, _usage, fallback, error = asyncio.run(
        planner_module.PlannerAgent(
            model, query_count=3, call_timeout_seconds=0.1
        ).aplan(
            "原始问题", []
        )
    )

    assert queries == ["原始问题"]
    assert fallback is True
    assert "provider down" in error
