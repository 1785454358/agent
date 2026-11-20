"""Run isolated real-provider delivery checks and preserve raw results."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import time
import uuid

from deeptrace.application.assembly import build_harness_runtime
from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.config import Settings
from deeptrace.domain import ResearchMode
from deeptrace.observability.model_metrics import run_usage_payload


CASES = [
    ("beijing", "请规划北京3天2晚自由行，每人预算2000元（不含往返北京大交通）。按普通非节假日、两人同行合住估算，给出每天可执行的路线、交通、预约提醒和分项预算；价格允许合理估算，但要说明假设，不要把估价当实时报价。", ResearchMode.WORKFLOW),
    ("checkpoint", "LangGraph 中 checkpoint、thread_id 和中断恢复是什么关系？请给一个最小恢复流程，并解释恢复时哪些步骤可能重新执行。", ResearchMode.PLAN_EXECUTE),
    ("unsupported-ranking", "仅根据 LangChain 官方结构化输出文档，能否认定 ProviderStrategy 在所有任务上都比 ToolStrategy 费用更低、延迟更小？若不能，请说明文档实际能支持哪些选择建议，还缺哪些测量。", ResearchMode.MULTI_AGENT),
]


class ClientClock:
    def now(self):
        return datetime(2026, 11, 17, 4, 0, tzinfo=UTC)


async def main():
    root = Path("runs") / ("delivery-repair-20261117-" + uuid.uuid4().hex[:6])
    root.mkdir(parents=True)
    settings = replace(Settings.from_env(), runtime_mode="local", mysql_dsn="", redis_url="",
                       memory_retrieval="lexical")
    (root / "protocol.json").write_text(json.dumps({
        "model": settings.openai_model, "date": "2026-11-17", "memory": "isolated lexical",
        "max_model_calls": settings.max_model_calls, "max_input_tokens": settings.max_input_tokens,
        "research_max_seconds": settings.research_max_seconds,
    }, ensure_ascii=False, indent=2), encoding="utf8")
    print("artifacts:", root.resolve(), flush=True)
    for name, question, mode in CASES:
        folder = root / name
        folder.mkdir()
        bundle = build_harness_runtime(settings, runs_dir=folder / "state")
        run_id = "delivery-" + uuid.uuid4().hex[:12]
        events = []
        def event(kind, details):
            events.append({"type": kind, "details": details})
        context = bundle.context_factory(run_id, event)
        gateway = context.model_gateway
        class RecordingGateway:
            def __getattr__(self, name):
                return getattr(gateway, name)
            async def invoke(self, **kwargs):
                started = time.monotonic()
                response = await gateway.invoke(**kwargs)
                identity = uuid.uuid4().hex[:8]
                (folder / f"model-{identity}-{kwargs['role']}.json").write_text(json.dumps({
                    "role": kwargs["role"], "seconds": time.monotonic() - started,
                    "messages": [m.model_dump(mode="json") for m in kwargs["messages"]],
                    "content": response.content, "usage": response.usage_metadata,
                }, ensure_ascii=False, indent=2, default=str), encoding="utf8")
                return response
        context = replace(context, model_gateway=RecordingGateway(), clock=ClientClock())
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(bundle.service.invoke(
                ApplicationResearchRequest(run_id=run_id, thread_id=run_id, question=question, mode=mode),
                config={"configurable": {"thread_id": run_id}}, context=context,
            ), timeout=780)
            (folder / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf8")
            (folder / "answer.md").write_text(result.response_outcome.content, encoding="utf8")
            print(name, result.status, result.termination_reason,
                  "chars=", len(result.response_outcome.content), "sources=", len(result.sources),
                  "seconds=", round(time.monotonic()-started, 2), flush=True)
        except Exception as exc:
            (folder / "error.json").write_text(json.dumps({"type": type(exc).__name__}, indent=2), encoding="utf8")
            print(name, "error", type(exc).__name__, flush=True)
        finally:
            (folder / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str), encoding="utf8")
            (folder / "usage.json").write_text(json.dumps(run_usage_payload(context), ensure_ascii=False, indent=2, default=str), encoding="utf8")
            await bundle.aclose()


if __name__ == "__main__":
    asyncio.run(main())
