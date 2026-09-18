"""DeepResearch 命令行入口（兼容 deeptrace 命令）。"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from deeptrace.application.agent_adapter import HarnessResearchRunner
from deeptrace.config import Settings
from deeptrace.domain import normalize_research_mode
from deeptrace.models import RunEvent
from deeptrace.observability import format_role_usage
from deeptrace.runtime.models import RunRecord


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deepresearch",
        description="运行 DeepResearch Workflow、Plan-and-Execute 或 Multi-Agent 研究 Agent",
    )
    parser.add_argument("question", help="研究问题")
    parser.add_argument(
        "--mode",
        default="workflow",
        help=(
            "workflow 固定并行研究流程；plan_execute 规划、执行与有界重规划；"
            "multi_agent 主管协调多个独立研究员（旧值 basic/deep 自动映射）"
        ),
    )
    return parser


def _print_event(event: RunEvent) -> None:
    print(event.message)


def _exit_code(status: str) -> int:
    return 0 if status == "completed" else 2


async def _run(question: str, mode: str = "workflow") -> int:
    canonical = normalize_research_mode(mode)
    runner = HarnessResearchRunner(Settings.from_env())
    run_id = uuid.uuid4().hex[:12]
    run = RunRecord(
        id=run_id,
        question=question,
        mode=canonical,
        thread_id=run_id,
        created_at=datetime.now(UTC),
    )
    result = await runner(run, on_event=_print_event)
    print("\n最终答案")
    print(result.answer)
    print("\n来源")
    if result.sources:
        for index, source in enumerate(result.sources, start=1):
            print(f"{index}. {source}")
    else:
        print("无成功抓取来源")
    print(f"\n状态：{result.status}；模型调用步数：{result.steps}")
    print("\n" + format_role_usage(result.role_usage))
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
        return asyncio.run(_run(args.question, args.mode))
    except (RuntimeError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
