"""ResearchPilot 命令行入口（兼容 deeptrace 命令）。"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from deeptrace import build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent
from deeptrace.observability import format_role_usage


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="researchpilot",
        description="运行 ResearchPilot Basic、Deep 或 Multi-Agent 研究 Agent",
    )
    parser.add_argument("question", help="研究问题")
    parser.add_argument(
        "--mode",
        choices=("basic", "deep", "multi_agent"),
        default="basic",
        help=(
            "basic 一轮研究；deep 规划、ReAct 执行与重规划；"
            "multi_agent 主管协调多个独立研究员"
        ),
    )
    return parser


def _print_event(event: RunEvent) -> None:
    print(event.message)


def _exit_code(status: str) -> int:
    return 0 if status == "completed" else 2


async def _run(question: str, mode: str = "basic") -> int:
    agent = build_real_agent(Settings.from_env(), on_event=_print_event, mode=mode)
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
