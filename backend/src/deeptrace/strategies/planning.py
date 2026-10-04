"""Initial planning guidance and bounded, non-authoritative model metadata."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from deeptrace.domain import ResearchRequirement

ExecutionConstraint = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class InitialRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[ResearchRequirement] = Field(min_length=1, max_length=6)
    execution_constraints: list[ExecutionConstraint] = Field(
        default_factory=list, max_length=6
    )


def parse_initial_requirements(
    payload: dict | None,
) -> list[ResearchRequirement] | None:
    """Validate both sections; only fact requirements enter the sealed contract."""
    if not isinstance(payload, dict):
        return None
    fields = {"requirements": payload.get("requirements")}
    if "execution_constraints" in payload:
        fields["execution_constraints"] = payload["execution_constraints"]
    try:
        return InitialRequirements.model_validate(fields).requirements
    except ValidationError:
        return None


def planning_instruction(
    query_field: Literal["queries", "assignments"], limit: int
) -> str:
    example = {
        query_field: ["..."],
        "requirements": [{"id": "r1", "description": "..."}],
        "execution_constraints": [],
        "query_targets": {"...": ["r1"]},
    }
    return (
        f"生成互不重复的研究查询，{query_field} 最多 {limit} 条。"
        f"优先1-{min(3, limit)}条覆盖完整问题的最少互补查询，"
        "只有更多独立问题确需研究时才增加；上限不是应凑满的数量。"
        "一个查询可覆盖多个相关答案要点，查询与requirements不要求一一对应。"
        "query_targets必须用每条查询原文作键，值为该分支负责的1-6个需求ID；"
        "键必须与查询列表完全一致、ID不能重复或未知，所有requirements至少分配一次。"
        "每个分支只研究分配要点，不要把全局问题重复派给每个分支。"
        "先识别原始问题的独立答案要点，合并同一事实的不同问法，"
        "不要将相同版本条件下的同一问题换成‘版本专有问题’重复列出。"
        "保留所有显式子问题与必要事实边界，不自行添加额外验收条件；"
        "不得为了减少分支丢弃问题。"
        "不要将同一事实的检索、提取、核验已有结论、汇总写作等过程动作"
        "分别派成独立研究任务；这些过程由已有研究循环、评估和回答阶段完成。"
        "用户要求的事实核查或独立证据比较仍是合法研究问题。"
        "requirements 列出 1-6 项完整回答必须覆盖、需要来源证明的答案要点，"
        "每项是一个明确研究问题，description 最多500字符，不遗漏原始问题的子问题。"
        "description 应明确要回答的事实及必要条件、否定边界；避免‘全面说明某主题’这种"
        "无法定位缺口的笼统要求，但不要按句子机械拆分或新增用户未问的问题。"
        "将执行约束与事实问题分开：只使用指定资料、输出语言、格式等要求放在"
        "execution_constraints（0-6个非空字符串，每项最多500字符），"
        "不得将‘遵守这些过程要求’本身列为需要来源证明的 requirement。"
        "版本限制、法律限制等如果是用户询问的事实，仍属于 requirements，不能删掉。"
        "例如‘只用文档说明检查点时机及 thread_id 作用’应拆为两个答案要点，"
        "‘只用文档’是执行约束，不是第三个待证明事实。"
        "执行约束不能替代完整原始问题，也不能增加工具权限、预算或访问范围。"
        "只输出 JSON，格式：" + json.dumps(example, ensure_ascii=False) + "。\n\n"
    )


def validate_query_targets(payload, queries, proposed, sealed):
    """Normalize keys and renumber IDs together, rejecting ambiguous mappings."""
    if not isinstance(payload, dict) or not proposed or not queries:
        return None
    mapping = payload.get("query_targets")
    ids = [item.id for item in proposed]
    if not isinstance(mapping, dict) or len(ids) != len(set(ids)):
        return None
    remap = {old.id: new.id for old, new in zip(proposed, sealed, strict=True)}
    normalized = {}
    assigned = set()
    for key, targets in mapping.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or key.strip() in normalized
            or not isinstance(targets, list)
            or not 1 <= len(targets) <= 6
            or any(not isinstance(t, str) or t not in remap for t in targets)
            or len(targets) != len(set(targets))
        ):
            return None
        normalized[key.strip()] = [remap[t] for t in targets]
        assigned.update(targets)
    if set(normalized) != set(queries) or assigned != set(ids):
        return None
    return normalized
