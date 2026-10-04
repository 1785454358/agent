import { isTerminalStatus, type RunEvent, type RunStatus } from "../api/types";

export const RESEARCH_STAGES = [
  { id: "prepare", label: "理解问题" },
  { id: "plan", label: "制定计划" },
  { id: "search", label: "检索资料" },
  { id: "read", label: "阅读原文" },
  { id: "review", label: "核对证据" },
  { id: "write", label: "生成回答" },
] as const;

type StageId = (typeof RESEARCH_STAGES)[number]["id"];
type OperationState = "running" | "done" | "returned" | "recorded" | "failed" | "retry" | "retried";

interface EventMeaning {
  key: string;
  stage: StageId | null;
  title: string;
  description: string;
  state: OperationState;
  tasks?: string[];
  gaps?: string[];
  round?: number;
  boundary?: boolean;
  callId?: string;
}

export interface ResearchOperation extends EventMeaning {
  time?: string;
  endedTime?: string;
  completedCalls: number;
  failedCalls?: number;
}

/** A compact stage summary per explicit research round; details keep chronology. */
function summarizeRounds(operations: ResearchOperation[], activeStage?: StageId | null) {
  const rounds = new Map<number, ResearchOperation[]>();
  for (const operation of operations) {
    const round = operation.round ?? 1;
    rounds.set(round, [...(rounds.get(round) ?? []), operation]);
  }
  const activeRound = operations.at(-1)?.round ?? 1;
  return [...rounds].flatMap(([round, items]) => RESEARCH_STAGES.flatMap(stage => {
    const related = items.filter(item => item.stage === stage.id);
    if (!related.length) return [];
    const last = related[related.length - 1];
    const calls = (tool: string) => related.filter(item => item.key === `tool:${tool}`).reduce((count, item) => count + item.completedCalls, 0);
    const completedCalls = related.reduce((count, item) => count + item.completedCalls, 0);
    const failedCalls = related.filter(item => item.state === "failed").length;
    const plan = [...related].reverse().find(item => item.tasks?.length);
    let description = last.description;
    if (stage.id === "prepare") description = "接收问题，整理研究上下文";
    if (stage.id === "plan") description = plan?.tasks?.length ? `本轮计划包含 ${plan.tasks.length} 个研究任务` : "制定或更新本轮研究计划";
    if (stage.id === "search") description = calls("search_web") ? `已完成 ${calls("search_web")} 次资料检索` : "按本轮计划查找相关资料";
    if (stage.id === "read") description = `抓取原文 ${calls("fetch_page")} 次 · 阅读证据 ${calls("read_evidence")} 次`;
    const state: OperationState = stage.id === activeStage && round === activeRound ? "running"
      : failedCalls && !completedCalls && related.every(item => item.state === "failed") ? "failed" : "recorded";
    return [{ ...last, key: `summary:${round}:${stage.id}`, round,
      title: round > 1 && stage.id === "plan" ? `第 ${round - 1} 轮补查 · 制定计划` : stage.label,
      description, state, completedCalls, failedCalls, tasks: plan?.tasks,
      boundary: round > 1 && stage.id === "plan",
    }];
  }));
}

const TOOLS: Record<string, [StageId, string, string]> = {
  search_web: ["search", "搜索网页资料", "检索与研究问题相关的网页资料"],
  fetch_page: ["read", "抓取网页内容", "获取来源网页的正文内容"],
  read_evidence: ["read", "阅读原文证据", "读取已抓取的原文，选取与问题相关的内容"],
  search_memory: ["prepare", "检索历史研究", "查找可供本次研究参考的历史记录"],
  record_findings: ["review", "整理研究发现", "记录本轮取材得到的结论与依据"],
  write_todos: ["plan", "更新研究任务", "记录本轮待办事项与执行安排"],
  finish_research: ["review", "提交本轮研究结果", "将研究发现交给后续评估与汇总"],
};

