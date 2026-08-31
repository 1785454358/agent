"""DeepTrace 命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from deeptrace.agent import build_real_agent
from deeptrace.config import Settings
from deeptrace.token_metrics import format_token_summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deeptrace",
        description="运行 DeepTrace 阶段 2 深度研究 Agent",
    )
    parser.add_argument("question", help="研究问题")
    return parser


async def _run(question: str) -> int:
    agent = build_real_agent(Settings.from_env(), on_event=print)
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
    print("\n" + format_token_summary(result.token_metrics))
    return 0 if result.status == "completed" else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args.question))
    except (RuntimeError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
