# 问题记录

## 2026-09-02 任务级 Token 预算导致研究提前停止

- **问题**：研究任务按动态分配的 API Token 配额停止，并且研究阶段只使用总运行时的 70%，导致后续研究任务没有执行，最终报告内容不完整。
- **解决**：移除任务级和全局 API Token 预算、Token 预留分配以及研究阶段运行时预留停止逻辑。保留步骤数、抓取页面数、费用上限和总运行时上限作为安全边界，同时继续累计并展示各阶段 Provider Token 用量。

## 2026-09-03 阶段 4 移除后文档矛盾与代码旧命名残留

- **问题**：阶段 4（Evidence/Claim/Verifier）移除的清理不彻底：docs/README 第 6 行说已移除、后文又说已落地且指向废弃的 stage-04 spec/plan；路线图、总体目标架构与 backend/README 仍描述 Evidence/Verifier 和不存在的 `DEEPTRACE_ENABLE_CLAIMS` 模式；代码里 nodes.py 仍输出"开始证据核验"并返回残留键 `used_claim_ids`，service.py 初始化函数仍叫 `_initial_stage_four_state`，cli.py 引用了被删除的 `_format_stage_four_summary` 和未定义的 `mode`（运行到打印报告必然 NameError），tests/agent/test_service.py 末尾测试被截断。
- **解决**：
  - 代码：`_initial_stage_four_state` → `_initial_research_state`（含测试同步并补全被截断断言）；nodes.py 事件文案改为"正在生成章节结果"并删除 `used_claim_ids` 残留键；cli.py 删除 `mode`/`_format_stage_four_summary` 两处残留恢复可运行。
  - 文档：backend/README.md 按现状重写（删除 Evidence/Verifier/`DEEPTRACE_ENABLE_CLAIMS`，目录与流程对齐真实代码，补 memory.py/api.py 与阶段 5）；docs/README 删除自相矛盾段落并把 stage-04 文档标为废弃历史；roadmap 与总体目标架构更新为"阶段 4 已移除、阶段 5 已完成、阶段 6 未开始"；两份 stage-04 spec/plan 加废弃状态标注。
  - 验证：`uv run pytest -m "not real"` 86 项通过，`compileall` 通过。

## 2026-09-04 真实 API 回归在 Writer 阶段无限等待

- **问题**：首次真实回归任务 `7e9b406a28f6`（问题为“2024 年 AI Agent 领域有哪些热点新闻？”）在研究任务全部结束后仍长期保持 `running`。15 分钟后手动取消，持久化状态为 `cancelled`。排查确认 `WriterAgent` 的异步模型调用没有超时，图级总运行时间只能在节点之间检查，无法中断已经发出的 Provider 请求。
- **解决**：为 Writer 的两次生成尝试增加共享的 120 秒绝对期限，并用异步超时包裹每次 Provider 调用；超时后沿用现有确定性降级报告。补充测试验证挂起模型不会阻塞任务。修复提交为 `426ef93`。同时把 Agent 的 `termination_reason` 写入 API 响应和本地运行记录，修复提交为 `399f7db`。
- **复测**：任务 `81868bfae030` 使用同一问题，在 2026-09-04 15:51:35 至 15:57:39（Asia/Shanghai）完成，终态为 `completed`，终止原因为 `completed`。任务得到 5 个来源和 1290 字报告；Writer Provider 超时后成功使用确定性降级报告。Provider Token 共 4144，其中 Planner 1592、Researcher 2552、Compression 0、Writer 0。SSE 返回完整事件序列和 `done` 事件，`runs/81868bfae030.json` 已存在且状态、终止原因与 API 一致。
