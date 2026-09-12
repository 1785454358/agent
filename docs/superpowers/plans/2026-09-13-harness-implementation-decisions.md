# Harness 重构实施决策记录

本文件记录 Harness 重构（Roadmap Plan 1–8）执行过程中的关键实现决策、与计划文档的偏差及其理由，供回顾与面试材料引用。按 Plan 顺序追加。

## Plan 3：Workflow 与 Response 纵向切片（2026-09-13 完成）

### 提交序列

| 提交 | 内容 |
| --- | --- |
| 341dad6 | feat: define research response contracts（Task 1） |
| ffba8db | feat: add research topic subgraph（Task 2） |
| 05e19be | feat: add workflow research strategy（Task 3） |
| ad78b5b | feat: add evidence-backed response graphs（Task 4） |
| b3be85b | feat: connect workflow and response subgraphs（Task 5） |
| 8b3b340 | feat: route workflow runs through application service（Task 6） |
| （本次） | test: lock workflow response vertical slice（Task 7） |

### 关键契约决策

1. **跨子图契约入 domain 层（偏离计划文件布局）。**
   计划 Task 2 把 `ResearchTopicInput/Outcome` 放在 `strategies/topic/state.py`。实际落地为
   `src/deeptrace/domain/research.py`（TopicStepError 一并纳入），策略包只保留图状态与节点。
   理由：设计规范 §8 要求"子图仅通过可序列化输入输出契约交换数据"，这类契约属领域层；
   同时避免 `harness/checkpoint.py`（严格序列化白名单）反向依赖 strategies 包。

2. **严格 checkpoint 序列化白名单扩展。**
   新进入图状态的模型（ResearchTopicInput/Outcome、TopicStepError、QueryPlan、
   WorkflowEvaluation、ResponseDraft）全部加入 `HARNESS_STATE_MSGPACK_TYPES`。
   未注册模型仍被拒绝（还原为 dict），测试持续锁定该行为。

3. **子图调用契约统一为 `outcome` 键 + 扁平输入。**
   顶层图以 `ResearchInput.model_dump(mode="json")`（扁平 dict）调用策略子图，
   子图最终状态中的 `outcome` 键承载 `ResearchOutcome`/`ResponseOutcome` 跨界。
   计划 Task 5 的"Only ResearchOutcome and ResponseOutcome cross child-graph boundaries"
   据此落地；Plan 1 的脚本化子图测试同步更新。

4. **ToolCaller 角色由 mode 派生。**
   `ResearchTopicInput.mode` 决定 `CallerRole`：workflow→WORKFLOW_GRAPH、
   plan_execute→PLAN_EXECUTE_EXECUTOR、multi_agent→MULTI_AGENT_RESEARCHER。
   topic 子图因此可被 Plan 4/5 复用，且 Supervisor 永远不会经由它获得工具权限。

5. **每分支最小 URL 授权。**
   fetch 分支的 `UrlAuthorization(source=SEARCH_RESULT, urls={本分支 URL})`
   在节点内从"仅来自搜索结果预览"的分支状态构造；select_urls 节点用
   `validate_public_url` 二次过滤（`normalize_url_before_fetch` 不拒绝内网地址），
   并做稳定去重与 max_pages 截断。

6. **确定性调用 ID。**
   `call_id = call-<sha256(run_id, stage, query, url, ordinal)[:32]>`，
   `request_id = request-<sha256(research_topic, thread, run, query)[:32]>`，
   跨 checkpoint 重放稳定，配合 Tool Execution Ledger 实现恢复不重复副作用。

7. **响应模式选择为确定性边界策略（responses/citations.py）。**
   REPORT 触发条件：尾部以"报告/完整报告/正式报告/报告形式/报告格式/report"结尾，
   或 `报告形式/报告格式` 出现，或英文动词短语 `generate|write|produce|create|draft … report`；
   BRIEF 触发词：总结/摘要/简报/对比/归纳/要点/brief/summary/tldr；
   其余一律 ANSWER。"这份报告的作者是谁"等名词用法不触发 REPORT。

8. **引用校验语义。**
   `validate_citations(draft, loaded_evidence_ids)` 只保留能映射到已加载 Evidence 的
   `[n]` 标记（按首次出现顺序稳定去重），未知标记从正文中移除、绝不伪造替代；
   全部失效时输出 `partial_reason="no_supported_citations"`，由图节点给出
   可追溯的来源列表作为部分结果。生成失败时同理（`generation_failed`、`no_evidence`）。

9. **图节点并发写入必须声明 reducer。**
   Workflow 的 `unresolved_gaps`、`topic_outcomes`、`evidence_ids`、`executed_steps`
   均为 Annotated reducer 通道（去重/按 query 替换/累加），避免
   `INVALID_CONCURRENT_GRAPH_UPDATE`；`findings` 仅由 evaluate 单节点写入，保持普通字段。

