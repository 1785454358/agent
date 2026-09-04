"""Benchmark one Basic research run with its event timeline."""

from __future__ import annotations

import asyncio
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from deeptrace import build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent
from deeptrace.observability import format_role_usage

QUESTION = "2024 年 AI Agent 领域有哪些热点新闻？"


async def main() -> None:
    started = time.perf_counter()

    def on_event(event: RunEvent) -> None:
        elapsed = time.perf_counter() - started
        print(f"[{elapsed:7.1f}s] {event.event_type}: {event.message}", flush=True)

    agent = build_real_agent(Settings.from_env(), on_event=on_event)
    try:
        result = await agent.arun(QUESTION)
    finally:
        await agent.aclose()
    total = time.perf_counter() - started

    print("\n" + "=" * 60)
    print("研究问题：", QUESTION)
    print("\n最终答案\n" + result.answer)
    print("\n来源")
    for index, source in enumerate(result.sources, start=1):
        print(f"  {index}. {source}")
    print("\n各环节耗时")
    for stage, seconds in result.stage_seconds.items():
        print(f"  {stage:<20} {seconds:7.1f}s")
    print(f"  {'TOTAL':<20} {total:7.1f}s")
    print("\n" + format_role_usage(result.role_usage))
    print(
        f"状态：{result.status}；步数：{result.steps}；"
        f"终止原因：{result.termination_reason}"
    )


if __name__ == "__main__":
    asyncio.run(main())
