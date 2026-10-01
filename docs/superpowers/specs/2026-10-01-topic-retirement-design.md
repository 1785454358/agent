# Harness 简化：研究执行入口统一

日期：2026-10-01。状态：用户已回复“开始”，确认迁移方案和删除清单；实施中。

## 目标与范围

让生产和主要回归测试共用 `harness.agent_executor.build_research_agent_graph`，退出第二套固定搜索、选 URL、抓取、结束的 Topic 执行图。保留三个研究策略；策略负责任务安排，共享 Agent Loop 负责模型与工具执行。

本次不改记忆生命周期、数据库、Provider 协议、依赖版本或前端。不将旧执行图复制到测试目录，也不新增执行框架。

## 已核实的现状

- `application/assembly.py` 已将同一个共享 Agent Executor 接入 Workflow、Plan-and-Execute、Multi-Agent，正式装配不使用旧 Topic 图。
- `strategies/topic` 的四个生产文件仍实现另一套执行流程；`strategies/__init__.py` 仍导出旧构图函数。
- 三个策略的图测试、Harness 响应切片和三个集成测试文件仍依赖旧图，恢复测试也在其中。仓库内查找未发现其他运行时消费者，但这不能证明没有仓库外消费者。
- 旧测试模型只支持 planner、supervisor、evaluator、responder 等角色，有些明确禁止调用模型。共享 Agent Loop 要通过 researcher 角色发送带工具定义的消息，不能只替换构图函数名。
- 旧 Topic 测试包含仍有价值的契约、权限、页数上限、失败处理和状态持久化测试，也包含只属于旧拓扑的节点、reducer、固定选择顺序断言。

## 方案比较

1. **推荐：迁移消费者，移除旧图与公开入口。** 真正少维护一套实现，主要测试覆盖正式执行路径。代价是旧 Python 导入入口不再兼容，需要明确迁移说明。
2. **保留旧图，只标记 deprecated。** 可缓冲外部调用者迁移，但继续保留两套执行语义，不能完成当前简化目标。
3. **旧函数转发到新图。** 可保留函数名称，但新图增加研究模型调用且改变状态拓扑，不是行为兼容。还会留下容易误解的入口，因此不采用。

## 推荐设计

### 执行与测试边界

主要策略图、Harness 切片和集成测试均构建真实共享 Agent Loop。模型和搜索、抓取服务使用确定性脚本替身；ToolGateway、证据存储和检查点保持真实组件，不用固定结果替身掩盖执行链路。

测试 fixture 只描述模型响应：根据当前分支的消息历史，返回 search、fetch 或结束的 AIMessage。不通过全局可变游标分配并发分支响应，不复制旧图中的 URL 安全、预算、证据写入或重试逻辑；这些行为仍由正式组件负责。

用于故障、未完成计划等情景的已有包装器可以保留，但包装共享 Executor。纯契约测试可以直接构造 Outcome，不为此构建另一套测试研究图。

### 公开入口与检查点

移除 `deeptrace.strategies.build_research_topic_graph` 以及 `deeptrace.strategies.topic` 的旧图、节点和状态导出；新调用者直接导入 `deeptrace.harness.agent_executor.build_research_agent_graph`。这是明确的 Python 接口变更，不宣称向后兼容。

保留 `ResearchTopicInput`、`ResearchTopicOutcome`、`TopicStepError` 等领域契约，它们仍被共享 Executor 和策略使用。保留其他策略自身的同名 reducer，不按名称批量删除。

正式 Agent Loop 的节点名、状态和 Checkpoint 边界不修改。旧 Topic 图的历史快照不承诺在新图中恢复，也不实现自动状态转换；若存在外部持久化的旧图任务，应先用旧版本完成或另建新任务。此次退出不删除检查点数据或执行账本。

### 测试覆盖迁移

