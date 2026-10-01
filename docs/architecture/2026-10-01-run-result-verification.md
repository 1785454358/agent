# 统一运行结果：实施与验收

日期：2026-10-01。

## 已实施

应用服务返回 ApplicationRunResult，包含权威 Harness 终态、原始研究/回答结果、停止原因、研究执行步数、未解决问题和引用来源。fresh、continuation、resume 使用同一提取边界。

Local 和 Worker 直接映射结果，不再通过 response.partial_reason 猜测整体成功，不再重复查询来源。研究受限但回答可用时仍保留 partial；Worker.steps 不再固定为 1；CLI 改为“执行步数”。

来源读取保持 workspace 隔离和引用顺序；只读 metadata，有引用查询一次，无引用不查询。研究未完成的原因优先于回答原因；研究 completed 后的回答失败仍保留整体 partial。复制 gaps，避免应用摘要与原研究列表相互污染。

异常、取消、身份校验、checkpoint 恢复和已有控制响应语义不变。未增加 schema、运行服务或依赖；用户原有配置、引用和评测修改未覆盖。

## 离线验证

- TDD 首先观察状态丢失回归失败，再实现返回契约；随后观察 Local/Worker 旧适配失败，再迁移两端。
- 应用/Local 专项最初 34 passed；应用/Local/Harness/集成专项 60 passed。
- 全仓首次发现 API 夹具仍返回旧 ResponseOutcome，显式迁移夹具后通过；没有把 failed 的预期改成“通过”。
- 最终 `.venv/Scripts/python.exe -m pytest -q -m "not real" --tb=short`：**562 passed, 2 deselected，49.49 秒**。其中包括工作区现有未提交评测代码，仅验证其兼容性，不将这些文件纳入本次提交。
- 修改的生产文件 Ruff 全规则、测试 I/F、14 个文件格式检查通过；git diff --check 通过。
- 审查了状态权威、原因优先级、来源租户边界、单次元数据查询、恢复不重复研究和适配器生命周期；原有 broad exception 保留在观察者隔离/公开运行失败边界，注明理由，不扩展吞异常行为。

## 真实 API：已执行，端到端未通过

执行命令：`.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -s -m real --tb=short --show-capture=no`。

单题：“LangGraph 的 checkpoint 机制是什么？”；独立 run/thread、临时 SQLite、lexical 记忆、每分支最多 3 轮、输出最多 1024 token、180 秒超时、最多 12 次逻辑模型/工具调用。没有使用生产 MySQL/Redis、历史运行数据或向量目录。finally 已关闭资源。

**结果：1 failed，26.70 秒；partial / no_sources，11 个研究执行步骤，0 个引用来源。**

失败发生在带引用答案断言；此前 ApplicationRunResult 与真实 Harness snapshot 的 status、研究/回答结果、身份、steps、gaps、reason 一致性断言均通过。不能将这次结果表述为“真实端到端已通过”。

对已保存 checkpoint 的只读调查发现：规划器分出 3 个研究分支，各分支 iteration=3、errors=[]，工具消息依次为 write_todos、search_web、write_todos；搜索返回 ok=true，但尚未调用 fetch_page。最终保留 agent_exit:iteration_limit 与 no_evidence_collected。诊断支持“测试轮次预算在抓取之前耗尽”，不支持“模型/Tavily 服务不可用”或“引用来源读取故障”。

没有为了获得通过结果提高限额、重跑真实流程或跑全题集。下一轮建议审阅预算与轨迹效率：规划辅助动作占用有限迭代，最低可执行路径需要先校准；扩大每分支上限也必须保留全局模型/工具上限。

逻辑调用数不等于网络重试数；本次失败前打印摘要尚在末尾，因此不能事后声称已得到完整计费统计。测试已将摘要打印移动到引用断言之前，方便后续失败诊断，此诊断改动尚未再次调用真实 API。执行步数不解释为 LLM 次数，Token 和费用仍未知。

## 新增 Agent 评测范围

设计提案见 `docs/superpowers/specs/2026-10-01-agent-evaluation-design.md`。推荐 Ragas 单主框架、pytest 工程回归、冻结题集、简单基线和记忆对照。尚未安装/接入 Ragas，也尚未执行框架真实 judge 或更大规模的 Agent 质量评测；待用户确认书面选型后实施。
