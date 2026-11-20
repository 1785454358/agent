"""Writing policies adapt space to the task while keeping explicit caller caps."""

import re
from dataclasses import dataclass, replace

from deeptrace.domain import ResponseInput, ResponseMode
from deeptrace.harness.context import HarnessContext

CITATION_RULE = (
    "引用规则：事实性表述就近标注支持它的资料编号 [n]，n 只能取下面列出的编号；"
    "必须使用半角方括号（如 [1]），不要编造引用。"
    "归纳或建议应说明依据与适用条件，不能把推断写成原文事实。"
)
MARKDOWN_RULE = (
    "格式规则：content正文可以使用Markdown。按需使用短标题、列表、比较表和带语言名的代码块；"
    "简单问题直接回答，不强行分节。段落之间空行。不要用代码块包裹整份答案。"
    "引用编号[n]保持为普通文本，不生成脚注定义；不输出HTML或图片。"
)

MAX_ANSWER_CONTENT = 2_000
MAX_DETAILED_CONTENT = 8_000
MAX_BRIEF_CONTENT = 8_000
MAX_REPORT_CONTENT = 50_000
ANSWER_SOURCE_CHARS = 6_000
BRIEF_SOURCE_CHARS = 6_000
REPORT_SOURCE_CHARS = 20_000

_WRITING_GUIDANCE = (
    "先给出直接结论，再解释支撑结论的原因、条件与实际意义。"
    "方案/推荐任务先给完整可用方案，再集中列真正的限制，避免每段反复免责声明。"
    "区分原文事实、明确假设下的预算分配和建议；建议不伪装成已核实市场实价。"
    "预算须说明人数、日期口径及分摊，逐项算账并解释余量用途，不用大额机动占位凑出预算上限。"
    "合理参考区间可以注明来源、时间与波动性；不能因缺官方统一定价就禁止住宿餐饮预算建议。"
    "逐项回答用户明确询问的对象和维度，不用相关事实代替答案。"
    "区分容器对象与其某个字段、静态输入与可变状态；不能把对象的全部属性写成某个字段的内容。"
    "首句结论、标题和表格主语须与正文的对象层级一致；只问某字段时只列该字段内容，"
    "其他组件仅作必要对照，不扩写成该字段的组成列表。"
    "比较题按相同维度比较，给出有证据的取舍与适用场景；"
    "技术题在有依据且有助理解时给简短示例，示例不是已运行验证的事实。"
    "用户询问流程、恢复、配置或API行为时，若原文给出关键调用及参数，"
    "说明最小调用与执行顺序，不以‘支持某能力’代替具体怎么触发；"
    "同时解释有据的重执行、失败或副作用边界，不编造示例API。"
    "综述应说明代表性成果的贡献及其边界，避免只罗列论文和术语。"
    "原文不足时保留已支持的具体内容，区分无法确认的事实与可提出的验证建议；"
    "如果用户询问无法从材料得出的指标，说明缺少哪些测量输入或核查步骤，建议明确标为建议。"
    "用自然清楚的中文，篇幅是上限而非目标，不复述问题、不凑字数。"
)


@dataclass(frozen=True)
class ResponsePolicy:
    mode: ResponseMode
    instructions: str
    max_content_chars: int
    per_source_chars: int


ANSWER_POLICY = ResponsePolicy(
    ResponseMode.ANSWER,
    _WRITING_GUIDANCE,
    MAX_ANSWER_CONTENT,
    ANSWER_SOURCE_CHARS,
)
BRIEF_POLICY = ResponsePolicy(
    ResponseMode.BRIEF,
    "用短小标题、要点或表格输出结构化摘要，突出结论与取舍。" + _WRITING_GUIDANCE,
    MAX_BRIEF_CONTENT,
    BRIEF_SOURCE_CHARS,
)
REPORT_POLICY = ResponsePolicy(
    ResponseMode.REPORT,
    "生成正式报告，包含概述、分节论述与结论，各项论述对应证据。" + _WRITING_GUIDANCE,
    MAX_REPORT_CONTENT,
    REPORT_SOURCE_CHARS,
)

_DETAILED = re.compile(
    r"详细|深入|全面|系统[地性]?|逐项|综述|年度|进展|"
    r"\b(detailed|in.depth|comprehensive|step.by.step|survey)\b",
    re.IGNORECASE,
)
_COMPARISON = re.compile(
    r"比较|对比|区别|异同|\b(compare|contrast|differences)\b", re.IGNORECASE
)


def effective_policy(
    policy: ResponsePolicy,
    context: HarnessContext,
    response_input: ResponseInput,
) -> ResponsePolicy:
    limit = policy.max_content_chars
    # Custom policies already carry an explicit ceiling. Only the built-in
    # answer policy opts in to task-dependent expansion.
    if policy == ANSWER_POLICY:
        research = response_input.research_outcome
        requirement_count = len(research.requirements) if research else 0
        if requirement_count >= 6 or _DETAILED.search(response_input.question):
            limit = MAX_DETAILED_CONTENT
        elif requirement_count >= 3 or _COMPARISON.search(response_input.question):
            limit = 4_000
    cap = context.response_max_content_chars
    if cap is not None:
        if type(cap) is not int or cap < 1:
            raise ValueError("response_max_content_chars must be a positive integer")
        limit = min(limit, cap)
    return replace(policy, max_content_chars=limit)
