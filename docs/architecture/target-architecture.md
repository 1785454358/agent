# 目标架构：Contract 驱动的深度研究运行时

> 状态：设计与主体已实现，部分层已接入生产执行路径，部分为可运行库。本文档描述目标架构，并标注每层的落地状态。

> 2026-11-15 实施更新：已按[重构方案](2026-11-14-controller-refactor-design.md)收敛为统一研究循环，Controller 可通过配置接入 Harness，支持任务级恢复、版本化补查及定向补读。默认仍为 legacy，尚未经过真实模型同题质量对比，不宣称达到市场产品水平。Contract/Critic/Controller/Scheduler 是内核内部组件，不是独立服务；通用多执行器平台后置。

## 1. 目标

把深度研究 Agent 从「三种策略名决定一切」重构为：

> 在**可审计、可复现、成本有界**的前提下，最大化「有证据支持的回答质量」。

核心判断：**最优架构不是选 Plan-and-Execute 还是 Multi-Agent，而是把「研究」建模成三件东西**：

1. 一份类型化的**研究契约**（要回答什么、什么算完成）
2. 一张类型化的**任务 DAG**（怎么分工、依赖是什么）
3. 一个**证据平面**（每个结论凭什么成立）

Workflow / ReAct / orchestrator-workers 都只是运行时的**执行策略**，由控制器按任务形态选择，而不是写死在代码里的三种模式。

## 2. 分层架构

```text
用户问题
    ↓
ResearchContract        目标 / 用户约束 / 验收标准 / 来源政策 / 预算 / 风险 / 歧义
    ↓
可选澄清                高风险且歧义大时暂停提问（HITL）
    ↓
ResearchPlan DAG        类型化任务、依赖、输入输出、完成条件、预算、revision
    ↓
PlanCritic              结构 / 权限 / 需求覆盖 / 预算可行性，执行前拒绝坏计划
    ↓
Adaptive Controller     选择 direct / retrieve / loop / fanout / dag，定并发
    ↓
DAG Scheduler           ready-set、拓扑排序、并发、失败阻断、恢复
    ↓
EvidenceGraph           Source → Evidence → Span → Claim 的证据链
    ↓
VerificationPlane       claim 支持性 / 覆盖 / 矛盾 / 来源质量 / 补查建议
    ↓                         ↘
Synthesizer              未通过 → 新 revision / 有限补查
    ↓
统一定案                completed / partial / failed / cancelled
```

## 3. 各层职责

| 层 | 拥有什么 | 绝不能做什么 |
|---|---|---|
| Contract | 目标、约束、验收标准 | 不生成事实 |
| Plan | 任务 DAG、依赖、预算、revision | 不负责执行 |
| Critic | 结构、权限、覆盖、预算校验 | 不做研究取材 |
| Controller | 选择深度/执行器、定并发 | 不做语义评估 |
| Scheduler | ready-set、拓扑、失败阻断、恢复 | 不回答用户问题 |
| Execution | retrieve / loop / fanout / dag | 只执行任务，不改全局计划 |
| Evidence | 原文、版本、span | 不接受模型自报坐标 |
| Verification | 支持性、覆盖、矛盾、质量 | 不生成新内容 |
| Synthesizer | 组织答案 | 不引入未验证 claim |
| Runtime | 网关、账本、预算、checkpoint、队列 | 不依赖模型自觉 |

关键原则：**模型是建议引擎，宿主是裁决引擎**。每一层都可以单独替换和评测。

## 4. 数据契约

### 4.1 ResearchContract（不可变，revision 只增）

```text
run_id, goal
user_constraints[]                用户明说
assumptions[]                     模型补充，必须可核查
requirements[]                    可判定的验收标准
source_policy{ mode, domains, publication_years }
risk                              low/medium/high
budget{ max_model_calls, max_input_tokens, max_seconds, max_cost_usd, finishing_calls }
ambiguity{ level, questions }     高风险 + 高歧义必须先澄清
revision / parent_revision / revision_reason
```

不变量：revision 不能清空验收标准；只有宿主能修订。

### 4.2 ResearchPlan（append-only DAG）

```text
plan_id, run_id, contract_revision, revision
tasks[]                          每个任务：
    id, type(discover/verify/compare/synthesize/compute)
    objective, in_scope, out_of_scope
    requirement_ids, depends_on, capabilities
    query_seeds, expected_output, acceptance, budget
    execution_hint(auto/direct/retrieve/loop/fanout)
stop_conditions[], replan_triggers[]
```

