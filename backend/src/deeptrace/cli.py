"""DeepTrace 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from deeptrace import build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent
from deeptrace.observability import format_role_usage, format_token_summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deeptrace",
        description="运行 DeepTrace 规划式深度研究 Agent",
    )
    parser.add_argument("question", help="研究问题")
    return parser


def _print_event(event: RunEvent) -> None:
    print(event.message)


def _exit_code(status: str) -> int:
    return 0 if status == "completed" else 2


def _format_stage_four_summary(result: object) -> str:
    evidence = getattr(result, "evidence_location_counts", {})
    verdicts = getattr(result, "verdict_counts", {})
    evidence_text = ", ".join(
        f"{key}={value}" for key, value in evidence.items()
    ) or "无"
    verdict_text = ", ".join(
        f"{key}={value}" for key, value in verdicts.items()
    ) or "无"
    return (
        "阶段 4 核验摘要\n"
        f"Evidence：{evidence_text}\n"
        f"Verdict：{verdict_text}\n"
        f"Gap={getattr(result, 'verification_gap_count', 0)}；"
        f"补搜轮次={getattr(result, 'supplement_rounds', 0)}；"
        f"使用 Claim={len(getattr(result, 'used_claim_ids', []))}；"
        f"使用来源={len(getattr(result, 'sources', []))}"
    )


async def _run(question: str) -> int:
    agent = build_real_agent(Settings.from_env(), on_event=_print_event)
    try:
        result = await agent.arun(question)
    finally:
        await agent.aclose()
    print("\n最终答案")
    print(result.answer)
    print("\n来源")
    if result.sources:
        for index, source in enumerate(result.sources, start=1):
            print(f"{index}. {source}")
    else:
        print("无成功抓取来源")
    print(f"\n状态：{result.status}；模型调用步数：{result.steps}")
    print("\n" + _format_stage_four_summary(result))
    print("\n" + format_token_summary(result.token_metrics))
    print(format_role_usage(result.role_usage))
    cost = (
        f"${result.estimated_cost_usd}"
        if result.estimated_cost_usd is not None
        else "unavailable"
    )
    print(f"估算模型费用：{cost}")
    return _exit_code(result.status)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args.question))
    except (RuntimeError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
