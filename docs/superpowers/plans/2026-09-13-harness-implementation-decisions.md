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

## Plan 6：会话与记忆生命周期（2026-09-13 完成）

分三个提交交付（791eac3 意图路由与多轮、3647942 记忆策略、本提交记忆接线）。

23. **意图路由为确定性边界策略。**
    `harness/policies/intent.py`：记忆更新/切换模式/增量研究/追问模式全部模式匹配，
    报告/简报措辞复用 `select_response_mode`。追问（有会话证据时）→ conversation
    直接走响应图，不触发研究；无证据时的报告措辞 → 先研究再报告。
    `requires_research=False` 的轮次 finalize 只看响应可用性。

24. **上下文滑动窗口。**
    `plan_context_window(messages, soft=24, hard=60)` 保留最近窗口，溢出消息经
    `RemoveMessage` 从会话状态移除；模型化结构压缩（summarizer 角色）留待 Plan 8
    接入真实网关后启用，当前为确定性裁剪 + 既有结构化摘要字段。

25. **记忆六问全部有可执行策略测试**（`tests/harness/memory/test_memory_policies.py`）：
    何时存（来源白名单：user_request/consolidation/repeated_preference；fact 必须有
    证据来源）、存什么（bounded 内容、唯一来源）、如何组织（scope/owner/kind 命名空间、
    跨租户不可见）、何时召回（research/incremental/report 自动触发，追问不召回） +
    排序（关键词重叠×10 + 新近度×5 + 置信度×3，状态门禁）、如何更新（同 subject
    版本链 + supersedes，同内容幂等）、如何遗忘（TTL→expired、30 天→stale、逻辑删除、
    物理删除）。

26. **记忆 Store 以 LangGraph Store 为底。**
    `InMemoryMemoryStore` 包装 `langgraph.store.memory.InMemoryStore`，键为
    `identity|v{version}`，被替代版本保留可查（审计轨迹）；identity =
    namespace|type|subject，id 由 identity+version 派生（确定性）。
    Plan 7 将其映射到 MySQL 实现。

27. **记忆接入顶层图。**
    `HarnessContext` 新增可选 `memory_store` 端口（向后兼容，默认 None）。
    图拓扑插入 `recall_memory`（classify_intent 之后、意图路由之前）与
    `consolidate_memory`（研究完成之后、响应之前）；MEMORY_UPDATE 意图进入
    `memory_update` 节点（"记住X"→偏好写入 + 部分响应 memory_updated）。
    召回结果记入 `turn.recalled_memory_ids`；集成测试锁定：研究轮召回偏好、
    证据沉淀为 workspace facts、追问轮不召回。

28. **测试基线：** Plan 6 完成时非真实套件 535 passed。

## Plan 7：MySQL 持久化与分布式恢复（2026-09-13 完成）

计划文档：`docs/superpowers/plans/2026-09-13-mysql-distributed-recovery.md`（本次新撰写）。

29. **自研 SQLAlchemy Checkpoint Saver。**
    `langgraph-checkpoint-mysql[asyncmy]` 未安装，选择自研
    `persistence/checkpoint.py:SqlAlchemyCheckpointSaver`（BaseCheckpointSaver）：
    复用 harness 严格序列化器；checkpoint/checkpoint_writes 两张表；
    测试经 aiosqlite 跑同一套 SQL，生产切 `mysql+asyncmy` DSN，图代码零分支。
    陷阱记录：PendingWrite 实际是 `(task_id, channel, value)` 三元组；
    metadata 必须保存自己的 serde 类型（不能假设 json）。

30. **SQL 工具执行台账。**
    `SqlAlchemyToolExecutionStore`：claim 以 (tenant, run, call_id) 唯一键竞争所有权，
    指纹冲突拒绝，FOLLOWER 轮询等待终态结果，abandon 后可回收；
    与网关的 replay 语义一致（`manager_id` 每实例生成，claim 需携带）。