不变量：无环；revision 需父版本 + 原因。fanout/dag 是调度形状；当前生产适配器生成独立 discover 任务并使用 retrieve，其他任务/执行器在分派前明确拒绝，不把库中类型存在当作生产支持。

### 4.3 EvidenceGraph

```text
Source(url, title, quality)
  → Evidence(id, version, content_hash, status)
    → EvidenceSpan(id, start, end, quote)
      → Claim(id, text, confidence, supports, status)
```

不变量：Claim 必须落在宿主解析出的 EvidenceSpan；accepted Claim 要求证据 ACTIVE、版本/哈希匹配、来源 eligible、原文区间与 quote 完全一致。

### 4.4 VerificationResult（唯一质量决策来源）

```text
graph, coverage
accepted_claims
issues[]
recommended_action  continue/replan/synthesize/partial/stop
```

不变量：`assessment.sufficient` 不能单独决定完成；coverage 只依据 host-accepted Claim 规整。

## 5. 控制流

```python
async def run(contract):
    if contract.requires_clarification:
        return await clarify(contract)

    plan = await planner.plan(contract)      # 模型提议
    plan = critic.review(plan)               # 宿主校验，未通过即拒
    decision = controller.decide(plan)       # 形状 + 每任务执行器 + 并发
    scheduler = Scheduler(plan, decision.max_parallel)

    while not scheduler.finished:
        batch = scheduler.next_batch()
        results = await executor.run(batch, decision.task_modes)
        for task, outcome in zip(batch, results):
            scheduler.mark_completed(task) or scheduler.mark_failed(task)

    verdict = verifier.evaluate(state, plan)
    if not verdict.coverage_complete and rounds_left:
        plan = planner.replan(plan, verdict.missing)   # 有限补查
        continue
    return synthesizer.write(state, contract, plan, verdict)
```

## 6. 关键不变量（跨层）

1. `completed` 唯一定义：全部验收通过 + 无阻塞缺口 + 计划完成 + 回答已生成。
2. 评估失败只产生明确降级，不保留旧 assessment 冒充本轮结果。
3. 已通过的 Claim 不因后续模型调用失败而丢失。
4. Planner 不能读工具正文形成事实；Executor 不能改全局计划。
5. 所有最终引用经过同一验证平面。
6. 预算在执行前预留成稿额度。
7. 并行只优化速度，不改变验证结果；调度顺序确定性化。
8. 每个任务边界持久化（checkpoint + ledger + budget）。

## 7. 模块与文件映射

### 7.1 新契约层（`backend/src/deeptrace/research/`）

| 文件 | 职责 | 状态 |
|---|---|---|
| `contract.py` | `ResearchContract`、`ContractBudget`、`SourcePolicy`、`ResearchAmbiguity` | 已实现 + 可持久化 |
| `plan.py` | `ResearchPlan`、`PlanTask`、`TaskBudget`、`ExecutionMode`、DAG 校验 | 已实现 |
| `critic.py` | `PlanReview`、`review_plan` 执行前校验 | 已实现 |
| `controller.py` | `ExecutionShape`、`ControllerDecision`、`decide_execution` | 已实现 |
| `scheduler.py` | `PlanScheduler`、`TaskRunStatus`，ready-set / 失败阻断 / 恢复 | 已实现 |
| `evidence_graph.py` | `EvidenceSource/EvidenceSpan/Claim/EvidenceGraph`、`build_evidence_graph` | 已实现 + 已接入 evaluator/Writer |
| `verification.py` | `VerificationResult`、`verify_evidence_graph`、`project_verification_result` | 已实现 + 已接入 finalize |
| `adapters.py` | 把 legacy planner 输出转成 Contract + Plan | 已实现 |
| `runtime.py` | 规划、调度、取材、验证、有限补查的统一图 | 已实现，可选接入 Harness |
| `planning.py` | 初始契约快照、单次运行初始化、目标明确的计划修订 | 已实现，runtime 只负责控制流 |
| `execution.py` | 上下文、任务尝试额度、执行能力校验及模式身份 | 已接入统一图 |
| `state.py` | 计划历史与任务结果 checkpoint 通道 | 已验证 SQLite 与嵌套 Harness 重启恢复 |
| `quality.py` | 评估失败时重新验证并保留旧发现，不沿用旧覆盖率 | 已接入统一图 |

### 7.2 已接入生产执行路径的改动

