import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from deeptrace.writer import WriterAgent
from deeptrace.deep.agent import DeepResearchAgent
from deeptrace.deep.models import ResearchPlan
from deeptrace.deep.tools import ResearchToolbox


def call(name, args):
    return AIMessage(
        content="",
        tool_calls=[{"id": f"call-{name}", "name": name, "args": args}],
        usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    )


def task(task_id="t1", objective="核对技术进展"):
    return {
        "id": task_id,
        "objective": objective,
        "success_criteria": "找到原始资料",
        "depends_on": [],
    }


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.messages.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Fetcher:
    def __init__(self, document):
        self.document = document
        self.calls = []

    async def fetch(self, url):
        self.calls.append(url)
        return self.document.model_copy(
            update={"requested_url": url, "final_url": url, "doc_id": url}
        )

    async def aclose(self):
        pass


class Compressor:
    async def aget_context(self, query, documents, max_results=10):
        return "\n".join(
            f"Source: {d.final_url}\nTitle: {d.title}\nContent: {d.content}"
            for d in documents
        )


def settings(**overrides):
    return SimpleNamespace(
        **{
            "max_runtime_seconds": 10,
            "writer_timeout_seconds": 1,
            "planner_timeout_seconds": 1,
            "deep_call_timeout_seconds": 1,
            "deep_max_tasks": 6,
            "deep_max_rounds_per_task": 4,
            "deep_max_steps": 12,
            "deep_max_replans": 2,
            "deep_max_tokens": 40000,
            "max_fetched_pages": 20,
            "deep_memory_max_age_days": 7,
            "use_memory": False,
            "input_cost_per_million": None,
            "output_cost_per_million": None,
            "max_cost_usd": None,
            **overrides,
        }
    )


def make_agent(raw_document, responses, **overrides):
    model = ScriptedModel(responses)
    fetcher = Fetcher(raw_document)

    async def search(query):
        return {
            "ok": True,
            "results": [
                {"url": "https://example.com/a", "title": "A", "content": "摘要"},
                {"url": "https://example.com/b", "title": "B", "content": "摘要"},
            ],
        }

    config = settings(**overrides)
    toolbox = ResearchToolbox(
        search=search, fetcher=fetcher, compressor=Compressor(), settings=config
    )
    return (
        DeepResearchAgent(
            model=model,
            writer=WriterAgent(model, call_timeout_seconds=1),
            tools=toolbox,
            settings=config,
        ),
        model,
        fetcher,
    )


def test_feedback_replans_and_writer_receives_original_sources(raw_document):
    agent, model, fetcher = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("search_web", {"query": "技术进展"}),
            call("fetch_page", {"url": "https://example.com/a"}),
            call("finish_task", {"status": "completed", "gaps": ["缺少部署限制"]}),
            call("submit_plan", {"tasks": [task("t2", "补查部署限制")]}),
            call("fetch_page", {"url": "https://example.com/b"}),
            call("finish_task", {"status": "completed", "gaps": []}),
            call("submit_plan", {"finish": True, "tasks": []}),
            AIMessage(
                content="报告\n\n1 结论\n\n已核对 [[source:2]]。",
                usage_metadata={
                    "input_tokens": 2,
                    "output_tokens": 3,
                    "total_tokens": 5,
                },
            ),
        ],
    )

    result = asyncio.run(agent.arun("核对技术进展及部署限制"))

    assert result.status == "completed"
    assert fetcher.calls == ["https://example.com/a", "https://example.com/b"]
    assert result.provider_usage.total_tokens == 45
    assert result.role_usage.planner.total_tokens == 5
    assert result.role_usage.executor.total_tokens == 25
    assert result.role_usage.replanner.total_tokens == 10
    assert result.role_usage.writer.total_tokens == 5
    assert result.events[-1].details["total_tokens"] == 45
    assert result.events[-1].details["elapsed_seconds"] >= 0
    assert any(e.event_type == "replanning.completed" for e in result.events)
    assert "缺少部署限制" in str(model.messages[4])
    assert raw_document.content in str(model.messages[4])
    assert raw_document.content in str(model.messages[-1])
    assert "1 结论" in result.answer
    assert result.sources == ["https://example.com/a", "https://example.com/b"]
    assert "http" not in result.answer.split("参考内容")[0]


def test_tool_failure_becomes_observation_and_allows_new_search(raw_document):
    agent, model, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("fetch_page", {"url": "https://unknown.example/a"}),
            call("search_web", {"query": "替代查询"}),
            call("fetch_page", {"url": "https://example.com/a"}),
            call("finish_task", {"status": "completed"}),
            call("submit_plan", {"finish": True}),
            AIMessage(content="结果 [[source:1]]。"),
        ],
    )
    result = asyncio.run(agent.arun("问题"))
    observations = [m for m in model.messages[2] if isinstance(m, ToolMessage)]
    assert "unknown_url" in observations[-1].content
    assert result.status == "completed"


def test_no_tools_cannot_loop_forever_or_claim_completion(raw_document):
    agent, model, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            AIMessage(content="我已经研究好了"),
            AIMessage(content="不用工具"),
        ],
        deep_max_rounds_per_task=2,
        deep_max_replans=0,
    )
    result = asyncio.run(agent.arun("问题"))
    assert len(model.messages) == 3
    assert result.status == "partial"
    assert result.termination_reason != "completed"
    assert result.sources == []


