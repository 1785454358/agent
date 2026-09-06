import asyncio

from deeptrace.multi_agent.graph import build_multi_agent_graph


def graph_state():
    return {
        "question": "问题",
        "current_date": "2026-09-06",
        "timezone": "Asia/Shanghai",
        "tasks": {},
        "ready_task_ids": [],
        "next_task_number": 1,
        "supervisor_iteration": 0,
        "supervisor_circuit_open": False,
        "first_batch": True,
        "final_sufficient": False,
        "final_gaps": [],
        "termination_reason": "",
        "research_context": "",
        "final_sources": [],
        "final_answer": "",
        "events": [],
        "role_usage": None,
        "stage_seconds": {},
        "step_count": 0,
        "max_supervisor_iterations": 3,
        "sources_before_batch": [],
    }


def test_graph_runs_plan_execute_replan_until_writer():
    async def scenario():
        calls = []

        class Nodes:
            async def plan_node(self, state):
                calls.append("plan")
                return {"ready_task_ids": ["r1"]}

            async def execute_node(self, state):
                calls.append("execute")
                return {"ready_task_ids": []}

            async def replan_node(self, state):
                calls.append("replan")
                if calls.count("replan") == 1:
                    return {
                        "ready_task_ids": ["r2"],
                        "termination_reason": "",
                    }
                return {
                    "ready_task_ids": [],
                    "termination_reason": "completed",
                }

            async def writer_node(self, state):
                calls.append("writer")
                return {"final_answer": "完成"}

        final = await build_multi_agent_graph().ainvoke(
            graph_state(), {"configurable": {"service": Nodes()}}
        )
        assert calls == [
            "plan",
            "execute",
            "replan",
            "execute",
            "replan",
            "writer",
        ]
        assert final["termination_reason"] == "completed"

    asyncio.run(scenario())


def test_graph_routes_planning_failure_directly_to_writer():
    async def scenario():
        calls = []

        class Nodes:
            async def plan_node(self, state):
                calls.append("plan")
                return {
                    "ready_task_ids": [],
                    "termination_reason": "planning_failed",
                }

            async def execute_node(self, state):
                raise AssertionError("planning failure must not execute")

            async def replan_node(self, state):
                raise AssertionError("planning failure must not replan")

            async def writer_node(self, state):
                calls.append("writer")
                return {"final_answer": "降级结果"}

        final = await build_multi_agent_graph().ainvoke(
            graph_state(), {"configurable": {"service": Nodes()}}
        )
        assert calls == ["plan", "writer"]
        assert final["termination_reason"] == "planning_failed"

    asyncio.run(scenario())


def test_graph_requires_node_service():
    async def scenario():
        try:
            await build_multi_agent_graph().ainvoke(graph_state())
        except RuntimeError as exc:
            assert "MultiAgentWorkflowNodes" in str(exc)
        else:
            raise AssertionError("missing node service should fail clearly")

    asyncio.run(scenario())
