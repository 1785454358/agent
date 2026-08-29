from __future__ import annotations

import argparse
from collections.abc import Sequence

import httpx
from openai import OpenAI
from tavily import TavilyClient

from deeptrace.agent import ResearchAgent
from deeptrace.config import Settings
from deeptrace.tools import ToolContext


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deeptrace",
        description="Run the DeepTrace stage 1 web research agent.",
    )
    parser.add_argument("question", help="Research question")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        model_client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        with httpx.Client(
            timeout=15.0,
            follow_redirects=False,
            headers={"User-Agent": "DeepTrace-Stage01/0.1"},
        ) as http_client:
            context = ToolContext(
                tavily=TavilyClient(api_key=settings.tavily_api_key),
                http=http_client,
                max_page_chars=settings.max_page_chars,
            )
            agent = ResearchAgent(
                model_client=model_client,
                settings=settings,
                tool_context=context,
                on_event=print,
            )
            result = agent.run(args.question)
    except (RuntimeError, ValueError) as exc:
        print(f"运行失败：{exc}")
        return 1

    print("\n最终答案")
    print(result.answer)
    print("\n来源")
    if result.sources:
        for index, source in enumerate(result.sources, start=1):
            print(f"{index}. {source}")
    else:
        print("无成功抓取来源")

    print(f"\n状态：{result.status}；模型调用步数：{result.steps}")
    return 0 if result.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
