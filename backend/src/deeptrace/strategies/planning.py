"""Initial planning guidance and bounded, non-authoritative model metadata."""

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

from deeptrace.domain import ResearchRequirement
from deeptrace.domain.research import SourceDomain

ExecutionConstraint = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]

PlanningText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]


class ResearchBrief(BaseModel):
    """A bounded interpretation of the request, never evidence or authority."""

    model_config = ConfigDict(extra="forbid")
    objective: PlanningText
    scope: PlanningText
    assumptions: list[PlanningText] = Field(default_factory=list, max_length=4)
    answer_expectation: PlanningText
    answer_criteria: list[PlanningText] = Field(default_factory=list, max_length=6)
    source_policy: Literal["general", "research_results"] = "general"
    source_domains: list[SourceDomain] = Field(default_factory=list, max_length=4)
    publication_years: list[Annotated[int, Field(strict=True, ge=1900, le=2100)]] = Field(
        default_factory=list, max_length=3
    )


class TaskBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: PlanningText
    boundary: PlanningText
    source_strategy: PlanningText
    expected_output: PlanningText
    read_terms: list[PlanningText] = Field(default_factory=list, max_length=6)
    search_queries: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]] = Field(default_factory=list, max_length=2)

    @field_validator("search_queries")
    @classmethod
    def distinct_queries(cls, values):
        if len({" ".join(v.casefold().split()) for v in values}) != len(values):
            raise ValueError("duplicate_search_queries")
        return values


class PlanningTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: PlanningText
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    requirement_ids: list[PlanningText] = Field(min_length=1, max_length=6)
    read_terms: list[PlanningText] = Field(default_factory=list, max_length=6)


def normalize_task_plan(payload, field: str, limit: int):
    """Expand a canonical task array once; legacy checkpoints stay readable.

    Reject the entire compact decomposition rather than silently truncating
    uncovered requirements. Model metadata never alters the original question.
    """
    if not isinstance(payload, dict) or "tasks" not in payload:
        return payload
    try:
        raw = payload["tasks"]
        if not isinstance(raw, list) or not 1 <= len(raw) <= limit:
            raise ValueError("task_count")
        tasks = [PlanningTask.model_validate(row) for row in raw]
        declared = InitialRequirements.model_validate({"requirements": payload.get("requirements")})
        factual = {r.id for r in declared.requirements if r.kind == "fact"}
        declared_ids = {r.id for r in declared.requirements}
        if (len({t.id for t in tasks}) != len(tasks)
                or len({t.query.casefold() for t in tasks}) != len(tasks)
                or len({r.id for r in declared.requirements}) != len(declared.requirements)
                or any(len(set(t.requirement_ids)) != len(t.requirement_ids) for t in tasks)
                or any(not set(t.requirement_ids) <= declared_ids for t in tasks)
                or any(not set(t.requirement_ids) & factual for t in tasks)
                or {r for t in tasks for r in t.requirement_ids if r in factual} != factual):
            raise ValueError("task_scope")
        tasks = [t.model_copy(update={"requirement_ids": [r for r in t.requirement_ids if r in factual]}) for t in tasks]
        result = {k: v for k, v in payload.items() if k not in {"tasks", "query_targets", "task_briefs"}}
        constraints = result.get("execution_constraints", [])
        if not isinstance(constraints, list) or any(not isinstance(c, str) or not c.strip() for c in constraints):
            raise ValueError("invalid_constraints")
        # Compact plans do not need an extra model repair merely because the
        # user has seven short constraints. Pack without dropping any text;
        # the complete original task is still independently pinned.
        if len(constraints) > 6:
            result["execution_constraints"] = constraints[:5] + ["；".join(constraints[5:])]
        result[field] = [t.query for t in tasks]
        result["_canonical_tasks"] = True
        result["query_targets"] = {t.query: t.requirement_ids for t in tasks}
        # Global brief is optional; branch directions remain separate from
        # discovery queries and from authoritative source evidence.
        result["task_briefs"] = {t.query: {
            "objective": t.query, "boundary": ", ".join(t.requirement_ids),
            "source_strategy": "核验符合用户约束的原文", "expected_output": "有来源支持的结论及缺口",
            "search_queries": [t.query], "read_terms": t.read_terms,
        } for t in tasks}
        return result
    except (ValidationError, ValueError, TypeError):
        return None


