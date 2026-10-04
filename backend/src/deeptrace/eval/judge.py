"""LLM-as-judge scoring for Tier 2 (real-model) evaluation runs.

The judge is a separate model gateway call with ``role="judge"``. It receives the
question, the produced answer, the loaded evidence excerpts and the reference
answer, and returns five bounded scores. The judge is never told which strategy
produced the answer, to avoid mode bias.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from deeptrace.harness.prompts import task_messages
from deeptrace.strategies.model_io import parse_json_object, payload_text

JUDGE_ROLE = "judge"
MAX_ANSWER_CHARS = 4_000
MAX_EVIDENCE_CHARS = 2_000

_RUBRIC = (
    "请从五个维度给这次研究结果打分，每项为 1-5 的整数（5 最好）：\n"
    "faithfulness：结论是否被所列证据支持；\n"
    "answer_correctness：与参考答案的一致程度；\n"
    "source_coverage：资料的广度与质量；\n"
    "citation_accuracy：引用与论断是否对应；\n"
    "coherence：回答结构是否清晰。\n"
    '只输出 JSON：{"faithfulness", "answer_correctness", "source_coverage", '
    '"citation_accuracy", "coherence"}，不要输出其他文字。'
)


class JudgeScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    faithfulness: int = Field(ge=1, le=5)
    answer_correctness: int = Field(ge=1, le=5)
    source_coverage: int = Field(ge=1, le=5)
    citation_accuracy: int = Field(ge=1, le=5)
    coherence: int = Field(ge=1, le=5)


def build_judge_prompt(
    *,
    question: str,
    answer: str,
    evidence_text: str,
    gold_answer: str = "",
) -> str:
    return (
        f"用户问题：{question}\n\n"
        f"参考答案：{gold_answer or '（无）'}\n\n"
        f"待评回答：\n{answer[:MAX_ANSWER_CHARS]}\n\n"
        f"已加载证据：\n{evidence_text or '（无）'}\n\n" + _RUBRIC
    )


async def judge_record(
    *,
    gateway: Any,
    question: str,
    answer: str,
    evidence_text: str,
    gold_answer: str = "",
) -> JudgeScore:
    messages = task_messages(
        instruction="你是研究质量评审，严格按给定维度评分，只输出 JSON。",
        task=question,
        constraints=[],
        prompt=build_judge_prompt(
            question=question,
            answer=answer,
            evidence_text=evidence_text,
            gold_answer=gold_answer,
        ),
    )
    response = await gateway.invoke(role=JUDGE_ROLE, messages=messages)
    payload = parse_json_object(payload_text(response))
    if payload is None:
        raise ValueError("judge payload is not a JSON object")
    return JudgeScore.model_validate(payload)
