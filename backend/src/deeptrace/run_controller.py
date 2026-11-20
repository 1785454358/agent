"""Run one research turn through the controller runtime for measurement."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

from deeptrace.application import assembly
from deeptrace.config import Settings
from deeptrace.domain import ResearchInput
from deeptrace.harness.batch_research import build_batch_research_graph
from deeptrace.harness.token_budget import TokenBudgetConfig
from deeptrace.research.runtime import run_controller_research


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deepresearch-controller")
    parser.add_argument("question", help="研究问题")
    parser.add_argument("--max-tasks", type=int, default=6)
    parser.add_argument("--max-parallel", type=int, default=4)
    return parser


async def _run(question: str, max_tasks: int, max_parallel: int) -> int:
    settings = Settings.from_env()
    bundle = assembly.build_harness_runtime(settings, runs_dir=Path("runs"))
    try:
        run_id = uuid.uuid4().hex[:12]
        context = bundle.context_factory(run_id)
        token_budget = TokenBudgetConfig(
            context_tokens=settings.model_context_tokens,
            output_reserve_tokens=settings.openai_max_tokens or 4096,
            safety_tokens=settings.context_safety_tokens,
        )
        executor = build_batch_research_graph(
            token_budget=token_budget,
            source_target=settings.research_source_target,
        )
        now = datetime.now(UTC)
        research_input = ResearchInput(
            run_id=run_id,
            thread_id=run_id,
            question=question,
            current_date=now.date().isoformat(),
            timezone=str(now.tzinfo),
        )
        outcome, verification = await run_controller_research(
            research_input=research_input,
            context=context,
            topic_graph=executor,
            max_tasks=max_tasks,
            max_parallel=max_parallel,
        )
        print(f"状态：{outcome.termination_reason}")
        coverage = outcome.coverage
        if coverage:
            covered = sum(item.status == "covered" for item in coverage.items)
            print(f"覆盖：{covered}/{len(coverage.items)}")
            for item in coverage.items:
                print(f"  {item.requirement_id}: {item.status}")
        if verification is not None:
            print(f"验证通过 Claim：{len(verification.accepted_claims)}")
            print(f"建议动作：{verification.recommended_action.value}")
            for issue in verification.issues[:10]:
                print(f"  [issue] {issue}")
        print(f"证据数：{len(outcome.evidence_ids)}")
        for identity in outcome.evidence_ids:
            try:
                record = await context.evidence_store.get(
                    context.workspace_id, identity
                )
                print(f"  [{record.canonical_url}] {record.title[:60]}")
            except Exception:  # noqa: BLE001 - report best effort
                continue
        return 0 if outcome.termination_reason == "completed" else 2
    finally:
        await bundle.aclose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args.question, args.max_tasks, args.max_parallel))
    except (RuntimeError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