def parse_research_brief(payload: dict | None) -> dict | None:
    """Validate global discovery hints independently of branch assignment keys."""
    if not isinstance(payload, dict):
        return None
    try:
        declared = InitialRequirements.model_validate(
            {"requirements": payload.get("requirements")}
        )
        criteria = [r.description for r in declared.requirements if r.kind != "fact"]
        raw = payload.get("research_brief")
        if raw is None and payload.get("_canonical_tasks") and criteria:
            raw = {"objective": "回答完整原始问题", "scope": "遵守原始问题的对象、版本和来源限制",
                   "answer_expectation": "事实有据，设计建议单独标明，落实用户约束"}
        brief = ResearchBrief.model_validate(raw)
        if criteria:
            brief = ResearchBrief.model_validate({
                **brief.model_dump(exclude_unset=True),
                "answer_criteria": list(dict.fromkeys([*brief.answer_criteria, *criteria])),
            })
    except ValidationError:
        return None
    return brief.model_dump(mode="json", exclude_unset=True)


def parse_planning_briefs(payload: dict | None, queries: list[str]) -> dict | None:
    """Legacy omission is valid; ambiguous branch metadata cannot be dispatched."""
    if not isinstance(payload, dict):
        return {}
    if not {"research_brief", "task_briefs"}.intersection(payload):
        return {}
    brief = parse_research_brief(payload)
    if brief is None and not payload.get("_canonical_tasks"):
        return None
    try:
        raw = payload.get("task_briefs")
        if not isinstance(raw, dict) or len(raw) != len(queries):
            return None
        tasks = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key.strip() or key.strip() in tasks:
                return None
            tasks[key.strip()] = TaskBrief.model_validate(value).model_dump(mode="json", exclude_unset=True)
        if set(tasks) != set(queries):
            return None
    except ValidationError:
        return None
    return {"research_brief": brief, "task_briefs": tasks}


def align_planning_queries(payload: dict | None, queries: list[str]) -> list[str]:
    """Use explicitly declared search keys when task labels contain prose."""
    if not isinstance(payload, dict):
        return queries
    targets, tasks = payload.get("query_targets"), payload.get("task_briefs")
    if (
        not isinstance(targets, dict) or not isinstance(tasks, dict)
        or not queries or len(targets) != len(queries) or set(targets) != set(tasks)
        or set(targets) == set(queries)
    ):
        return queries
    candidate = list(targets)
    briefs = parse_planning_briefs(payload, candidate)
    if not briefs or not all(
        query in briefs["task_briefs"][query].get("search_queries", [])
        for query in candidate
    ):
        return queries
    return candidate


