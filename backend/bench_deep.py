"""A bounded real-provider Deep smoke test; never prints credentials."""

import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

from deeptrace import build_real_agent
from deeptrace.config import Settings


async def main(args):
    config = replace(
        Settings.from_env(),
        deep_max_tool_calls=args.tool_calls,
        deep_max_tasks=2,
        deep_max_steps=6,
        deep_max_replans=1,
    )
    started = time.monotonic()

    def event(item):
        print(
            f"[{time.monotonic() - started:.1f}s] {item.event_type}: {item.message}",
            flush=True,
        )

    agent = build_real_agent(config, on_event=event, mode="deep")
    try:
        result = await agent.arun(args.question)
    finally:
        await agent.aclose()
    payload = {
        "status": result.status,
        "termination_reason": result.termination_reason,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "usage": result.provider_usage.model_dump(),
        "role_usage": result.role_usage.model_dump(),
        "sources": result.sources,
        "answer": result.answer,
        "events": [e.model_dump() for e in result.events],
    }
    print(
        json.dumps(
            {k: v for k, v in payload.items() if k not in {"answer", "events"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default="依据 ReAct 原始论文的网页，简要说明 ReAct 的核心机制与一项局限。只规划一个任务，阅读一到两个来源即可。",
    )
    parser.add_argument("--tool-calls", type=int, default=8)
    parser.add_argument("--output")
    asyncio.run(main(parser.parse_args()))