| 旧覆盖 | 迁移后的验收 |
| --- | --- |
| 输入边界、唯一引用、错误契约、严格序列化 | 迁到领域研究契约测试，保留原行为验证 |
| 搜索后抓取、多个页面、有效证据汇总 | 真实 Agent Loop + 脚本工具调用；不要求旧 select_urls 拓扑 |
| workspace、caller、mode、URL 授权 | 在共享 Executor 路径核对 Gateway 收到的上下文与授权，非法 URL 不进入外部抓取 |
| 幂等工具身份 | 对同一运行与已持久化的工具调用检查稳定身份及重放；不要求不同运行身份相同 |
| 空搜索、异常预览、部分抓取失败、fatal 错误 | 检查正式实现的受控错误与停止语义、保留有效证据、无无界重试；不机械保留旧图独有错误码 |
| max_pages | 模型请求超额抓取时，由执行边界阻止额外外部请求，不能仅让脚本少请求几页 |
| 检查点不保存证据正文 | 在共享 Executor 的 snapshot 检查唯一正文标记未持久化，证据仍可通过引用读取 |
| 进程中断后恢复 | 保留持久化 saver 与账本测试，验证已完成搜索、抓取和证据写入不重复 |
| 多模式评估成本 | 将 researcher 调用计入脚本模型调用成本；保留确定性比较，不将代理指标描述为真实质量或延迟 |
| 旧 reducer、旧 schema 注解与旧节点顺序 | 随旧实现退出，不为维持测试数量保留无用途类型 |

如果迁移暴露正式执行路径的行为缺口，先记录具体失败并区分旧拓扑语义与真实安全不变量。不为让旧断言通过而恢复第二套执行流程；涉及独立生产行为修复时另行明确范围。

## 文件边界

完成迁移并验证后删除：

- `backend/src/deeptrace/strategies/topic/__init__.py`
- `backend/src/deeptrace/strategies/topic/graph.py`
- `backend/src/deeptrace/strategies/topic/nodes.py`
- `backend/src/deeptrace/strategies/topic/state.py`

修改旧导出：`backend/src/deeptrace/strategies/__init__.py`。

测试消费者：

- `backend/tests/strategies/fixtures.py`
- `backend/tests/strategies/{workflow,plan_execute,multi_agent}/test_graph.py`
- `backend/tests/harness/test_workflow_response_slice.py`
- `backend/tests/integration/test_workflow_response_exit_gate.py`
- `backend/tests/integration/test_recovery.py`
- `backend/tests/integration/test_mode_evaluation.py`

将 `backend/tests/strategies/topic/test_state.py` 中有效契约迁至 `backend/tests/domain/test_research.py`；将 `test_graph.py` 中有效行为迁至现有 `backend/tests/harness/test_agent_executor.py` / `test_agent_invariants.py` 的相应边界，然后退出旧测试文件及其空包初始化文件。

更新 `docs/architecture/agent-harness.md`，说明唯一执行入口和旧 Python 入口迁移方式。历史设计文件作为历史记录保留，不将“当时保留旧图”的决策伪改成已经删除。

## 验证与交付

1. 先建立并运行生产路径行为测试，再迁移消费者，最后删除无消费者的旧实现。
2. 运行领域、Harness、策略、响应、恢复与多模式集成测试；再运行全仓库 `pytest -m "not real"`。
3. 检查 Ruff、格式和 `git diff --check`；检查运行时代码和测试无旧导入。
4. 用覆盖迁移清单解释测试增减，不以数量相等代替行为覆盖。
5. 只暂存本次明确文件，保留用户已有引用、评测、配置与文档修改。

## 审阅

- [x] 核对正式装配、旧入口与所有仓库内测试消费者。
- [x] 比较删除、保留 deprecated、函数转发三种方案。
- [x] 明确公开接口变更、历史快照限制与行为覆盖迁移。
- [x] 自审范围、术语与验收要求，不引入第二套测试执行器。
- [x] 用户确认设计及上述删除清单。
- [x] 确认后使用 writing-plans 制定实施计划，再开始实现与验证。