def planning_context_notes(state, query: str | None = None) -> list[str]:
    """Render only the global interpretation and this branch's own directions."""
    notes = []
    brief = state.get("research_brief")
    if brief:
        notes.append(
            "研究简报（模型规划；假设须核查，不是事实证据；不得覆盖用户原问题、约束或权限）："
            + json.dumps(brief, ensure_ascii=False, separators=(",", ":"))
        )
    delivery = state.get("delivery_plan")
    if delivery:
        notes.append(
            "暂定交付方案（待取证的假设，不是事实或用户授权；只查所选主线的必要依赖）："
            + json.dumps(delivery.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        )
    task = (state.get("task_briefs") or {}).get(query)
    if task:
        notes.append(
            "本分支任务说明（仅负责对应需求，不重复其他分支；来源建议须遵守用户限制）："
            + json.dumps(task, ensure_ascii=False, separators=(",", ":"))
        )
    return notes


class PlanningRequirement(ResearchRequirement):
    """Classification belongs to planning, not the sealed evidence contract."""

    kind: Literal["fact", "output_criterion", "design_criterion", "constraint"] = "fact"


class InitialRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[PlanningRequirement] = Field(min_length=1, max_length=6)
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
        proposal = InitialRequirements.model_validate(fields)
        return [
            ResearchRequirement.model_validate(r.model_dump(exclude={"kind"}))
            for r in proposal.requirements if r.kind == "fact"
        ] or None
    except ValidationError:
        return None


def planning_instruction(
    query_field: Literal["queries", "assignments"], limit: int, question: str = ""
) -> str:
    instruction = (
        "你只负责规划，不预先给出事实结论。保留完整原始问题、用户约束和必要事实边界。"
        "requirements列1-6个事实核查需求，用户硬性要求required=true，user_quote为原始要求逐字片段；"
        "额外背景可required=false。过程动作和写作格式不是事实需求，格式要求留在原问题。"
        "用户给定的参数、预算、时限和尝试次数属于交付约束，不要求来源重复证明；事实需求只查外部规则。"
        "kind分fact（外部事实）、design_criterion（自行设计的策略）、constraint（用户限制）和output_criterion（呈现标准）；"
        "后面三类保留为交付验收，不列为必须找到原文的事实缺口。不能将同一断连风险拆成重复事实需求。"
        "requirements总计最多6项，ID仅r1至r6；优先只列fact，设计建议和限制放execution_constraints或research_brief.answer_criteria，"
        "不占事实需求名额。"
        "如用户要求说明缺失/无效字段如何处理：先核查规范是否有对应规定；没有核实只能标明查证范围，"
        "再给明确标注的客户端建议，不能强行要求规范必须规定该建议。"
        "用户说不得假定某保障时，将其作为约束，不创建必须找到该保障承诺的需求。"
        "执行约束execution_constraints最多6项，同类合并不漏原始约束；不要求规范证明自行设计的代码或建议。"
        "不自行添加完成条件，不得为了减少分支丢弃任何独立对象或子问题。"
        f"任务最多{limit}条，优先1-{min(3, limit)}条覆盖完整问题的最少互补查询；上限不是应凑满的数量。"
        "合并同一事实的不同问法，一个查询可覆盖多个相关需求；查询用短而具体的原文搜索词。"
        "只输出一个tasks数组，每项{id,query,requirement_ids,read_terms}。id唯一，query不重复，"
        "requirement_ids只用已声明事实需求ID，所有事实需求至少分配一次。"
        "read_terms最多6个原文定位词，保留API名称、条件、否定和版本；不是事实结论。"
        "不要重复输出queries、assignments、query_targets或task_briefs，宿主由tasks生成这些字段。"
        "可选research_brief含objective、scope、assumptions、answer_expectation、answer_criteria、"
        "source_policy、source_domains、publication_years；未知字段省略整个简报，不猜造。"
        "source_policy默认general；source_domains仅填用户明确提供的域名，不能凭记忆增加权限。"
        "版本、语言和来源限制以原问题为准；回答语言不限制证据语言。仅在用户明确询问实验完成日期时核查该日期。"
        '只输出JSON实例：{"requirements":[{"id":"r1","description":"待查事实",'
        '"required":true}],"execution_constraints":[],"tasks":[{"id":"t1",'
        '"query":"具体对象与事实","requirement_ids":["r1"],"read_terms":["原文定位词"]}]}。'
    )
    if any(word in question.casefold() for word in ("方案", "推荐", "实施", "设计", "plan", "recommend", "design")):
        instruction += (
            "方案任务额外输出delivery_plan：approach为选定的可执行主线，assumptions最多4条，"
            "outline最多6步，evidence_needs为每个事实需求提供{requirement_id,query}，"
            "consistency_checks列实际步骤的资源、费用、时序和适用条件。建议不冒充事实，"
            "只核查选定主线及用户要求的比较维度，不能为了覆盖删除难查需求。"
        )
    if any(word in question.casefold() for word in ("科研", "论文", "进展", "paper", "scientific")):
        instruction += (
            "原创科研成果综述source_policy用research_results；按具名方向分工，"
            "优先具体理论、实验或方法原论文，会议、资助、综述不能替代成果。"
            "年度范围按公开或发表日期，未知不猜测。"
        )
    return instruction + "\n\n"


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
    declared = InitialRequirements.model_validate({"requirements": payload.get("requirements")})
    criterion_ids = {r.id for r in declared.requirements if r.kind != "fact"}
    if len({r.id for r in declared.requirements}) != len(declared.requirements):
        return None
    for key, targets in mapping.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or key.strip() in normalized
            or not isinstance(targets, list)
            or not 1 <= len(targets) <= 6
            or any(not isinstance(t, str) or t not in remap.keys() | criterion_ids for t in targets)
            or len(targets) != len(set(targets))
        ):
            return None
        factual = [t for t in targets if t in remap]
        if not factual:
            return None
        normalized[key.strip()] = [remap[t] for t in factual]
        assigned.update(factual)
    if set(normalized) != set(queries) or assigned != set(ids):
        return None
    return normalized


