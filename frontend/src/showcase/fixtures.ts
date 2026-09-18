import type { ResearchMode, RunEvent } from "../api/types";

export interface ShowcaseScenario {
  mode: ResearchMode;
  question: string;
  summary: string;
  events: RunEvent[];
  answer: string;
  sources: string[];
  sourceCodeUrl: string;
}

const REPOSITORY = "https://github.com/1785454358/agent";

export const SHOWCASE_SCENARIOS: Record<ResearchMode, ShowcaseScenario> = {
  workflow: {
    mode: "workflow",
    question: "模型与外部工具如何经过统一治理？",
    summary: "固定流程快速验证 ModelGateway、ToolGateway 与证据边界。",
    events: [
      {
        id: 1,
        event_type: "run.started",
        message: "Workflow 已接收研究任务并固定原始约束",
      },
      {
        id: 2,
        event_type: "planning.completed",
        message: "生成 2 个互补查询并分配调用预算",
      },
      {
        id: 3,
        event_type: "tool.completed",
        tool: "search_web",
        message: "ToolGateway 完成权限、参数与预算校验",
      },
      {
        id: 4,
        event_type: "tool.completed",
        tool: "fetch_page",
        message: "抓取结果写入 Evidence Store，State 只保留 Evidence ID",
      },
      {
        id: 5,
        event_type: "run.completed",
        message: "Workflow 汇总证据并产生明确 Outcome",
      },
    ],
    answer:
      "DeepResearch 把模型与外部工具放在两个确定边界后面。ModelGateway 在调用 Provider 前校验 system instruction、original task 与 current constraints；ToolGateway 统一处理白名单、URL 安全、预算、重试、Ledger 和 Evidence。策略只决定怎样研究，不直接绕过这些边界。",
    sources: [
      `${REPOSITORY}/blob/main/backend/src/deeptrace/harness/model_gateway.py`,
      `${REPOSITORY}/blob/main/backend/src/deeptrace/tools/gateway.py`,
    ],
    sourceCodeUrl: `${REPOSITORY}/blob/main/backend/src/deeptrace/strategies/workflow`,
  },
  plan_execute: {
    mode: "plan_execute",
    question: "长时运行 Agent 如何避免恢复时重复执行外部工具？",
    summary: "Planner 拆分研究 todo，Executor 逐项执行，Evaluator 按证据决定补查或结束。",
    events: [
      {
        id: 1,
        event_type: "planning.completed",
        message: "Planner 根据原始任务与当前约束拆分 3 项可执行研究 todo",
      },
      {
        id: 2,
        event_type: "task.started",
        message: "Executor 选取下一个 todo，交给 Shared Agent Loop 执行",
      },
      {
        id: 3,
        event_type: "tool.completed",
        tool: "search_web",
        message: "无依赖搜索通过 ToolGateway 有界并行执行",
      },
      {
        id: 4,
        event_type: "replanning.completed",
        message: "Evaluator 根据证据缺口决定完成或生成补查 todo",
      },
      {
        id: 5,
        event_type: "run.recovered",
        message: "Checkpoint 恢复 Agent State，Ledger 恢复工具执行与幂等记录",
      },
      {
        id: 6,
        event_type: "research.completed",
        message:
          "Execution Policy 根据恢复后的状态生成 AgentOutcome；Finalize 汇总为 ResearchOutcome",
      },
    ],
    answer:
      "Planner 只根据原始任务、当前约束和会话背景拆分可执行研究 todo，Executor 再逐项交给 Shared Agent Loop。恢复时，Checkpoint 还原 Agent State，Ledger 提供已执行工具与幂等记录；它们都不负责产出结果。Agent Loop 恢复推进后，由 Execution Policy 根据 todo、证据、错误与预算生成 AgentOutcome，最后由 Plan-and-Execute Finalize 汇总各子任务为 ResearchOutcome。",
    sources: [
      `${REPOSITORY}/blob/main/backend/src/deeptrace/harness/policies/agent_context.py`,
      `${REPOSITORY}/blob/main/backend/src/deeptrace/harness/policies/execution.py`,
      `${REPOSITORY}/blob/main/backend/src/deeptrace/harness/checkpoint.py`,
      `${REPOSITORY}/blob/main/backend/src/deeptrace/persistence/execution_ledger.py`,
    ],
    sourceCodeUrl: `${REPOSITORY}/blob/main/backend/src/deeptrace/strategies/plan_execute`,
  },
  multi_agent: {
    mode: "multi_agent",
    question: "三个策略怎样共享同一个 Agent Runtime？",
    summary: "Supervisor 负责任务协调，Researcher 复用同一个受治理循环。",
    events: [
      {
        id: 1,
        event_type: "run.started",
        message: "Multi-Agent 已接收研究任务",
      },
      {
        id: 2,
        event_type: "supervisor.planned",
        message: "Supervisor 拆分三个相互独立的研究方向",
      },
      {
        id: 3,
        event_type: "researcher.started",
        message: "Researcher 分支通过共享 Agent Loop 并行执行",
      },
      {
        id: 4,
        event_type: "tool.completed",
        tool: "search_web",
        message: "共享 ToolGateway 控制并发、预算与幂等",
      },
      {
        id: 5,
        event_type: "research.completed",
        message: "Reducer 合并各分支 Evidence 与未解决缺口",
      },
      {
        id: 6,
        event_type: "run.completed",
        message: "Supervisor 评估完整性并返回统一 ResearchOutcome",
      },
    ],
    answer:
      "Workflow、Plan-and-Execute 和 Multi-Agent 只负责不同的 orchestration strategy。Multi-Agent 的 Supervisor 做拆解、派发与评估，每个 Researcher 都调用同一个 Shared Agent Loop，因此模型信封、工具权限、预算、ToolMessage 配对、Checkpoint 和 AgentOutcome 不变量不会因策略不同而分叉。",
    sources: [
      `${REPOSITORY}/blob/main/backend/src/deeptrace/harness/agent_executor.py`,
      `${REPOSITORY}/blob/main/backend/src/deeptrace/strategies/multi_agent/nodes.py`,
    ],
    sourceCodeUrl: `${REPOSITORY}/blob/main/backend/src/deeptrace/strategies/multi_agent`,
  },
};
