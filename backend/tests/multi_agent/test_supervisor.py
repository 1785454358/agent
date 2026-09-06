import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from deeptrace.multi_agent.models import AssignmentDraft
from deeptrace.multi_agent.runtime import MultiAgentRuntime
from deeptrace.multi_agent.supervisor import Supervisor, build_gap_followups


def decision_call(args):
    return AIMessage(
        content="",
        tool_calls=[
            {"id": "decision", "name": "submit_supervisor_decision", "args": args}
        ],
        usage_metadata={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
    )


def valid_finish_call():
    return decision_call(
        {
            "action": "finish",
            "rationale": "已有资料可回答",
            "assignments": [],
            "sufficient": True,
            "gaps": [],
        }
    )


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bind_kwargs = []
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        self.bind_kwargs.append(kwargs)
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return self.responses.pop(0)


def settings():
    return SimpleNamespace(
        multi_agent_call_timeout_seconds=1,
        multi_agent_max_batch_size=3,
    )


def partial_history():
    return [
        {
            "id": task_id,
            "objective": objective,
            "required_outputs": [required],
            "excluded_scope": [],
            "source_guidance": ["官方来源"],
            "parent_ids": [],
            "status": "partial",
            "summary": "取得部分资料",
            "gaps": gaps,
            "source_count": source_count,
        }
        for task_id, objective, required, gaps, source_count in [
            (
                "r1",
                "研究模型发布",
                "核对模型事件",
                ["Claude 官方公告缺失", "Gemini 官方公告缺失"],
                4,
            ),
            (
                "r2",
                "研究行业应用",
                "核对应用事件",
                ["医疗案例缺失", "金融案例缺失"],
                1,
            ),
            (
                "r3",
                "研究监管政策",
                "核对政策事件",
                ["欧盟官方文件缺失"],
                2,
            ),
        ]
    ]


def test_supervisor_dispatches_valid_independent_batch_without_forced_tool_choice():
    async def scenario():
        model = ScriptedModel(
            [
                decision_call(
                    {
                        "action": "dispatch",
                        "rationale": "覆盖三个独立方向",
                        "assignments": [
                            {
                                "objective": "研究技术",
                                "required_outputs": ["代表性进展"],
                                "excluded_scope": ["产业和政策"],
                                "source_guidance": ["官方公告"],
                                "parent_ids": [],
                            }
                        ],
                        "sufficient": False,
                        "gaps": [],
                    }
                )
            ]
        )
        supervisor = Supervisor(model, MultiAgentRuntime(settings()))
        decision = await supervisor.decide(
            "2025 AI 热点", [], remaining_slots=6, can_dispatch=True
        )
        assert decision.action == "dispatch"
        assert model.bind_kwargs == [{}]

    asyncio.run(scenario())


def test_supervisor_repairs_one_invalid_decision():
    async def scenario():
        valid = {
            "action": "finish",
            "rationale": "已有资料可回答",
            "assignments": [],
            "sufficient": True,
            "gaps": [],
        }
        model = ScriptedModel([AIMessage(content="plain text"), decision_call(valid)])
        runtime = MultiAgentRuntime(settings())
        decision = await Supervisor(model, runtime).decide(
            "问题", [], remaining_slots=0, can_dispatch=False
        )
        assert decision.action == "finish"
        assert runtime.steps == 2
        retry = next(
            event for event in runtime.events if event.event_type == "supervisor.retry"
        )
        assert retry.details["reason_code"] == "missing_tool_call"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("invalid_response", "reason_code"),
    [
        (
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "first",
                        "name": "submit_supervisor_decision",
                        "args": {
                            "action": "finish",
                            "rationale": "one",
                            "assignments": [],
                            "sufficient": True,
                            "gaps": [],
                        },
                    },
                    {
                        "id": "second",
                        "name": "submit_supervisor_decision",
                        "args": {
                            "action": "finish",
                            "rationale": "two",
                            "assignments": [],
                            "sufficient": True,
                            "gaps": [],
                        },
                    },
                ],
            ),
            "multiple_tool_calls",
        ),
        (
            decision_call(
                {
                    "action": "finish",
                    "rationale": "缺少具体缺口",
                    "assignments": [],
                    "sufficient": False,
                    "gaps": [],
                }
            ),
            "invalid_arguments",
        ),
    ],
)
def test_supervisor_retry_classifies_invalid_decisions(
    invalid_response, reason_code
):
    async def scenario():
        model = ScriptedModel([invalid_response, valid_finish_call()])
        runtime = MultiAgentRuntime(settings())
        decision = await Supervisor(model, runtime).decide(
            "问题", [], remaining_slots=0, can_dispatch=False
        )
        assert decision.sufficient
        retry = next(
            event for event in runtime.events if event.event_type == "supervisor.retry"
        )
        assert retry.details["reason_code"] == reason_code

    asyncio.run(scenario())


def test_supervisor_timeout_dispatches_followups_without_second_provider_call():
    class TimeoutModel(ScriptedModel):
        def __init__(self):
            super().__init__([])
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            await asyncio.sleep(0.05)
            raise AssertionError("timeout call unexpectedly completed")

    async def scenario():
        current_settings = settings()
        current_settings.multi_agent_call_timeout_seconds = 0.01
        runtime = MultiAgentRuntime(current_settings)
        model = TimeoutModel()
        outcome = await Supervisor(model, runtime).replan(
            "2025 AI 热点",
            partial_history(),
            current_date="2026-09-06",
            timezone="Asia/Shanghai",
            remaining_slots=3,
            max_assignments=3,
            circuit_open=False,
        )
        assert model.calls == 1
        assert outcome.circuit_open
        assert outcome.fallback_reason == "provider_timeout"
        assert outcome.decision.action == "dispatch"
        assert [
            item.parent_ids for item in outcome.decision.assignments
        ] == [["r1"], ["r1"], ["r2"]]
        assert not any(
            event.event_type == "supervisor.retry" for event in runtime.events
        )

    asyncio.run(scenario())


