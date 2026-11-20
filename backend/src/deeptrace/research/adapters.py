"""Convert legacy planner payloads into the typed contract and plan."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping

from deeptrace.domain.coverage import ResearchRequirement
from deeptrace.research.contract import (
    ContractBudget,
    ResearchContract,
    SourcePolicy,
)
from deeptrace.research.plan import (
    PlanTask,
    ResearchPlan,
    TaskBudget,
    TaskType,
)

DISCOVER_CAPABILITIES = ("search_web", "fetch_page", "read_evidence")


def build_discovery_tasks(
    *,
    requirements: Iterable[ResearchRequirement],
    queries: Iterable[str],
    query_targets: Mapping[str, Iterable[str]],
    first_task_number: int = 1,
    source_policy: str = "general",
) -> tuple[PlanTask, ...]:
    """Build explicitly assigned work without adding any acceptance obligations."""
    queries = tuple(queries)
    if not queries or len(queries) != len(set(queries)):
        raise ValueError("discovery queries must be nonempty and unique")
    if set(queries) != set(query_targets):
        raise ValueError("each discovery query requires an explicit target assignment")
    allowed = {requirement.id for requirement in requirements}
    tasks = []
    for index, query in enumerate(queries, first_task_number):
        targets = tuple(query_targets[query])
        if not targets or len(targets) != len(set(targets)) or not set(targets) <= allowed:
            raise ValueError("discovery targets must be nonempty, unique and known")
        tasks.append(PlanTask(
            id=f"t{index}", type=TaskType.DISCOVER,
            objective=f"Gather and verify original sources for: {query}"[:500],
            in_scope="Requirements assigned to this research task",
            out_of_scope="Final answer synthesis and other tasks",
            requirement_ids=targets, capabilities=DISCOVER_CAPABILITIES,
            query_seeds=(query,), expected_output="Findings with host-verified source spans",
            acceptance=("Every assigned requirement has a verified support",),
            # Three target originals may require a landing page plus full text.
            # These are actual fetches, still charged to the run tool/page cap.
            budget=TaskBudget(max_calls=2, max_pages=6 if source_policy == "research_results" else 3),
        ))
    return tuple(tasks)


def build_contract_and_plan(
    *,
    run_id: str,
    question: str,
    requirements: Iterable[ResearchRequirement],
    queries: Iterable[str],
    query_targets: Mapping[str, list[str]] | None = None,
    source_policy: str = "general",
    source_domains: Iterable[str] = (),
    publication_years: Iterable[int] = (),
    budget: ContractBudget | None = None,
) -> tuple[ResearchContract, ResearchPlan]:
    """One research task per query; dependencies stay empty for legacy plans."""
    requirements = tuple(requirements)
    if not requirements:
        raise ValueError("a research plan requires sealed requirements")
    queries = tuple(dict.fromkeys(query.strip() for query in queries if query.strip()))
    if not queries:
        raise ValueError("a research plan requires at least one query")

    target_by_query = dict(query_targets or {})
    requirement_ids = {requirement.id for requirement in requirements}
    unknown = {
        requirement_id
        for targets in target_by_query.values()
        for requirement_id in targets
        if requirement_id not in requirement_ids
    }
    if unknown:
        raise ValueError(f"query targets reference unknown requirements: {sorted(unknown)}")

    contract = ResearchContract(
        run_id=run_id,
        goal=question,
        requirements=requirements,
        source_policy=SourcePolicy(
            mode=source_policy,
            domains=tuple(source_domains),
            publication_years=tuple(publication_years),
        ),
        budget=budget or ContractBudget(),
    )
    assignments = [
        list(
            target_by_query.get(query)
            or [requirement.id for requirement in requirements]
        )
        for query in queries
    ]
    covered = {
        requirement_id
        for assigned in assignments
        for requirement_id in assigned
    }
    uncovered = [
        requirement.id for requirement in requirements if requirement.id not in covered
    ]
    if uncovered and assignments:
        assignments[0] = list(dict.fromkeys([*assignments[0], *uncovered]))

    tasks = build_discovery_tasks(
        requirements=requirements, queries=queries,
        query_targets=dict(zip(queries, assignments)),
        source_policy=source_policy,
    )
    plan_id = f"plan-{contract.run_id}"
    if len(plan_id) > 128:
        plan_id = "plan-" + hashlib.sha256(contract.run_id.encode("utf-8")).hexdigest()
    plan = ResearchPlan(
        plan_id=plan_id,
        run_id=run_id,
        contract_revision=contract.revision,
        tasks=tuple(tasks),
        stop_conditions=("All acceptance requirements are covered",),
        replan_triggers=("A requirement remains missing after this wave",),
    )
    return contract, plan