const PHASE_EVENTS: Record<string, [StageId, string, string]> = {
  "run.started": ["prepare", "接收研究问题", "开始处理本次研究任务"],
  "agent.context_view": ["prepare", "准备研究上下文", "整理问题、约束与已有材料，供模型决策"],
  "planning.started": ["plan", "制定研究计划", "将问题拆分为可执行的研究任务"],
  "planning.completed": ["plan", "研究计划已记录", "研究任务进入后续执行流程"],
  "replanning.started": ["plan", "调整研究计划", "根据已有结果安排后续补查"],
  "replanning.completed": ["plan", "补查计划已记录", "继续执行调整后的研究任务"],
  "plan.finish_rejected": ["review", "继续补充证据", "需求覆盖评估未通过，继续查证"],
  "task.started": ["search", "执行研究子任务", "按计划推进当前研究方向"],
  "supervisor.planned": ["plan", "拆分研究方向", "协调多个相对独立的研究任务"],
  "supervisor.dispatched": ["plan", "分配研究任务", "将研究方向交给对应分支"],
  "supervisor.retry": ["plan", "安排补充研究", "继续查证尚需支持的研究方向"],
  "supervisor.reviewed": ["review", "评审研究结果", "汇总并检查各研究分支的结果"],
  "researcher.started": ["search", "研究分支开始执行", "推进已分配的研究方向"],
  "researcher.queued": ["search", "研究分支等待执行", "等待开始处理已分配的任务"],
  "researcher.completed": ["review", "研究分支返回结果", "将分支发现交给汇总环节"],
  "evidence.view": ["review", "整理证据片段", "选取后续核验与回答使用的原文片段"],
  "task.completed": ["search", "研究子任务结束", "本研究方向已返回结果"],
  "task.failed": ["search", "研究子任务未完成", "本研究方向执行失败"],
  "evaluation.started": ["review", "核对本轮证据", "逐项检查研究需求是否有原文支持"],
  "evaluation.completed": ["review", "核对本轮证据", "本轮证据检查已返回结果"],
  "research.batch_synthesis.started": ["review", "整理研究发现", "集中整理本批原文与引用依据"],
  "research.batch_synthesis.completed": ["review", "研究发现已整理", "将本批发现交给后续证据核验"],
  "research.batch_synthesis.failed": ["review", "研究发现待核验", "保留已读原文，继续核对证据"],
  "research.route": ["review", "确定下一步", "根据证据检查结果决定后续步骤"],
  "research.completed": ["review", "汇总研究结果", "汇集研究发现与尚需查证的内容"],
  "writing.started": ["write", "撰写研究回答", "依据研究材料组织最终回答"],
  "writing.completed": ["write", "回答撰写结束", "返回本次生成的回答内容"],
  "response.excerpts": ["write", "整理回答引用", "将原文材料交给回答生成环节"],
  "response.completed": ["write", "研究回答已返回", "本次回答生成流程已结束"],
  "run.completed": ["write", "研究执行已结束", "查看最终回答与资料来源"],
  "run.recovered": ["prepare", "恢复研究记录", "从已保存的状态继续处理任务"],
};

const STOP_REASONS: Record<string, string> = {
  iteration_limit: "研究分支已达到迭代上限", max_iterations: "研究分支已达到迭代上限",
  budget_exhausted: "研究预算已用完", max_replans_reached: "已达到补查轮数上限",
  no_research_progress: "补查未获得新增证据", coverage_complete: "研究需求已有原文支持",
  evaluation_unavailable: "证据评估未获得有效结果", insufficient_evidence: "部分研究需求仍需原文支持",
  incomplete_plan: "研究任务仍有未完成事项", topic_execution_failed: "研究子任务执行失败",
};

export function researchStopReason(reason?: string) {
  return reason ? STOP_REASONS[reason] : undefined;
}