def test_gap_followups_create_one_assignment_per_exact_gap():
    history = partial_history()[:1]
    history[0]["gaps"] = [f"缺口 {index}" for index in range(1, 6)]
    history[0]["excluded_scope"] = ["排除融资"]
    history[0]["source_guidance"] = ["官方来源", "官方来源"]

    followups = build_gap_followups(history, max_assignments=3)

    assert [item.required_outputs for item in followups] == [
        ["缺口 1"],
        ["缺口 2"],
        ["缺口 3"],
    ]
    assert [item.objective for item in followups] == [
        "补充并核实：缺口 1",
        "补充并核实：缺口 2",
        "补充并核实：缺口 3",
    ]
    assert all(item.parent_ids == ["r1"] for item in followups)
    assert followups[0].excluded_scope == ["排除融资", "不重复已确认内容"]
    assert followups[0].source_guidance == [
        "官方来源",
        "优先官方或一手来源",
    ]


def test_broad_supervisor_draft_cannot_replace_exact_parent_gap():
    history = partial_history()[:1]
    preferred = [
        AssignmentDraft(
            objective="整理全球 AI 模型热点",
            required_outputs=["完成模型整理"],
            parent_ids=["r1"],
        )
    ]

    followups = build_gap_followups(
        history,
        max_assignments=1,
        preferred_assignments=preferred,
    )

    assert followups[0].objective == "补充并核实：Claude 官方公告缺失"
    assert followups[0].required_outputs == ["Claude 官方公告缺失"]
    assert followups[0].parent_ids == ["r1"]


def test_open_supervisor_circuit_replans_without_calling_provider():
    class ForbiddenModel(ScriptedModel):
        async def ainvoke(self, messages):
            raise AssertionError("open circuit must not call Provider")

    async def scenario():
        runtime = MultiAgentRuntime(settings())
        outcome = await Supervisor(ForbiddenModel([]), runtime).replan(
            "问题",
            partial_history(),
            current_date="2026-09-06",
            timezone="Asia/Shanghai",
            remaining_slots=2,
            max_assignments=2,
            circuit_open=True,
        )
        assert outcome.decision.action == "dispatch"
        assert len(outcome.decision.assignments) == 2
        assert outcome.circuit_open
        assert outcome.fallback_reason == "circuit_open"

    asyncio.run(scenario())


def test_supervisor_receives_authoritative_application_date():
    async def scenario():
        model = ScriptedModel([valid_finish_call()])
        outcome = await Supervisor(model, MultiAgentRuntime(settings())).replan(
            "2025 AI 热点",
            partial_history(),
            current_date="2026-09-06",
            timezone="Asia/Shanghai",
            remaining_slots=3,
            max_assignments=3,
            circuit_open=False,
        )
        assert outcome.decision.action == "finish"
        prompt = "\n".join(str(message.content) for message in model.messages[0])
        assert '"application_current_date": "2026-09-06"' in prompt
        assert '"application_timezone": "Asia/Shanghai"' in prompt

    asyncio.run(scenario())


def test_supervisor_failed_review_preserves_concrete_researcher_gaps():
    history = [
        {
            "assignment": {"id": "r1"},
            "result": {
                "status": "partial",
                "gaps": ["技术发布日期未确认", "政策原文未取得"],
            },
        },
        {
            "assignment": {"id": "r2"},
            "result": {
                "status": "blocked",
                "gaps": ["政策原文未取得"],
            },
        },
    ]

    async def scenario():
        runtime = MultiAgentRuntime(settings())
        decision = await Supervisor(
            ScriptedModel([AIMessage(content="plain"), AIMessage(content="plain")]),
            runtime,
        ).decide("问题", history, remaining_slots=0, can_dispatch=False)
        assert decision.action == "finish"
        assert not decision.sufficient
        assert decision.gaps == ["技术发布日期未确认", "政策原文未取得"]
        fallback = next(
            event
            for event in runtime.events
            if event.event_type == "supervisor.fallback"
        )
        assert fallback.details["reason_code"] == "missing_tool_call"

    asyncio.run(scenario())


def test_supervisor_final_round_rejects_dispatch_and_falls_back_to_finish():
    async def scenario():
        dispatch = {
            "action": "dispatch",
            "rationale": "继续",
            "assignments": [
                {
                    "objective": "新增研究",
                    "required_outputs": ["结果"],
                    "excluded_scope": [],
                    "source_guidance": [],
                    "parent_ids": [],
                }
            ],
            "sufficient": False,
            "gaps": [],
        }
        model = ScriptedModel([decision_call(dispatch), decision_call(dispatch)])
        runtime = MultiAgentRuntime(settings())
        decision = await Supervisor(model, runtime).decide(
            "问题", [], remaining_slots=3, can_dispatch=False
        )
        assert decision.action == "finish"
        assert not decision.sufficient
        assert decision.gaps == ["Supervisor 无法形成有效的初始研究分工"]
        retry = next(
            event for event in runtime.events if event.event_type == "supervisor.retry"
        )
        assert retry.details["reason_code"] == "dispatch_not_allowed"

    asyncio.run(scenario())
