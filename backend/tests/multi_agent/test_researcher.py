import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.multi_agent.models import ResearchAssignment
from deeptrace.multi_agent.researcher import Researcher
from deeptrace.multi_agent.runtime import MultiAgentRuntime


def call(name, args):
    return AIMessage(
        content="",
        tool_calls=[{"id": name, "name": name, "args": args}],
        usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    )


def assignment(*, parents=()):
    return ResearchAssignment(
        id="r1",
        objective="核对技术进展",
        required_outputs=["代表性进展"],
        excluded_scope=["融资"],
        source_guidance=["官方公告"],
        parent_ids=list(parents),
    )


def finish_args(**overrides):
    return {
        "task_id": "r1",
        "status": "completed",
        "summary": "已核对技术进展",
        "source_urls": ["https://example.com/a"],
        "gaps": [],
        "stop_reason": "completed",
        **overrides,
    }


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []
        self.bound_tool_names = []

    def bind_tools(self, tools, **kwargs):
        self.bound_tool_names.append(
            [tool["function"]["name"] for tool in tools]
        )
        return self

    async def ainvoke(self, messages):
        self.messages.append(list(messages))
        return self.responses.pop(0)


class Tools:
    def __init__(self):
        self.lease = SimpleNamespace(limit=10, used=0)
        self.read_sources = {"https://example.com/a"}
        self.known_urls = {"https://example.com/a"}
        self.queries = []

    async def execute(self, name, args):
        return {
            "ok": True,
            "fetched": 1,
            "pages": [
                {
                    "ok": True,
                    "url": "https://example.com/a",
                    "context": "LAST_TOOL_MARKER",
                }
            ],
        }


def settings(rounds=3):
    return SimpleNamespace(
        multi_agent_call_timeout_seconds=1,
        multi_agent_max_researcher_rounds=rounds,
    )


def test_early_finish_does_not_add_a_closeout_call():
    async def scenario():
        model = ScriptedModel([call("finish_research", finish_args())])
        result = await Researcher(model, MultiAgentRuntime(settings())).run(
            assignment(), Tools()
        )
        assert result.status == "completed"
        assert len(model.messages) == 1

    asyncio.run(scenario())


def test_model_never_receives_raw_search_web_tool():
    async def scenario():
        model = ScriptedModel([call("finish_research", finish_args())])
        await Researcher(model, MultiAgentRuntime(settings())).run(
            assignment(), Tools()
        )
        assert "search_web" not in model.bound_tool_names[0]
        assert "research_topic" in model.bound_tool_names[0]

    asyncio.run(scenario())


def test_researcher_receives_authoritative_application_date():
    async def scenario():
        model = ScriptedModel([call("finish_research", finish_args())])
        await Researcher(
            model,
            MultiAgentRuntime(settings()),
            question="2025 AI 热点",
            current_date="2026-09-06",
            timezone="Asia/Shanghai",
        ).run(assignment(), Tools())
        prompt = "\n".join(str(message.content) for message in model.messages[0])
        assert '"application_current_date": "2026-09-06"' in prompt
        assert '"application_timezone": "Asia/Shanghai"' in prompt

    asyncio.run(scenario())


def test_only_first_valid_research_tool_executes_per_decision():
    class TrackingTools(Tools):
        def __init__(self):
            super().__init__()
            self.executed_queries = []

        async def execute(self, name, args):
            self.executed_queries.append(args["query"])
            return await super().execute(name, args)

    async def scenario():
        model = ScriptedModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": f"topic-{index}",
                            "name": "research_topic",
                            "args": {
                                "query": query,
                                "max_pages": 1,
                                "target_output": "代表性进展",
                            },
                        }
                        for index, query in enumerate(
                            ["first", "second", "third"], start=1
                        )
                    ],
                ),
                call("finish_research", finish_args()),
            ]
        )
        tools = TrackingTools()
        runtime = MultiAgentRuntime(settings(2))
        result = await Researcher(model, runtime).run(assignment(), tools)
        assert result.status == "completed"
        assert tools.executed_queries == ["first"]
        assert any(
            event.event_type == "tool.batch_limited" for event in runtime.events
        )

    asyncio.run(scenario())


def test_last_tool_observation_is_visible_to_reserved_closeout():
    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "q",
                        "max_pages": 1,
                        "target_output": "代表性进展",
                    },
                ),
                call("finish_research", finish_args()),
            ]
        )
        result = await Researcher(model, MultiAgentRuntime(settings(2))).run(
            assignment(), Tools()
        )
        closeout_text = "\n".join(str(message.content) for message in model.messages[1])
        assert "LAST_TOOL_MARKER" in closeout_text
        assert result.status == "completed"
        assert model.bound_tool_names[-1] == ["finish_research"]

    asyncio.run(scenario())


def test_malformed_closeout_returns_conservative_partial():
    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "q",
                        "max_pages": 1,
                        "target_output": "代表性进展",
                    },
                ),
                AIMessage(content="done"),
            ]
        )
        tools = Tools()
        result = await Researcher(model, MultiAgentRuntime(settings(2))).run(
            assignment(), tools
        )
        assert result.status == "partial"
        assert result.stop_reason == "finalization_failed"
        assert result.gaps == ["代表性进展：未确认"]

    asyncio.run(scenario())


