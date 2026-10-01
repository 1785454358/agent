# Harness 与记忆模块收敛实施计划

**Goal:** 在现有接口上简化 Harness 依赖，完成长期记忆的写入、版本、召回与降级闭环。

**Architecture:** LangGraph 继续管理状态与恢复，Shared Loop 统一 Agent 执行。记忆采用线程 State + 用户偏好/研究事实 collection + SQL 权威记录/Chroma 检索索引。

**Tech Stack:** Python 3.11、LangGraph、Pydantic、SQLAlchemy、SQLite、pytest。

**Spec:** `docs/superpowers/specs/2026-10-01-harness-standardization-design.md`

## Global Constraints

- 不新增依赖、通用插件框架、独立 Memory Agent 或后台队列。
- 保留三种策略、公开图入口与 Outcome JSON 字段。
- 保留原有节点名和工具后的 Checkpoint 边界。
- 用户原有评测、引用、配置和索引文档改动不进入本次提交。
- 每个行为改动先写回归测试，确认失败，再修改实现；纯函数搬迁用既有测试保护。

## Task 1：收敛 Shared Loop 与公共策略边界

Files：`harness/agent_executor.py`、`agent_state.py`、`policies/execution.py`、`domain/agent.py`、新增 `harness/model_io.py`、新增 `strategies/common.py`、三个策略 `nodes.py`、`harness/graph.py`、`strategies/model_io.py`。

- [x] 在 Agent 测试中断于 prepare_context，恢复后确认 Provider 从原始任务重建模型视图；Checkpoint 不保存重复视图。
- [x] 在 Workflow 测试使用真实 AIMessage 返回规划 JSON，确认选择模型给出的查询而非错误回退。
- [x] 运行新增测试观察失败。
- [x] 将 payload_text / parse_json_object 搬到 harness/model_io；旧调用入口通过直接导入兼容。
- [x] 公共策略函数迁移到 common；集中调用验证/取消传播及外层完成状态降级。
- [x] Policy 输出 AgentOutcome，Executor 包装 ResearchTopicOutcome；添加共享 Literal 类型别名与核心接口类型。
- [x] 运行 harness / strategies 既有测试。

## Task 2：记忆版本事务与写入治理

Files：`memory/write.py`、`store.py`、`forget.py`、`persistence/memory_store.py`、`harness/context.py`、`domain/memory.py`、memory tests、SQLite persistence tests。

- [x] 测试未带证据的 FACT 经 remember 被拒绝；已失效同内容记录被显式写入时生成新版本。
- [x] 测试多个并发更新留下单一 ACTIVE 版本和完整 supersedes 链。
- [x] 测试逻辑遗忘排除所有旧版本。
- [x] Store.upsert 用锁/事务统一版本写入；在 SQL 主键冲突时有限重试。
- [x] remember 强制 source 策略；明确 facts TTL 与偏好稳定身份；用内存和 SQLite 验证。

## Task 3：召回、注入与整理闭环

Files：`memory/recall.py`、`retriever.py`、`lifecycle.py`、`harness/context.py`、`prompts.py`、memory tests。

- [x] 测试向量命中后失效/越 namespace 的记录被丢弃，过期/STALE 不参与注入。
- [x] 测试中文事实可被 fallback 匹配，无关事实不填充额度，通用偏好可跨问题使用。
- [x] 测试自动整理存储失败仍返回研究结果；伪造 Evidence ID 不进入长期记忆。
- [x] 测试同一 finding ID 的不同事实保留不同身份，同内容重复整理不增加版本。
- [x] 召回加条数/token 限制与来源元数据；显式偏好直接读取，事实才做语义检索。
- [x] 将记忆失败降级与事件集中处理，显式写入回应成功/失败，自动整理保留研究结果。
- [x] 运行 memory / graph / application 测试。

## Task 4：整体验证与交付

- [x] 更新 `docs/architecture/agent-harness.md` 并新增 `docs/architecture/memory.md`，说明真实实现与参考取舍。
- [x] 运行相关目录：`.\.venv\Scripts\python.exe -m pytest tests/harness tests/strategies tests/tools tests/persistence -m "not real" -q`。
- [x] 运行全仓库：`.\.venv\Scripts\python.exe -m pytest -m "not real" -q`。
- [x] 使用 code-review-and-quality 审查边界、并发与恢复语义，执行 `git diff --check`。
- [x] 只暂存本次明确路径，检查 staged diff 后提交；交付测试结果、记忆架构文档及尚未覆盖的真实服务边界。

## 验收记录

- Harness / Strategies / Tools / Persistence：`308 passed`。
- 全仓库 `not real`：`507 passed, 2 deselected`（18.87 秒）。
- 本次改动的 22 个源文件：Ruff check 通过；源文件及相关测试的格式检查通过。
- `git diff --check` 与各实现提交的 staged diff 检查通过。
- Harness 重构：`7801a21`；记忆闭环：`7338b97`。文档随独立提交交付。
- 自审中补正 SQL 最新失效版本屏蔽旧 ACTIVE 版本，以及完整记忆身份匹配；失败回归确认后实现，内存 / SQLite 交叉测试通过。
- 未引入新依赖、SDK、服务或后台队列；原有评测、引用、配置与文档索引修改未纳入上述提交。
- 真实 Provider / Chroma / MySQL 多进程环境未在本次验收运行。大规模版本扫描、任意语义冲突合并、认证后的租户隔离与敏感内容治理不作已完成承诺，边界已写入架构文档。
