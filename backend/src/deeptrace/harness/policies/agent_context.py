"""Token-bounded model views; the durable transcript is never truncated."""

import json

from langchain_core.messages import ToolMessage

from deeptrace.harness.agent_state import topic_input
from deeptrace.harness.prompts import RESEARCH_SYSTEM_INSTRUCTION, task_messages
from deeptrace.harness.token_budget import TokenBudgetConfig, count_tokens


class ContextLimitError(ValueError):
    pass


def message_tokens(messages, tools=()):
    # Conservative serialization estimate including tool schemas and framing.
    payload = [m.model_dump(mode="json") for m in messages]
    return count_tokens(json.dumps([payload, tools], ensure_ascii=False, default=str))


def prepare_messages(state, tools, budget: TokenBudgetConfig):
    task = topic_input(state)
    prefix = task_messages(
        instruction=RESEARCH_SYSTEM_INSTRUCTION,
        task=task.original_task or task.query,
        constraints=task.constraints,
        prompt="当前研究分支：" + task.query,
    )
    todos = state.get("todos") or []
    if todos:
        prefix[1].content += "\n当前计划：" + json.dumps(
            [t.model_dump(mode="json") for t in todos], ensure_ascii=False
        )
    if state.get("evidence_ids"):
        prefix[1].content += "\n已收集证据：" + ", ".join(state["evidence_ids"])
    # Groups are indivisible: one assistant tool call batch plus all results.
    groups = []
    for message in state.get("messages") or []:
        if message.type == "system":
            continue
        if isinstance(message, ToolMessage):
            if not groups or message.tool_call_id not in {
                c["id"] for c in getattr(groups[-1][0], "tool_calls", [])
            }:
                raise ContextLimitError("Unpaired tool result")
            groups[-1].append(message)
        else:
            groups.append([message])
    for group in groups:
        requested = [c["id"] for c in getattr(group[0], "tool_calls", [])]
        returned = [m.tool_call_id for m in group if isinstance(m, ToolMessage)]
        if sorted(requested) != sorted(returned):
            raise ContextLimitError("Unclosed tool batch")
    selected = []
    for group in reversed(groups):
        candidate = group + selected
        if message_tokens(prefix + candidate, tools) > budget.input_budget:
            if not selected:
                raise ContextLimitError("Current exchange exceeds context budget")
            break
        selected = candidate
    if message_tokens(prefix + selected, tools) > budget.input_budget:
        raise ContextLimitError("Task and constraints exceed context budget")
    # Recalled background is elastic; constraints above are always pinned.
    for note in task.context_notes:
        candidate = prefix[1].model_copy(
            update={"content": prefix[1].content + "\n背景资料：" + note}
        )
        if (
            message_tokens([prefix[0], candidate] + selected, tools)
            <= budget.input_budget
        ):
            prefix[1] = candidate
    return prefix + selected