def test_completed_result_cannot_claim_unread_source():
    async def scenario():
        args = finish_args(source_urls=["https://example.com/not-read"])
        model = ScriptedModel([call("finish_research", args), call("finish_research", args)])
        result = await Researcher(model, MultiAgentRuntime(settings(2))).run(
            assignment(), Tools()
        )
        assert result.status == "partial"
        assert result.gaps == ["代表性进展：未确认"]

    asyncio.run(scenario())


def test_research_tool_timeout_is_reported_and_closeout_still_runs():
    class SlowTools(Tools):
        def __init__(self):
            super().__init__()
            self.read_sources = set()

        async def execute(self, name, args):
            await asyncio.sleep(0.05)
            return {"ok": True}

    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "q",
                        "max_pages": 1,
                        "target_output": "代表性进展",
                    },
                ),
                call(
                    "finish_research",
                    finish_args(
                        status="blocked",
                        source_urls=[],
                        gaps=["代表性进展：工具超时"],
                        stop_reason="provider_failure",
                    ),
                ),
            ]
        )
        current_settings = settings(2)
        current_settings.multi_agent_call_timeout_seconds = 0.01
        runtime = MultiAgentRuntime(current_settings)
        result = await Researcher(model, runtime).run(assignment(), SlowTools())
        assert result.status == "blocked"
        assert any("tool_timeout" in event.message for event in runtime.events)
        assert len(model.messages) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "args",
    [
        {"query": "宽泛查询", "max_pages": 1},
        {
            "query": "宽泛查询",
            "max_pages": 1,
            "target_output": "不属于任务的检查项",
        },
    ],
)
def test_unknown_target_output_is_rejected_before_tool_execution(args):
    class TrackingTools(Tools):
        def __init__(self):
            super().__init__()
            self.execute_calls = 0

        async def execute(self, name, current_args):
            self.execute_calls += 1
            return await super().execute(name, current_args)

    async def scenario():
        model = ScriptedModel(
            [
                call("research_topic", args),
                call(
                    "finish_research",
                    finish_args(
                        status="partial",
                        gaps=["代表性进展：未确认"],
                        stop_reason="round_limit",
                    ),
                ),
            ]
        )
        tools = TrackingTools()
        runtime = MultiAgentRuntime(settings(2))

        result = await Researcher(model, runtime).run(assignment(), tools)

        assert result.status == "partial"
        assert tools.execute_calls == 0
        assert tools.lease.used == 0
        rejected = next(
            event
            for event in runtime.events
            if event.event_type == "tool.rejected"
        )
        assert rejected.details["reason_code"] == "unknown_target_output"

    asyncio.run(scenario())


def test_valid_target_output_is_recorded_on_tool_event():
    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "代表性技术进展 官方公告",
                        "max_pages": 1,
                        "target_output": "代表性进展",
                    },
                ),
                call("finish_research", finish_args()),
            ]
        )
        runtime = MultiAgentRuntime(settings(2))

        await Researcher(model, runtime).run(assignment(), Tools())

        started = next(
            event for event in runtime.events if event.event_type == "tool.started"
        )
        assert started.details["target_output"] == "代表性进展"
        assert "代表性进展" in started.message

    asyncio.run(scenario())


def test_followup_prompt_requires_direct_gap_research():
    async def scenario():
        initial_model = ScriptedModel([call("finish_research", finish_args())])
        followup_model = ScriptedModel([call("finish_research", finish_args())])

        await Researcher(initial_model, MultiAgentRuntime(settings())).run(
            assignment(), Tools()
        )
        await Researcher(followup_model, MultiAgentRuntime(settings())).run(
            assignment(parents=("r0",)), Tools()
        )

        initial_prompt = "\n".join(
            str(message.content) for message in initial_model.messages[0]
        )
        followup_prompt = "\n".join(
            str(message.content) for message in followup_model.messages[0]
        )
        assert "initial assignment" in initial_prompt
        assert "broad context" in initial_prompt
        assert "follow-up assignment" in followup_prompt
        assert "do not restart broad topic research" in followup_prompt
        assert "Start broad" not in followup_prompt

    asyncio.run(scenario())


def test_target_output_uses_the_schema_whitespace_normalization():
    class TrackingTools(Tools):
        def __init__(self):
            super().__init__()
            self.received_args = None

        async def execute(self, name, args):
            self.received_args = args
            return await super().execute(name, args)

    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "代表性技术进展 官方公告",
                        "max_pages": 1,
                        "target_output": " 代表性进展 ",
                    },
                ),
                call("finish_research", finish_args()),
            ]
        )
        tools = TrackingTools()
        runtime = MultiAgentRuntime(settings(2))

        await Researcher(model, runtime).run(assignment(), tools)

        assert tools.received_args["target_output"] == "代表性进展"
        assert not any(
            event.event_type == "tool.rejected" for event in runtime.events
        )

    asyncio.run(scenario())


def test_next_decision_receives_task_local_output_progress():
    async def scenario():
        model = ScriptedModel(
            [
                call(
                    "research_topic",
                    {
                        "query": "代表性技术进展 官方公告",
                        "max_pages": 1,
                        "target_output": "代表性进展",
                    },
                ),
                call("finish_research", finish_args()),
            ]
        )

        await Researcher(model, MultiAgentRuntime(settings(3))).run(
            assignment(), Tools()
        )

        second_prompt = "\n".join(
            str(message.content) for message in model.messages[1]
        )
        assert '"researched_outputs": ["代表性进展"]' in second_prompt
        assert '"not_yet_researched_outputs": []' in second_prompt

    asyncio.run(scenario())