function textList(encoded?: string): string[] {
  try {
    const value: unknown = JSON.parse(encoded ?? "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  } catch { return []; }
}

function meaning(event: RunEvent): EventMeaning | null {
  if (event.event_type === "done") return null;
  if (event.event_type === "agent.tool_observation" && !event.details?.call_id) return null;
  const tool = event.tool ?? event.details?.tool;
  const toolMeaning = tool ? TOOLS[tool] : undefined;
  const isTool = event.event_type.startsWith("tool.") || event.event_type === "agent.local_tool" || event.event_type === "agent.tool_observation";
  const definition = isTool ? toolMeaning : PHASE_EVENTS[event.event_type];
  const [stage, defaultTitle, defaultDescription] = definition ?? [null, "其他运行记录", "展开原始记录可查看详情"];
  let title = defaultTitle;
  let description = defaultDescription;
  const details = event.details;
  const tasks = textList(details?.tasks_json);
  const gaps = textList(details?.gaps_json).map(gap => gap
    .replace(/^[^:]+:missing:/, "需补充：")
    .replace(/^[^:]+:conflicting:/, "证据冲突："));
  const round = details?.round;
  const boundary = event.event_type.startsWith("planning.") || event.event_type.startsWith("replanning.");
  if (event.event_type.startsWith("replanning.")) {
    const prefix = round ? `第 ${round - 1} 轮补查` : "补充研究";
    title = `${prefix} · ${event.event_type.endsWith("started") ? "调整计划" : "计划已生成"}`;
    description = event.event_type.endsWith("started")
      ? details?.reason ?? "针对上一轮尚未解决的问题制定补查任务"
      : tasks.length ? `新增 ${tasks.length} 个研究任务，继续查证` : "本轮未生成新的补查任务";
  }
  if (event.event_type === "planning.completed") description = tasks.length ? `初始研究 · ${tasks.length} 个研究任务` : description;
  if (event.event_type.startsWith("task.") && details?.task) description = details.task;
  if (event.event_type === "evaluation.completed") {
    description = typeof details?.total === "number" && details.total > 0
      ? `本轮 ${details.covered ?? 0}/${details.total} 项研究需求已有原文支持` : "本轮证据检查已返回结果";
  }
  if (event.event_type === "research.route") {
    const reason = researchStopReason(details?.reason) ?? "依据本轮运行状态";
    if (details?.next_step === "replan") {
      title = "进入补查"; description = `${reason}，接下来重新规划研究任务`;
    } else {
      title = "结束取材 · 转入回答";
      description = `${reason}${details?.action === "replan" ? "；评估建议补查，但本次未进入再次规划" : "，整理已有证据生成回答"}`;
    }
  }
  if (isTool && details?.query) description = details.query;
  if (isTool && details?.url) description = details.url;
  let state: OperationState = "recorded";
  if (event.event_type.endsWith(".started")) state = "running";
  if (event.event_type.endsWith(".completed")) state = "done";
  if (event.event_type === "task.completed") state = "returned";
  if (event.event_type === "agent.tool_observation" && details?.ok) state = "done";
  if (details?.ok === false || event.message.includes("失败") || event.event_type.endsWith(".failed")) {
    state = "failed";
    description = details?.message ?? event.message;
  }
  if (event.event_type === "tool.retry") state = "retry";
  return { key: isTool ? `tool:${tool ?? "unknown"}` : event.event_type, stage, title, description, state,
    tasks, gaps, round, boundary, callId: details?.call_id };
}

/** Describe observed actions only; later stages never imply earlier ones succeeded. */
export function buildResearchProgress(events: RunEvent[], status?: RunStatus | null) {
  const operations: ResearchOperation[] = [];
  const seenIds = new Set<number>();
  const completedCallIds = new Set(events.filter(event => event.event_type === "tool.completed" || event.event_type === "agent.local_tool").flatMap(event => event.details?.call_id ? [event.details.call_id] : []));
  let contextSeen = false;
  let currentRound = 1;
  for (const event of events) {
    if (event.event_type === "agent.tool_observation" && event.details?.call_id && completedCallIds.has(event.details.call_id)) continue;
    if (event.id !== undefined) {
      if (seenIds.has(event.id)) continue;
      seenIds.add(event.id);
    }
    if (event.event_type === "agent.context_view") {
      if (contextSeen) continue;
      contextSeen = true;
    }
    const item = meaning(event);
    if (!item) continue;
    if (item.round !== undefined) currentRound = item.round;
    item.round = currentRound;
    const previous = operations.at(-1);
    // Failure/retry transitions remain visible even for the same tool.
    const mergeable = previous && previous.key === item.key && !item.boundary &&
      (!previous.callId || !item.callId || previous.callId === item.callId) &&
      !["failed", "retry"].includes(previous.state) &&
      (!["failed", "retry"].includes(item.state) || (previous.state === "running" && item.state === "failed"));
    const completedCall = (event.event_type === "tool.completed" || event.event_type === "agent.tool_observation") && item.state === "done" ? 1 : 0;
    if (mergeable) {
      previous.completedCalls += completedCall;
      previous.state = item.state;
      if (event.event_type === "tool.completed") previous.endedTime = event.ts;
      if (item.state === "failed" || event.details?.message || event.details?.url || event.details?.query) previous.description = item.description;
    } else {
      operations.push({ ...item, time: event.ts, completedCalls: completedCall });
    }
  }
  if (status && isTerminalStatus(status)) {
    for (const operation of operations) {
      if (operation.state === "running") operation.state = "recorded";
      if (operation.state === "retry") operation.state = "retried";
    }
  }
  const activeStage = status === "running" || status === "cancel_requested"
    ? [...operations].reverse().find((operation) => operation.stage)?.stage
    : undefined;
  const stages = RESEARCH_STAGES.map((stage) => ({
    ...stage,
    state: stage.id === activeStage ? "active" : operations.some((op) => op.stage === stage.id) ? "recorded" : "unrecorded",
  }));
  return { stages, operations, summary: summarizeRounds(operations, activeStage) };
}