31. **恢复语义的关键发现：子图 checkpoint 复用优先于台账重放。**
    强制崩溃（以 CancelledError 注入节点边界，经 LangGraph 转为 NodeCancelledError
    传播——普通 Exception 会被策略节点按"任务局部失败"吞掉，这是设计使然）后，
    `ainvoke(None)` 从持久 checkpoint 恢复：计划节点不重跑（模型调用不重复），
    已完成的 topic 子图直接复用其最终状态——提供方调用、台账写入、Evidence 入库
    全部恰好一次。三个恢复测试覆盖：计划后崩溃、工具执行后崩溃、记忆沉淀后崩溃
    （版本化 upsert 保证记忆不重复）。恢复测试中 4 项断言：
    status=completed、提供方调用各一次、gateway 调用数、记忆 facts 恰好 1 条。

32. **范围裁剪：** SQL 版记忆 Store 与 Evidence Store 适配器顺延至 Plan 8
    （内存适配器已固化生产语义，SQL 映射属机械工作）；现有 Redis broker 的
    租约/恢复扫描已有测试覆盖，不重写。

33. **测试基线：** Plan 7 完成时非真实套件 538 passed。

## Plan 8：可观测性、评测与切换（2026-09-13 完成）

34. **真实 ModelGateway 落地。**
    `harness/model_gateway.py:ChatModelGateway` 包装 `ChatOpenAI`（复用现有
    `Settings` 配置），按 role 支持 bind 覆盖；策略节点已兼容 AIMessage.content。
    从此 Harness 路径可承载真实流量。

35. **本地运行时切换（保留旧路径）。**
    `application/assembly.py:build_harness_runtime(settings)` 从 Settings 组装
    完整运行时（真实搜索/抓取/模型 + 进程内预算/台账/缓存/Evidence Store +
    HarnessEventRecorder）。`api.py:_build_runtime` 在 local 模式且配置了
    openai_api_key 时默认走 Harness 路径；无 key 或显式注入运行时时回退旧路径，
    `build_real_agent` 未删除。**注意：** context_factory 按 run_id 构建预算作用域，
    gateway 与 context 必须共享同一个 Evidence Store 实例（踩坑已记录）。

36. **结构化事件与指标。**
    `observability/events.py:HarnessEventRecorder` 作为 EventSink 收集
    tool.started/completed 等事件（仅标识与稳定错误码，无正文无异常文本），
    `metrics()` 输出工具次数/失败/缓存命中/耗时聚合。

37. **可重复的三模式对照基线。**
    `tests/integration/test_mode_evaluation.py` 在同一脚本化数据集上评测三种模式
    （脚本化模型 + 真实 LangGraph 子图 + 真实网关管道），输出质量/成本/延迟代理
    指标（termination、evidence_count、executed_steps、model_calls、tool_calls）。
    脚本化评估器按提示词特征返回 workflow 的 `sufficient` 或
    plan_execute/multi_agent 的 `action` JSON——两套评估契约并存是设计使然。
    真实 API 的对照评测脚本可在此骨架上换真实网关执行（-m real）。

38. **真实 API 冒烟测试通过。**
    `tests/real/test_real_smoke.py`（-m real，40s）：真实 Tavily 搜索 → 真实抓取 →
    真实 LLM（planner/evaluator/responder）→ 带引用的简洁回答，走完整生产装配路径。

## 交付总结（2026-09-13）

- Plan 1–8 全部交付；非真实套件 539 passed + real 冒烟 1 passed。
- 顶层运行图承载全部三种研究模式与响应模式；多轮会话、意图路由、滑动窗口、
  记忆六问生命周期、持久 checkpoint 恢复、分层预算、幂等台账、引用校验全部有
  可执行测试锁定。
- 明确未做（诚实边界）：SQL 版记忆/Evidence Store 适配器（语义已在内存适配器固化）、
  Auto Mode（等评测基线积累）、UI 更名（前端资源未动）。
- Plan 5（Multi-Agent）：待实施。
- Plan 6（会话与记忆）：待实施。
- Plan 7（MySQL 与分布式恢复）：待实施。
- Plan 8（可观测性、评测与切换）：待实施。
