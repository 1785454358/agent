import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.deep.planner import plan_research
from deeptrace.deep.runtime import RunRuntime


class AutoOnlyModel:
    """Provider double that rejects explicit tool_choice on invocation."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.options = {}

    def bind_tools(self, tools, **kwargs):
        self.options = kwargs
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if "tool_choice" in self.options:
            raise ValueError("Thinking mode does not support this tool_choice")
        return next(self.responses)


def valid_plan():
    return AIMessage(
        content="",
        tool_calls=[
            {
                "id": "plan-1",
                "name": "submit_plan",
                "args": {
                    "tasks": [
                        {
                            "id": "t1",
                            "objective": "核对原始资料",
                            "success_criteria": "找到可引用的原文",
                            "depends_on": [],
                        }
                    ]
                },
            }
        ],
    )


def run_plan(model, initial):
    runtime = RunRuntime(SimpleNamespace(deep_call_timeout_seconds=1))
    plan = asyncio.run(
        plan_research(
            model,
            runtime,
            question="研究问题",
            history=[],
            pending=[],
            slots=2,
            initial=initial,
        )
    )
    return plan, runtime


@pytest.mark.parametrize("initial", [True, False], ids=["planner", "replanner"])
def test_plan_supports_provider_without_explicit_tool_choice(initial):
    plan, _ = run_plan(AutoOnlyModel([valid_plan()]), initial)
    assert plan is not None
    assert plan.tasks[0].id == "t1"
    assert plan.tasks[0].objective == "核对原始资料"


@pytest.mark.parametrize("initial", [True, False], ids=["planner", "replanner"])
def test_plain_text_response_is_retried_not_accepted_as_plan(initial):
    model = AutoOnlyModel([AIMessage(content="计划已经完成"), valid_plan()])
    plan, runtime = run_plan(model, initial)
    assert plan is not None
    assert plan.tasks[0].id == "t1"
    assert model.calls == 2
    assert sum(e.event_type.endswith(".retry") for e in runtime.events) == 1


@pytest.mark.parametrize("initial", [True, False], ids=["planner", "replanner"])
def test_repeated_plain_text_stops_after_two_attempts(initial):
    model = AutoOnlyModel([AIMessage(content="没有工具调用")] * 3)
    plan, runtime = run_plan(model, initial)
    assert plan is None
    assert model.calls == 2
    assert not any(e.event_type.endswith(".completed") for e in runtime.events)