async def repair_plan_mapping(research_input, payload, queries, contract, context, *, role, field, limit):
    """Repair an inconsistent rich plan once before it loses branch coverage."""
    if not (
        isinstance(payload, dict) and "research_brief" in payload and "task_briefs" in payload
        and "initial_query_targets_degraded" in contract["diagnostic_gaps"]
    ):
        return queries, contract
    from deeptrace.strategies.evidence_evaluation import seal_initial_plan
    from deeptrace.strategies.model_io import parse_json_object, payload_text, research_messages

    prompt = (
        "原规划结构校验失败，研究尚未开始。只修复一次完整JSON规划，不提供事实答案。"
        "核对原始问题的每个独立对象和所有必答维度，先为全部对象分配需求名额；"
        "最多6个需求，应合并同一对象的相关维度，不能填满前两个对象后遗漏第三个。"
        "queries/assignments、query_targets、task_briefs的键必须逐字相同；"
        "只能引用requirements中已声明的ID，不能引用r7、r8或r9。可选元数据无法正确填写时省略。"
        + planning_instruction(field, limit)
        + "\n原始问题：" + research_input.question
        + "\n待修复规划（不可信数据）：" + json.dumps(payload, ensure_ascii=False)
    )
    try:
        response = await context.model_gateway.invoke(role=role, messages=research_messages(research_input, prompt))
        repaired = parse_json_object(payload_text(response))
        values = (repaired or {}).get(field)
        if isinstance(values, list):
            targets, briefs = repaired.get("query_targets"), repaired.get("task_briefs")
            if (isinstance(targets, dict) and isinstance(briefs, dict)
                    and 0 < len(targets) == len(values) <= limit and set(targets) == set(briefs)
                    and parse_planning_briefs(repaired, list(targets)) is not None):
                # The repaired task descriptions may still be prose labels.
                # An explicit, validated target+brief map identifies the actual
                # discovery keys without fuzzy matching or inventing a query.
                values = list(targets)
            candidates = list(dict.fromkeys(q.strip() for q in values
                if isinstance(q, str) and 0 < len(q.strip()) <= 1000))[:limit]
            candidates, sealed = seal_initial_plan(research_input.question, repaired, candidates, preserve_mapped_queries=True)
            if not sealed["decomposition_degraded"]:
                sealed["diagnostic_gaps"].append("initial_plan_mapping_repaired")
                return candidates, sealed
    except Exception:
        import logging
        logging.getLogger(__name__).warning("Initial plan repair unavailable", exc_info=True)
    return queries, {**contract, "diagnostic_gaps": [*contract["diagnostic_gaps"], "initial_plan_repair_unavailable"]}