def test_provider_timeout_finishes_with_no_false_success(raw_document):
    agent, _, _ = make_agent(raw_document, [TimeoutError(), TimeoutError()])
    result = asyncio.run(agent.arun("问题"))
    assert result.status == "partial"
    assert result.termination_reason == "planning_failed"


def test_cancellation_propagates_from_executor(raw_document):
    agent, model, _ = make_agent(
        raw_document, [call("submit_plan", {"tasks": [task()]})]
    )
    original = model.ainvoke
    entered = asyncio.Event()

    async def invoke(messages):
        if model.responses:
            return await original(messages)
        entered.set()
        await asyncio.Event().wait()

    model.ainvoke = invoke

    async def run():
        operation = asyncio.create_task(agent.arun("问题"))
        await entered.wait()
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation

    asyncio.run(run())


def test_old_time_and_token_settings_do_not_stop_research(raw_document):
    agent, model, fetcher = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("fetch_page", {"url": "https://example.com/a"}),
            call("finish_task", {"status": "completed"}),
            call("submit_plan", {"finish": True}),
            AIMessage(content="结果 [[source:1]]"),
        ],
        deep_max_tokens=1,
        max_runtime_seconds=0.00001,
    )
    result = asyncio.run(agent.arun("阅读 https://example.com/a"))
    assert result.status == "completed"
    assert result.provider_usage.total_tokens == 20
    assert result.search_queries == []


def test_tool_limit_is_shared_across_parallel_calls(raw_document):
    agent, model, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "a", "name": "search_web", "args": {"query": "A"}},
                    {"id": "b", "name": "search_web", "args": {"query": "B"}},
                ],
            ),
        ],
        deep_max_tool_calls=1,
    )
    result = asyncio.run(agent.arun("问题"))
    assert result.search_queries == ["A"]
    assert result.termination_reason == "tool_call_limit"
    assert result.events[-1].details["tool_calls"] == 1
    assert len(model.messages) == 2


def test_writer_still_runs_after_tool_limit(raw_document):
    agent, _, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("fetch_page", {"url": "https://example.com/a"}),
            AIMessage(content="完整报告 [[source:1]]"),
        ],
        deep_max_tool_calls=1,
    )
    result = asyncio.run(agent.arun("阅读 https://example.com/a"))
    assert result.termination_reason == "tool_call_limit"
    assert "完整报告 [1]" in result.answer
    assert not any(e.event_type == "writing.fallback" for e in result.events)


def test_global_executor_step_limit_stops_replanning(raw_document):
    agent, model, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("search_web", {"query": "first"}),
        ],
        deep_max_steps=1,
    )
    result = asyncio.run(agent.arun("问题"))
    assert result.termination_reason == "step_budget"
    assert len(model.messages) == 2


def test_early_finish_with_pending_tasks_remains_partial(raw_document):
    agent, _, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task(), task("t2", "商业落地")]}),
            call("finish_task", {"status": "blocked", "gaps": ["缺资料"]}),
            call("submit_plan", {"finish": True}),
        ],
    )
    result = asyncio.run(agent.arun("问题"))
    assert result.status == "partial"
    assert "商业落地" in result.unresolved_gaps
    assert "缺资料" in result.unresolved_gaps
    assert any(
        "商业落地" in event.message
        for event in result.events
        if event.event_type == "research.gaps"
    )


def test_parallel_tool_calls_receive_matching_observations(raw_document):
    searches = AIMessage(
        content="",
        tool_calls=[
            {"id": "search-a", "name": "search_web", "args": {"query": "A"}},
            {"id": "search-b", "name": "search_web", "args": {"query": "B"}},
        ],
    )
    agent, model, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            searches,
            call("fetch_page", {"url": "https://example.com/a"}),
            call("finish_task", {"status": "completed"}),
            call("submit_plan", {"finish": True}),
            AIMessage(content="结果 [[source:1]]"),
        ],
    )
    result = asyncio.run(agent.arun("问题"))
    observations = [m for m in model.messages[2] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in observations] == ["search-a", "search-b"]
    assert result.status == "completed"


def test_invalid_plan_retry_usage_is_not_discarded(raw_document):
    agent, _, _ = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [{**task(), "depends_on": ["missing"]}]}),
            call("submit_plan", {"tasks": [task()]}),
            call("finish_task", {"status": "blocked"}),
        ],
        deep_max_replans=0,
    )
    result = asyncio.run(agent.arun("问题"))
    assert result.role_usage.planner.total_tokens == 10
    assert result.provider_usage.total_tokens == 15


def test_explicit_user_url_can_be_read_without_search(raw_document):
    agent, _, fetcher = make_agent(
        raw_document,
        [
            call("submit_plan", {"tasks": [task()]}),
            call("fetch_page", {"url": "https://example.com/a"}),
            call("finish_task", {"status": "completed"}),
            call("submit_plan", {"finish": True}),
            AIMessage(content="结果 [[source:1]]"),
        ],
    )
    result = asyncio.run(agent.arun("阅读 https://example.com/a 并说明机制"))
    assert fetcher.calls == ["https://example.com/a"]
    assert result.status == "completed"


@pytest.mark.parametrize(
    "tasks",
    [
        [{**task(), "depends_on": ["missing"]}],
        [task(), task()],
        [{**task(), "depends_on": ["t2"]}, {**task("t2"), "depends_on": ["t1"]}],
    ],
)
def test_invalid_plan_dependencies_rejected(tasks):
    with pytest.raises(ValueError):
        ResearchPlan.model_validate({"tasks": tasks}).validate_dependencies(set())
