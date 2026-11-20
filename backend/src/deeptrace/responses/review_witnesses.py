"""Review evidence checks provenance, not semantic truth or generated execution."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["fact", "behavior"]
    status: Literal["passed", "unresolved"]
    answer_excerpt: str = Field(min_length=1, max_length=800)
    reason: str = Field(min_length=1, max_length=300)
    source_marker: str | None = Field(default=None, pattern=r"^\[\d+\]$")
    source_quote: str | None = Field(default=None, min_length=1, max_length=400)
    scenario: str | None = Field(default=None, min_length=1, max_length=300)


def validate_review_witnesses(content, checks, sources=None):
    indexed = {match[0]: source for source in sources or []
               if (match := re.match(r"\[\d+\](?=\s|$)", source))}
    for check in checks:
        if check.answer_excerpt not in content:
            raise ValueError("invalid_answer_witness")
        if check.kind == "behavior" and not check.scenario:
            raise ValueError("missing_behavior_witness")
        if check.kind == "fact" and check.status == "passed":
            if not check.source_marker or not check.source_quote:
                raise ValueError("missing_source_witness")
            # Extracted HTML wraps inline punctuation onto separate lines.
            # Preserve every lexical/punctuation token, only ignore layout.
            def layout_tokens(text):
                return "\0" + "\0".join(re.findall(r"\w+|[^\w\s]", text)) + "\0"
            if (not check.source_quote.strip() or (sources is not None
                    and layout_tokens(check.source_quote) not in layout_tokens(indexed.get(check.source_marker, "")))):
                raise ValueError("invalid_source_witness")


REVIEW_WITNESS_INSTRUCTION = (
    "另外必须返回checks数组，选2-4项优先主结论和用户硬约束，不逐段重复核验。"
    "每项{kind:fact/behavior,status:passed/unresolved,answer_excerpt:修订后答案逐字片段,reason:实际判断依据}。"
    "fact通过时还须source_marker(如[1])与source_quote(该编号可见原文逐字引用，最多400字符)，"
    "核对所属章节、对象、版本和限定条件，不能只因引文真实就判支持。"
    "behavior还须scenario：具体输入→依次走过的条件分支→结果；失败提供反例。"
    "首句、表格和代码按同一规则核对；对每个相关错误分支验证保护条件，"
    "自行建议也必须遵守用户约束及规范限制，不能以工程取舍为名放宽保护。"
    "不能用只出现在另一个分支的保护来判当前分支安全。"
    "先修正对应片段，再以修订后的内容给检查结论；仍无法解决的反例用unresolved。"
    "checks是有据的审查记录，不执行代码，也不把场景描述当成实际运行结果。"
)
