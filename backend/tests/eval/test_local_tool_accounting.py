import asyncio
import json
from dataclasses import replace

from deeptrace.domain import ResearchMode
from deeptrace.eval.env import build_eval_context
from deeptrace.eval.scripted import ScriptedResearchModel
from deeptrace.harness.agent_executor import build_research_agent_graph
from harness.test_record_findings_loop import seed, task_for
from langchain_core.messages import AIMessage, ToolMessage
from strategies.fixtures import TENANT_ID
from tests.eval.test_env import _corpus


def test_finish_is_counted_in_total_without_consuming_gateway_budget():
    async def run():
        env = build_eval_context(_corpus(), model_gateway=ScriptedResearchModel(), run_id="run-1")
        await env.events.emit("agent.local_tool", {
            "tool": "finish_research", "executed": True, "ok": False,
        })
        totals = env.usage_snapshot()["agent_tools"]
        assert totals.get("finish_research_calls") == 1
        assert totals["total_executed_calls"] == 1
        assert totals["gateway_calls"] == 0
    asyncio.run(run())


def test_last_record_call_is_measured_without_another_model_turn():
    async def run():
        env = build_eval_context(
            _corpus(), model_gateway=ScriptedResearchModel(), run_id="run-1"
        )
        record, _ = await seed(env)

        class Reader:
            async def invoke(self, *, role, messages, tools=None):
                returned = [m for m in messages if isinstance(m, ToolMessage)]
                if not returned:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "read",
                                "name": "read_evidence",
                                "args": {"evidence_id": record.id},
                            }
                        ],
                    )
                ref = json.loads(json.loads(returned[-1].content)["preview"])[
                    "passages"
                ][0]["ref"]
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "note",
                            "name": "record_findings",
                            "args": {
                                "findings": [
                                    {
                                        "claim": "Context required",
                                        "refs": [ref],
                                        "confidence": 0.8,
                                    }
                                ]
                            },
                        }
                    ],
                )

        # seed uses the test workspace; align both reads and records with it.
        result = await build_research_agent_graph(max_iterations=2).ainvoke(
            {"topic_input": task_for(ResearchMode.WORKFLOW, record)},
            context=replace(
                env.context, workspace_id=TENANT_ID, model_gateway=Reader()
            ),
        )
        assert result["outcome"].executed_steps == 2
        assert env.tool_calls == 1
        assert env.usage_snapshot()["agent_tools"]["record_findings_calls"] == 1
        actual = env.trajectory.snapshot(full=True)["agent_tool_results"]
        assert actual[-1]["result"]["ok"]
        assert actual[-1]["tool"] == "record_findings"

    asyncio.run(run())
