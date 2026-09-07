"""Public adapter for the LangGraph Supervisor Multi-Agent workflow."""

from __future__ import annotations

import asyncio
from datetime import datetime

from deeptrace.models import AgentResult, UsageBreakdown
from deeptrace.multi_agent.graph import build_multi_agent_graph
from deeptrace.multi_agent.nodes import MultiAgentWorkflowNodes
from deeptrace.multi_agent.runtime import MultiAgentRuntime
from deeptrace.multi_agent.supervisor import Supervisor
from deeptrace.observability import estimate_usage_cost


class SupervisorResearchAgent:
    """Run the compiled research graph and adapt its final public result."""

    def __init__(
        self,
        *,
        model,
        writer,
        resources,
        settings,
        on_event=None,
        supervisor=None,
        researcher_factory=None,
        graph=None,
    ) -> None:
        self.model = model
        self.writer = writer
        self.resources = resources
        self.settings = settings
        self.on_event = on_event
        self._supervisor = supervisor
        self._researcher_factory = researcher_factory
        self.graph = graph or build_multi_agent_graph()

    async def arun(self, question: str) -> AgentResult:
        question = question.strip()
        if not question:
            raise ValueError("问题不能为空")

        runtime = MultiAgentRuntime(self.settings, self.on_event)
        supervisor = self._supervisor or Supervisor(self.model, runtime)
        nodes = MultiAgentWorkflowNodes(
            model=self.model,
            writer=self.writer,
            resources=self.resources,
            settings=self.settings,
            runtime=runtime,
            supervisor=supervisor,
            researcher_factory=self._researcher_factory,
        )
        now = datetime.now().astimezone()
        initial = {
            "question": question,
            "current_date": now.date().isoformat(),
            "timezone": str(now.tzinfo),
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
            "role_usage": UsageBreakdown(),
            "stage_seconds": {},
            "step_count": 0,
            "max_supervisor_iterations": int(
                self.settings.multi_agent_max_supervisor_rounds
            ),
            "sources_before_batch": [],
        }
        final = await self.graph.ainvoke(
            initial,
            {"configurable": {"service": nodes}},
        )

        role_usage = final.get("role_usage", runtime.role_usage)
        sources = list(final.get("final_sources", []))
        reason = final.get("termination_reason", "no_sources")
        if reason == "completed":
            status = "completed"
        elif sources or final.get("research_context"):
            status = "partial"
        else:
            status = "failed"
        return AgentResult(
            status=status,
            answer=final.get("final_answer", ""),
            sources=sources,
            steps=int(final.get("step_count", runtime.steps)),
            events=list(final.get("events", runtime.events)),
            termination_reason=reason,
            search_queries=list(getattr(self.resources, "queries", [])),
            provider_usage=role_usage.total,
            role_usage=role_usage,
            estimated_cost_usd=estimate_usage_cost(
                role_usage.total,
                getattr(self.settings, "input_cost_per_million", None),
                getattr(self.settings, "output_cost_per_million", None),
            ),
            stage_seconds=dict(
                final.get("stage_seconds", runtime.stage_seconds)
            ),
            unresolved_gaps=list(final.get("final_gaps", [])),
        )

    async def aclose(self) -> None:
        await self.resources.aclose()

    def run(self, question: str) -> AgentResult:
        return asyncio.run(self.arun(question))
