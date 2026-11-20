"""Run the production application through LangSmith's evaluation runner."""
from dataclasses import replace
from datetime import datetime, UTC
import hashlib
from uuid import uuid4

from deeptrace.application.research import ApplicationResearchRequest
from deeptrace.observability.langsmith import application_outputs
from deeptrace.observability.model_metrics import run_usage_payload
from deeptrace.tools.evidence_store import EvidenceDraft


class _CountTools:
    def __init__(self, inner):
        self.inner, self.calls, self.successes = inner, 0, 0
        self.scope_violations = 0

    async def execute(self, **kwargs):
        self.calls += 1
        result = await self.inner.execute(**kwargs)
        self.scope_violations += int(result.error_code in {"tool_not_allowed", "evidence_not_authorized"})
        self.successes += int(result.ok)
        return result


def make_target(bundle, mode):
    async def target(inputs):
        run_id, thread_id = uuid4().hex, uuid4().hex
        try:
            documents = inputs.get("documents")
            if documents is not None:
                if not isinstance(documents, list) or not 1 <= len(documents) <= 32:
                    raise ValueError("documents must contain 1..32 source documents")
                for document in documents:
                    if hashlib.sha256(document["body"].encode("utf-8")).hexdigest() != document["sha256"]:
                        raise ValueError("source document hash mismatch")
            context = bundle.context_factory(run_id)
            gateway = context.tool_gateway
            ids = None
            if documents is not None:
                ids = []
                for document in documents:
                    record = await context.evidence_store.ingest(context.workspace_id,
                        EvidenceDraft(canonical_url=document["url"], title=document["title"],
                            body=document["body"], media_type="text/markdown",
                            fetched_at=datetime.now(UTC), source_quality=1.0,
                            metadata={"provided_source": True, "sha256": document["sha256"]}))
                    ids.append(record.id)
                gateway = gateway.with_source_scope(frozenset(ids))
            tools = _CountTools(gateway)
            # Trials must not learn reference answers or memories from other trials.
            context = replace(context, tool_gateway=tools, memory_store=None, memory_retriever=None,
                              source_evidence_ids=tuple(ids) if ids is not None else None)
            request = ApplicationResearchRequest(run_id=run_id, thread_id=thread_id,
                question=inputs["question"], mode=mode)
            result = await bundle.service.invoke(request,
                config={"configurable": {"thread_id": thread_id}}, context=context)
            source_urls = {document["url"] for document in documents} if documents is not None else None
            excerpts = []
            if result.research_outcome:
                for finding in result.research_outcome.findings:
                    for support in finding.supports:
                        excerpts.append({"evidence_id": support.evidence_id, "quote": support.quote})
            usage = run_usage_payload(context)
            model = context.model_gateway
            budget_ok = (model.used_calls <= model.max_calls and model.used_input_tokens <= model.max_input_tokens
                         if hasattr(model, "used_calls") else None)
            return {**application_outputs(result), "run_id": run_id,
                "tool_calls": tools.calls, "tool_successes": tools.successes,
                "source_scope_ok": (not tools.scope_violations and (source_urls is None or set(result.sources) <= source_urls)),
                "budget_compliant": budget_ok,
                "evidence_excerpts": excerpts[:100], "usage": usage}
        finally:
            bundle.release_run(run_id)
    return target
