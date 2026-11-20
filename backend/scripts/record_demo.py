"""Record a real new conversation against a running DeepResearch API.

Run from backend: uv run python scripts/record_demo.py --base-url http://127.0.0.1:8001
The target must serve the built dashboard. No API responses are mocked.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import re
import time

from playwright.async_api import async_playwright

DEFAULT_QUESTION = (
    "依据 Python 官方文档，对比 asyncio.gather 与 TaskGroup 在异常传播、"
    "其他子任务取消和适用场景上的区别。请用表格总结，并明确 Python 版本条件。"
)


def validate_result(result: dict, browser_errors: list[str]) -> None:
    if result.get("status") != "completed":
        raise ValueError(f"Demo did not complete: {result.get('status')}")
    if len(result.get("answer", "").strip()) < 20:
        raise ValueError("Demo answer is empty or too short")
    sources = result.get("sources") or []
    markers = [int(value) for value in re.findall(r"\[(\d+)\]", result["answer"])]
    if not sources or not markers or any(value < 1 or value > len(sources) for value in markers):
        raise ValueError("Demo requires sources and valid numbered citations")
    if browser_errors:
        raise ValueError("Browser reported uncaught JavaScript errors")


async def record(args) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = args.base_url.rstrip("/")
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=str(output / "video"),
            record_video_size={"width": 1440, "height": 1000},
        )
        page = await context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            await page.goto(base)
            await page.get_by_role("button", name="新研究", exact=True).click()
            await page.get_by_role("combobox", name="研究模式").select_option(args.mode)
            await page.screenshot(path=str(output / "01-new-conversation.png"))
            await page.locator(".topbar input").fill(args.question)
            started = time.monotonic()
            async with page.expect_response(
                lambda r: r.url == base + "/researches" and r.request.method == "POST"
            ) as created_response:
                await page.get_by_role("button", name="开始研究", exact=True).click()
            response = await created_response.value
            if not response.ok:
                raise ValueError(f"Create run failed: HTTP {response.status}")
            created = await response.json()
            run_id = created["id"]
            print(f"run_id={run_id}; output={output}", flush=True)
            previous = None
            async with asyncio.timeout(args.timeout):
                while True:
                    response = await context.request.get(f"{base}/researches/{run_id}")
                    if not response.ok:
                        raise ValueError(f"Read run failed: HTTP {response.status}")
                    result = await response.json()
                    progress = (result["status"], len(result.get("events", [])))
                    if progress != previous:
                        print(f"status={progress[0]}; events={progress[1]}", flush=True)
                        previous = progress
                    if result["status"] in {"completed", "partial", "failed", "cancelled"}:
                        break
                    await asyncio.sleep(2)
            elapsed = time.monotonic() - started
            (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
            (output / "answer.md").write_text(result.get("answer", ""), encoding="utf8")
            summary = {
                "run_id": run_id, "status": result["status"], "mode": args.mode,
                "selected_mode": result.get("selected_mode"), "routing_reason": result.get("routing_reason"),
                "elapsed_seconds": round(elapsed, 2), "answer_chars": len(result.get("answer", "")),
                "sources": len(result.get("sources", [])), "browser_errors": errors,
                "usage": result.get("usage"),
            }
            (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(output / "02-result.png"), full_page=True)
            # Show the actual answer and sources in the recording after the live process.
            for selector in [".report-block", ".report-block pre", ".report-block table", ".sources-block"]:
                target = page.locator(selector).first
                if await target.count():
                    await target.scroll_into_view_if_needed()
                    await page.wait_for_timeout(3500)
            validate_result(result, errors)
            print(f"PASS: {summary['answer_chars']} characters; {summary['sources']} sources; {elapsed:.2f}s", flush=True)
        finally:
            video = page.video
            await context.close()
            if video:
                await video.save_as(str(output / "new-conversation.webm"))
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--mode", choices=["auto", "workflow", "plan_execute", "multi_agent"], default="auto")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--timeout", type=float, default=800)
    parser.add_argument("--output", type=Path, default=Path("runs") / datetime.now().strftime("demo-%Y%m%d-%H%M%S"))
    asyncio.run(record(parser.parse_args()))


if __name__ == "__main__":
    main()
