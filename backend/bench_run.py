"""DeepTrace 单次运行基准：事件时间线、各环节耗时与按角色 token。"""

from __future__ import annotations

import asyncio
import sys
import time
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

from deeptrace import build_real_agent
from deeptrace.config import Settings
from deeptrace.models import RunEvent
from deeptrace.observability import (
    format_round_metrics,
    format_token_summary,
)

QUESTION = "2024 年 AI Agent 领域有哪些热点新闻？"

PHASES = {
    "planning.completed": "Planner 规划",
    "planning.fallback": "Planner 降级",
    "task.started": "任务启动/切换",
    "tools.completed": "Researcher 研究轮（LLM+搜索/抓取/压缩）",
    "budget.reached": "预算停止",
    "task.failed": "任务失败",
    "task.completed": "任务完结",
    "writing.completed": "Writer 写作",
    "writing.fallback": "Writer 降级",
    "run.completed": "运行收尾",
}


async def main() -> None:
    start = time.perf_counter()
    marks: list[tuple[float, str, str]] = []

    def on_event(event: RunEvent) -> None:
        elapsed = time.perf_counter() - start
        marks.append((elapsed, event.event_type, event.message))
        print(f"[{elapsed:7.1f}s] {event.event_type}: {event.message}", flush=True)

    agent = build_real_agent(Settings.from_env(), on_event=on_event)
    try:
        result = await agent.arun(QUESTION)
    finally:
        await agent.aclose()
    total = time.perf_counter() - start

    print("\n" + "=" * 60)
    print("研究问题：", QUESTION)
    print("\n最终答案")
    print(result.answer)
    print("\n来源")
    for index, source in enumerate(result.sources, start=1):
        print(f"  {index}. {source}")

    print("\n" + "=" * 60)
    print("各环节耗时（相邻事件间隔归入后一事件所属环节）")
    phase_seconds: dict[str, float] = defaultdict(float)
    phase_seconds["启动/依赖组装（含 BGE-M3 加载）"] += (
        marks[0][0] if marks else total
    )
    prev = marks[0][0] if marks else 0.0
    for elapsed, event_type, _message in marks[1:]:
        phase = PHASES.get(event_type, event_type)
        phase_seconds[phase] += elapsed - prev
        prev = elapsed
    phase_seconds["结果组装/收尾"] += total - prev
    for phase, seconds in sorted(phase_seconds.items(), key=lambda kv: -kv[1]):
        print(f"  {seconds:7.1f}s  {phase}  ({seconds / total:.1%})")
    print(f"  {total:7.1f}s  总耗时")

    usage = result.role_usage
    print("\n" + "=" * 60)
    print("各环节 Provider Token（真实 API usage）")
    rows = [
        ("Planner", usage.planner),
        ("Researcher", usage.researcher),
        ("Compression", usage.compression),
        ("Writer", usage.writer),
    ]
    total_input = 0
    total_output = 0
    for name, item in rows:
        print(
            f"  {name:<16} input={item.input_tokens:>8,}  "
            f"output={item.output_tokens:>8,}  total={item.total_tokens:>8,}"
        )
        total_input += item.input_tokens
        total_output += item.output_tokens
    print(
        f"  {'TOTAL':<16} input={total_input:>8,}  "
        f"output={total_output:>8,}  total={total_input + total_output:>8,}"
    )

    print(f"\n状态：{result.status}；步数：{result.steps}；终止原因：{result.termination_reason}")
    print(f"总耗时：{total:.1f}s")
    print()
    for metrics in result.token_metrics:
        print(format_round_metrics(metrics))
    print(format_token_summary(result.token_metrics))
    cost = (
        f"${result.estimated_cost_usd}"
        if result.estimated_cost_usd is not None
        else "unavailable（未配置单价）"
    )
    print(f"估算模型费用：{cost}")


if __name__ == "__main__":
    asyncio.run(main())
