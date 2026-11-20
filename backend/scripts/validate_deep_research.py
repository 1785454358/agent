"""Trace a real scholarly research run without replacing production components."""

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import time
import uuid

from deeptrace.application.assembly import build_harness_runtime
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode, ResponseMode
from deeptrace.observability.model_metrics import run_usage_payload

QUESTION = (
    "2024—2025年，推理时计算扩展（test-time compute scaling）如何改善大语言模型的数学推理？"
    "对比至少3项代表性原始研究，解释候选采样/搜索、验证器、推理预算控制分别的作用；"
    "列出各研究的模型、评测集、计算预算口径与主要结果，分析为什么不能直接比较榜单数字，"
    "给出固定推理预算下的工程选型建议。优先原始论文和官方技术报告；缺少数据明确标注，"
    "不要把跨模型、跨数据集的数字当作公平对比。用中文形成有分析深度的研究报告。"
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=lambda x:
        x.model_dump(mode="json") if hasattr(x, "model_dump") else str(x)), encoding="utf8")


class ClientClock:
    def now(self):
        return datetime(2026, 11, 17, 8, 0, tzinfo=UTC)


async def run(label):
    root = Path("runs") / ("deep-research-20261117-" + label + "-" + uuid.uuid4().hex[:6])
    root.mkdir(parents=True)
    settings = replace(Settings.from_env(), runtime_mode="local", mysql_dsn="", redis_url="",
                       memory_retrieval="lexical")
    save(root / "protocol.json", {
        "question": QUESTION, "label": label, "model": settings.openai_model,
        "mode": "multi_agent", "response_mode": "report", "date": "2026-11-17",
        "max_model_calls": settings.max_model_calls, "max_input_tokens": settings.max_input_tokens,
        "research_max_seconds": settings.research_max_seconds,
        "research_source_target": settings.research_source_target, "memory": "isolated lexical",
        "code_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(Path("src/deeptrace").rglob("*.py"))},
    })
    run_id = "deep-test-" + uuid.uuid4().hex[:12]
    bundle = build_harness_runtime(settings, runs_dir=root / "state")
    started = time.monotonic()
    def event(kind, details):
        with (root / "events.jsonl").open("a", encoding="utf8") as stream:
            stream.write(json.dumps({"seconds": round(time.monotonic()-started, 3),
                                     "type": kind, "details": details}, ensure_ascii=False, default=str) + "\n")
    context = bundle.context_factory(run_id, event)
    model, tools = context.model_gateway, context.tool_gateway
    sequence = {"model": 0, "tool": 0}

    class RecordingModel:
        def __getattr__(self, name):
            return getattr(model, name)
        async def invoke(self, **kwargs):
            sequence["model"] += 1
            index, begin = sequence["model"], time.monotonic()
            path = root / f"model-{index:02d}-{kwargs['role']}.json"
            record = {"index": index, "role": kwargs["role"], "started_seconds": begin-started,
                      "messages": [m.model_dump(mode="json") for m in kwargs["messages"]]}
            save(path, record)
            try:
                response = await model.invoke(**kwargs)
                record.update(content=response.content, usage=response.usage_metadata,
                              response_metadata=response.response_metadata)
                return response
            except BaseException as exc:
                record["error_type"] = type(exc).__name__
                record["error_code"] = getattr(exc, "code", None)
                raise
            finally:
                record["seconds"] = time.monotonic()-begin
                save(path, record)

    class RecordingTools:
        def __getattr__(self, name):
            return getattr(tools, name)
        async def execute(self, **kwargs):
            sequence["tool"] += 1
            index, begin = sequence["tool"], time.monotonic()
            request = kwargs["request"]
            path = root / f"tool-{index:03d}-{request.tool}.json"
            record = {"index": index, "started_seconds": begin-started, "request": request}
            save(path, record)
            try:
                response = await tools.execute(**kwargs)
                record["result"] = response
                return response
            except BaseException as exc:
                record["error_type"] = type(exc).__name__
                raise
            finally:
                record["seconds"] = time.monotonic()-begin
                save(path, record)

    context = replace(context, model_gateway=RecordingModel(), tool_gateway=RecordingTools(), clock=ClientClock())
    print("artifacts:", root.resolve(), flush=True)
    try:
        result = await asyncio.wait_for(bundle.service.invoke(
            ApplicationResearchRequest(run_id=run_id, thread_id=run_id, question=QUESTION,
                                       mode=ResearchMode.MULTI_AGENT, response_mode=ResponseMode.REPORT),
            config={"configurable": {"thread_id": run_id}}, context=context,
        ), timeout=780)
        save(root / "result.json", result)
        (root / "answer.md").write_text(result.response_outcome.content, encoding="utf8")
        records = []
        for identity in result.research_outcome.evidence_ids:
            record = await context.evidence_store.get(context.workspace_id, identity)
            records.append({**record.model_dump(mode="json"),
                            "body": await context.evidence_store.read_body(context.workspace_id, identity)})
        save(root / "sources.json", records)
        save(root / "final-state.json", (await bundle.service._graph.aget_state(
            {"configurable": {"thread_id": run_id}}, subgraphs=True)).values)
        print(result.status, result.termination_reason, "chars", len(result.response_outcome.content),
              "sources", len(result.sources), "seconds", round(time.monotonic()-started, 2), flush=True)
    except Exception as exc:
        save(root / "error.json", {"type": type(exc).__name__})
        print("error", type(exc).__name__, flush=True)
    finally:
        save(root / "usage.json", run_usage_payload(context))
        save(root / "timing.json", {"seconds": time.monotonic()-started})
        await bundle.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="baseline")
    asyncio.run(run(parser.parse_args().label))