10. **应用服务身份边界在副作用之前。**
    `ResearchApplicationService.invoke` 先校验 `config.configurable.thread_id`
    存在且等于 `request.thread_id`（否则抛 `ExecutionIdentityMismatch`，零模型/工具/事件调用），
    再构造 Harness State 并调用顶层图；显式 `response_mode` 通过
    `configurable.response_mode_override` 传入，`select_response_mode` 节点优先采用。

11. **RunRecord 模式规范化。**
    `RunMode` 扩展为 canonical+legacy 字面量并集；`RunRecord.mode` 的 before 校验器
    将 `basic→workflow`、`deep→plan_execute` 规范化（读取旧记录即得规范值），
    新写入一律规范值。本地运行时旧工厂路径通过
    `{workflow: basic, plan_execute: deep}` 反向映射保持可用，未删除任何旧路径。

12. **租户标识取 workspace_id。**
    Graph 节点调用 Tool Gateway / Evidence Store 时以 `HarnessContext.workspace_id`
    作为 `tenant_id`，与设计 §13.4 的 workspace 作用域命名空间一致。

### 测试基线

- Plan 3 完成时：非真实套件 487 passed，`compileall` 通过。
- 真实 API（真实模型/Tavily）验证留待 Plan 8 评测阶段按需执行。

## Plan 4：Plan-and-Execute 策略（2026-09-13 完成）

计划文档：`docs/superpowers/plans/2026-09-13-plan-execute-strategy.md`（本次新撰写，路线图原本未给出）。

13. **循环拓扑：队列驱动而非逐任务评估。**
    拓扑为 `plan → select_task →(有任务)→ execute_task → select_task`、
    `(队列空)→ evaluate →(replan 且未超限)→ replan → select_task`、
    `(complete/block/解析失败/超限)→ finalize`。即先耗尽计划队列再做一次评估，
    replan 生成新队列后重新进入同一 select_task 循环；重规划上限在条件边内强制。
    首版拓扑（每个任务后立刻评估）会让评估器提前结束队列，已修正。

14. **任务即查询。** 任务表示为归一化查询字符串（≤6 条、稳定去重），
    单任务执行直接复用 ResearchTopicGraph（mode=PLAN_EXECUTE），
    失败任务记入 gaps，兄弟任务证据保留；replan 生成的查询按 completed_tasks 去重，
    生成不出新任务时以 `no_new_tasks_to_plan` 缺口终局（`max_replans_reached` 或
    `insufficient_evidence`）。

15. **模型输出解析助手下沉共享模块。**
    `strategies/model_io.py` 提供 `payload_text/parse_json_object`（去 markdown 围栏、
    容错 JSON 解析），workflow 与 plan_execute 共用，消除两份拷贝。

16. **测试夹具预算作用域覆盖三种模式×三个 caller。**
    GatewayFixture 为 run/mode/agent 三级、全部 canonical 模式与典型 caller_id
    预配置预算，避免策略子图因未配置作用域在网关内报错。

17. **测试基线：** Plan 4 完成时非真实套件 501 passed。

## Plan 5：Multi-Agent 策略（2026-09-13 完成）

计划文档：`docs/superpowers/plans/2026-09-13-multi-agent-strategy.md`（本次新撰写）。

18. **Researcher 即 Topic 子图实例。**
    `Send("researcher", ResearcherBranchState(...))` 为每个研究方向派生独立分支，
    分支内以 `ResearchTopicInput(mode=MULTI_AGENT, caller_id=researcher-{index})`
    调用共享的 ResearchTopicGraph——研究员天然拥有隔离的任务视图与网关侧配额，
    一个研究员失败只记自身缺口，兄弟证据经 reducer 合并保留。

19. **Supervisor 结构性无网络权限。**
    supervisor_plan / supervisor_evaluate / follow_up 三个节点只访问 model_gateway
    与 evidence_store.get_many，从不触碰 ToolGateway；测试断言网关调用记录中的
    caller_id 全部以 `researcher-` 开头。`dispatched_queries` 通道（reducer 去重）
    保证 follow_up 不会重复派发已研究方向。

20. **follow_up 路由返回 Send 列表。**
    follow_up 节点后若返回字符串边，researcher 节点会拿到整份主状态而非分支输入
    （KeyError: query）；必须与首次派发一致地返回 `Send` 列表，空 assignments 时
    返回 "finalize"。这是 Send 拓扑的通用陷阱，已记录。

21. **终止原因语义：** `completed` / `no_sources` / `max_follow_ups_reached` /
    `insufficient_evidence`；默认一轮 follow-up（max_follow_ups=1）。

22. **测试基线：** Plan 5 完成时非真实套件 514 passed。

## 后续 Plan 决策（待补充）

- Plan 6（会话与记忆）：待实施。
- Plan 5（Multi-Agent）：待实施。
- Plan 6（会话与记忆）：待实施。
- Plan 7（MySQL 与分布式恢复）：待实施。
- Plan 8（可观测性、评测与切换）：待实施。