| 文件 | 改动 |
|---|---|
| `strategies/evidence_evaluation.py` | 生成 `VerificationResult`；修复「失败 repair 丢弃已通过 findings」 |
| `strategies/{workflow,plan_execute,multi_agent}/nodes.py` | finalize 以 `verified_coverage_complete` 为准 |
| `strategies/common.py` | `verified_coverage_complete` 辅助 |
| `strategies/evaluation_materials.py` | 评估视图携带 Evidence + 正文供宿主校验 |
| `harness/graph.py` | `_mode_node` 接收 verification；`_finalize_turn` 以验证覆盖定完成 |
| `harness/state.py` | `TurnState.verification` |
| `domain/response.py` | `ResponseInput.verified_finding_ids` |
| `responses/graph.py` + `responses/evidence.py` | Writer 只消费 accepted Claim 及其源材料 |
| `harness/checkpoint.py` | 新类型加入严格 allowlist |
| `persistence/schema.py` | 补 `tool_executions` 迁移列（历史 bug 修复） |

### 7.3 独立入口

| 文件 | 用途 |
|---|---|
| `backend/src/deeptrace/run_controller.py` | `python -m deeptrace.run_controller "<问题>"` 实测入口 |

## 8. 当前状态与待办

**已完成**：统一规划/取材/验证循环；三种对外模式兼容；范围审查与定向补读复用；缺口补查计划版本链；普通分支失败隔离；独立图及生产 Harness 的任务级恢复；任务尝试调用上限与页数限制；绑定生产持久化预算；Review 绑定计划摘要；有效发现保留；Writer 审查失败及空白回答不误报完成。

启用方式：`DEEPTRACE_RESEARCH_ORCHESTRATOR=controller`；默认 `legacy`。Plan-and-Execute 配置顺序执行，另两种允许有界并行，复用同一个研究图。没有新增 AUTO 对外模式、任务数据库或额外模型审查层。

需求类型现为不可变值对象，已封存的验收标准只能通过新契约 revision 改变。独立持久化图在同一 thread 开始新 run 时重置任务结果、证据、验证与诊断通道；传入 `None` 恢复原 run 则保留已完成分支。补查直接基于原契约构建任务，不重新扩张目标。评测可用 `--orchestrator legacy|controller` 显式指定编排器，实验名与 metadata 均记录实际配置。

**待办（按序）**：

1. 固定数据版本、模型、配置与预算，开展 controller/legacy 同题配对评测并检查原始回答。
2. 事实覆盖允许多段、多来源；综合交付由 Writer 与回答审查验证，继续量化其完整性和推导质量。
3. 质量不退化后切换默认入口，再删除仍承担回退职责的旧路由与策略；避免提前删除。
4. 根据实际任务瓶颈决定是否增加新的执行能力，不提前建设通用 Agent 平台。

## 9. 迁移阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 基线测试 + 完成语义锁定 | ✅ |
| Phase 1 | Contract + EvidenceGraph + Verification | ✅ |
| Phase 2 | Plan DAG + Critic | ✅ |
| Phase 3 | 验证平面接入 evaluator/Writer/finalize | ✅ |
| Phase 4 | 统一运行内核与任务边界恢复 | ✅ |
| Phase 5 | 三模式可选接入 Harness | ✅；默认切换及旧策略删除待质量对比 |
| Phase 6 | 冻结语料同题模型评测 + planner/evaluator 迭代 | ⬜ 待办，模型评测不称为确定性测试 |

2026-11-15 已完成一次[北京 3 天 2 晚、每人 2000 元真实测试](../benchmarks/2026-11-15-beijing-controller-live/README.md)：119.32 秒、11 次模型尝试、88,100 token，结果 partial。完整路径可运行，但暴露规划降级、来源政策扩大、局部覆盖误判和预算占位问题；本次质量检查未通过，不据此切换默认入口。尚未完成新旧内核配对评测。

## 10. 实测与验证方法

- 单元/契约测试：`uv run --no-sync pytest tests/research -q`。
- 全量后端：`uv run --no-sync pytest -m "not real" -q`；2026-11-15 最新实测 1606 passed、1 deselected、36 warnings，56.38 秒。包含原有 SDK 警告及 aiosqlite 事件循环关闭后的后台线程警告。
- 真实模型评测：`uv run python -m deeptrace.evaluation run --mode workflow --max-examples 10 --judge`（30 题冻结语料，`deeptrace-grounded-v1`；调用模型与 LangSmith，不是确定性离线测试）。分别设置编排开关，并固定 `--dataset-version` 后对比。
- 单题 live：`uv run python -m deeptrace.run_controller "<问题>"`（仅用于快速探查，不适合下结论）
