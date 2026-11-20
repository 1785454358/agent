"""One report and, when needed, one local revision of the same visible sources."""

import json
import logging
import re

from deeptrace.domain import ResponseOutcome
from deeptrace.harness.model_budget import BudgetStateUnavailable, ModelBudgetExceeded
from deeptrace.harness.model_io import payload_text
from deeptrace.harness.model_recovery import invoke_readonly_with_recovery
from deeptrace.harness.policies.agent_context import message_tokens
from deeptrace.harness.prompts import task_messages
from deeptrace.harness.token_budget import bounded_run_context
from deeptrace.responses.citations import extract_citation_markers, validate_citations
from deeptrace.responses.constraint_audit import retry_constraint_issue
from deeptrace.responses.evidence import assemble_response_materials
from deeptrace.responses.models import ResponseDraft


def _content(response):
    raw = payload_text(response).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(data, dict) or not isinstance(data.get("content"), str):
        raise TypeError("missing_report_content")
    content = data["content"]
    if data.get("budgets"):
        from deeptrace.responses.budgets import BudgetTable, render_budget_content

        content, _ = render_budget_content(
            content, [BudgetTable.model_validate(b) for b in data["budgets"]]
        )
    return content


async def generate_delivery_report(context, request, loaded, policy, budget):
    # Late import only reuses existing formatting and token assembly helpers;
    # no second response graph or research/recovery coordinator is constructed.
    from deeptrace.responses.graph import _compose_prompt, _looks_incomplete

    materials = await assemble_response_materials(
        context, request, loaded, policy.per_source_chars
    )
    needs_review = context.response_fact_review and bool(
        re.search(
            r"代码|方案|设计|预算|重试|诊断|比较|对比|\b(?:code|design|retry|diagnos|compare)",
            request.question,
            re.IGNORECASE,
        )
    )
    allocation_budget = await bounded_run_context(
        context.model_gateway,
        "responder",
        budget,
        remaining_calls=2 if needs_review else 1,
    )
    prompt, allocation = _compose_prompt(
        policy,
        request,
        materials.sources,
        "",
        "\n".join(request.context_notes),
        corrective_suffix=None,
        budget_config=allocation_budget,
    )
    visible = [
        r.id
        for i, r in enumerate(loaded, 1)
        if any(
            p.text in allocation.rendered_segments.get(f"source_{i}", "")
            for p in materials.passages_by_source.get(r.id, ())
        )
    ]
    sources = [
        allocation.rendered_segments[f"source_{i}"]
        for i, r in enumerate(loaded, 1)
        if r.id in visible
    ]

    async def emit(kind, data):
        try:
            await context.event_sink.emit(kind, data)
        except Exception:  # Telemetry must not erase a report.
            logging.getLogger(__name__).debug(
                "Delivery progress unavailable", exc_info=True
            )

    await emit(
        "response.excerpts",
        {
            "algorithm": "actual-reads",
            "response_mode": policy.mode.value,
            "attempt": 1,
            "per_source_chars": None,
            "sources": [
                {
                    **s,
                    "token_status": "dropped"
                    if s["segment"] in allocation.dropped
                    else "truncated"
                    if s["segment"] in allocation.truncated
                    else "full",
                }
                for s in materials.selections
            ],
        },
    )
    for record in loaded:
        for passage in materials.passages_by_source.get(record.id, ()):
            await emit(
                "evidence.view",
                {
                    "stage": "response",
                    "evidence_id": record.id,
                    "version": record.version,
                    "content_hash": record.content_hash,
                    "start": passage.start,
                    "end": passage.end,
                    "passage_id": passage.passage_id,
                    "visibility": any(passage.text in s for s in sources),
                },
            )

    def fallback(reason):
        # Literal material only; this is explicitly a limited fallback, not
        # an error string passed off as a successful substantive report.
        excerpts = [
            f"> {p.text[:450]}\n\n[{i}] {r.canonical_url}"
            for i, r in enumerate(loaded, 1)
            if r.id in visible
            for p in materials.passages_by_source.get(r.id, ())[:1]
        ]
        text = (
            (
                "本次未能完成可靠的最终报告。已取得的原始依据如下；尚不能据此确认全部问题：\n\n"
                + "\n\n".join(excerpts)
            )
            if excerpts
            else "本次没有取得可用的来源正文，无法据此作出可靠结论。需要补充可访问的原始资料后再研究。"
        )
        return ResponseOutcome(
            response_mode=policy.mode,
            content=text[: policy.max_content_chars],
            partial_reason=reason,
        )

    if not visible:
        return fallback("no_evidence")
    allowed = {f"[{i}]" for i, r in enumerate(loaded, 1) if r.id in visible}

    def issues(content):
        result = []
        markers = set(extract_citation_markers(content))
        if not content.strip() or _looks_incomplete(content):
            result.append("正文须完整，代码围栏及句子必须闭合")
        if len(content) > policy.max_content_chars:
            result.append(f"全文最多{policy.max_content_chars}字符，保留完整必要步骤")
        if not markers or not markers <= allowed:
            result.append("事实引用仅能使用实际可见的来源编号")
        problem = retry_constraint_issue(request.question, content)
        if problem:
            result.append(problem)
        return result

    instructions = (
        policy.instructions + "\n根据本次已有原文尽力完整回答，不等待所有事实查清。"
        "明确已支持结论、建议/假设、相反证据和本次未核实之处；不把未知升级为规范没有规定。"
        '不要输出内部覆盖或审查协议。返回正文或JSON {"content":"报告正文"}。'
    )
    try:
        response = await invoke_readonly_with_recovery(
            context.model_gateway,
            role="responder",
            messages=task_messages(
                instruction=instructions,
                task=request.question,
                constraints=request.constraints,
                prompt=prompt,
            ),
        )
        draft = _content(response)
    except BudgetStateUnavailable:
        raise
    except Exception:  # noqa: BLE001 - provider/output failures produce an honest partial result
        return fallback("generation_failed")
    problems = issues(draft)
    content = draft
    partial_reason = None
    if needs_review or problems:
        retry_checks = (
            "重试题逐分支检查：没有去重承诺且不能确认未生效的POST收到429/503后不能直接重发，"
            "业务接受重复风险不是幂等或未生效的依据；send绑定剩余预算，最后一次失败不再等待。"
            if re.search(r"\bPOST\b", request.question, re.IGNORECASE)
            and re.search(r"retry|重试", request.question, re.IGNORECASE)
            else ""
        )
        review_prompt = (
            "按原始问题、约束和同一份可见原文直接修订草稿，保留有用内容、引用和未知说明。"
            "首句、表格与代码须使用同一规则；自行建议不能绕过用户约束。"
            + retry_checks
            + '返回完整修订正文或{"content":"修订正文"}，不要返回checks或edits等辅助协议。\n'
            + json.dumps(
                {"sources": sources, "draft": draft, "issues": problems},
                ensure_ascii=False,
            )
        )
        try:
            messages = task_messages(
                instruction=instructions,
                task=request.question,
                constraints=request.constraints,
                prompt=review_prompt,
            )
            review_budget = await bounded_run_context(
                context.model_gateway, "responder", budget, remaining_calls=1
            )
            if message_tokens(messages) > review_budget.input_budget:
                raise ModelBudgetExceeded("delivery_review_context_limit")
            revised = _content(
                await invoke_readonly_with_recovery(
                    context.model_gateway, role="responder", messages=messages
                )
            )
            if issues(revised):
                raise ValueError("invalid_revised_report")
            content = revised
            await emit(
                "response.fact_review.completed",
                {
                    "drafting_mode": "delivery_revision",
                    "draft": draft,
                    "revised_answer": content,
                    "issues": problems,
                    "unanswered_points": [],
                },
            )
        except BudgetStateUnavailable:
            raise
        except Exception:  # noqa: BLE001 - optional revision cannot erase a valid draft
            if problems:
                return fallback("answer_review_unavailable")
            partial_reason = "answer_review_unavailable"
            await emit("response.fact_review.unavailable", {"draft_retained": True})
    outcome = validate_citations(
        ResponseDraft(response_mode=policy.mode, content=content),
        loaded_evidence_ids=[r.id for r in loaded],
        visible_evidence_ids=visible,
    )
    return outcome.model_copy(
        update={"partial_reason": partial_reason or outcome.partial_reason}
    )
