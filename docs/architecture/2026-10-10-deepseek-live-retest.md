# DeepSeek 真实 API 重测

日期：2026-10-10。接续 [Harness 运行时优化与离线验收](2026-10-10-harness-runtime-implementation.md)，保留失败样本。

## 配置和测量范围

本地 `backend/.env` 的 `OPENAI_MODEL` 已切换为 `deepseek-v4.1-flash`，使用现有火山方舟 API 与 Tavily 凭据。实际响应报告的模型是 `deepseek-v4-1-flash-260910`。没有导出凭据。

完整研究运行使用生产 `build_harness_runtime`、LocalResearchRuntime、真实模型、Tavily 和网页抓取。每个样本采用独立 SQLite 运行库与 Chroma 目录；保留 BGE-M3 语义记忆、事实审查、现有来源规则与预算。没有连接真实 MySQL/Redis，也没有修改已有运行数据库。

| 配置 | 本次值 |
| --- | --- |
| 思考 | `auto`，该模型保留供应商默认；实际返回含 reasoning Token |
| 输出上限 | 16,000 Token |
| 全局模型次数／输入额度 | 20 次／100,000 Token |
| 研究期限／收尾期限 | 600 秒／额外 120 秒 |
| 最终事实审查 | 开启 |
| 研究来源目标 | 3 |
| Benchmark DNS proxy 配置 | 既有 `allow_benchmark_dns_proxy=true`；不能泛化到其他部署网络 |

每条 wall time 从 Local 创建任务开始，到 done 事件为止，含研究、回答和同步记忆整理；组装耗时另外记录。Token 来自供应商 usage，reasoning 已包含在 output/total。角色模型时间不是端到端耗时。测试调用没有修改 `MODEL_THINKING` 默认值。

## 端到端结果

三种策略使用同一问题：**仅依据 Python 3.11 官方文档，比较 TaskGroup 与默认 gather 在子任务普通异常、取消及清理时的行为，并说明吞掉 CancelledError 的影响。用中文回答。**

另用 Plan-and-Execute 测试“2026年量子力学领域进展”，以及独立文档任务的真实模型工具循环。

| 样本 | 运行状态 | wall 秒 | 组装秒 | 模型调用 | 合格引用来源 | 总 Token |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Python / Workflow | partial / insufficient_evidence | 162.068 | 3.198 | 5 | 0 | 34,363 |
| Python / Plan-and-Execute | partial / insufficient_evidence | 262.743 | 0.356 | 11 | 0 | 78,497 |
| Python / Multi-Agent | partial / max_follow_ups_reached | 499.198 | 0.259 | 13 | 1 | 128,679 |
| 量子研究 / Plan-and-Execute | completed，规划降级，覆盖不足 | 241.335 | 0.370 | 5 | 2 | 未知；已观察 40,324 |
| 独立文档循环 | completed | 3.899 | — | 2 | 本地文件 1 个 | 1,139 |

前三条均未通过完整答案覆盖要求。Workflow 没有合格的指定版本原文；Plan-and-Execute 还出现核验 schema 失败；Multi-Agent 提供了 TaskGroup 和取消的部分回答，保留缺少 gather 原文的明确说明与结构化缺口。不能把多 Agent 的单次耗时差异解释成普遍性能排序。

量子题首次 planner 请求在约 60.5 秒后超时，随后使用 `decomposition_degraded=true` 的单个兜底需求。4 次返回有 usage、1 次没有，所以 input/output/total 均为 null，observed_usage 保留 40,324。回答列出一个代表性成果及背景，并明确说明无法完整覆盖全领域年度进展；运行状态却是 completed、结构化 unresolved_gaps 为空。它只能证明兜底链路完成，**不算年度综述质量通过**。详见下面的状态语义问题。

独立文档任务使用真实模型产生 `read_local_document` 调用，真实 Gateway 完成一次只读文件读取，ToolMessage 返回后模型结束。两次调用 input=781、output=358、total=1139；文件内容为两句固定测试事实，回答复述了内容且说明文件陈述仍需证据核对。该样本验证共享循环、非研究 State/Context、自定义工具与模型计量；不是 Coding Agent 的文件修改／命令沙箱或故障恢复实验。示例仍使用内存账本。

## 现有真实测试

命令（backend 目录）：

```powershell
uv run --no-sync pytest -m real tests/real/test_real_smoke.py tests/real/test_eval_quality.py -q -s --tb=short
```

结果：**1 passed、1 failed，173.07 秒**。没有把 completed 断言改成允许 partial。

- `test_real_eval_produces_bounded_judge_scores` 通过：离线语料配真实模型和裁判，验证评分契约落在 1–5；不代表答案质量优秀或联网取材通过。
- `test_real_workflow_run_returns_cited_answer` 失败：问题为“LangGraph 的 checkpoint 机制是什么？”，结果 partial/insufficient_evidence。6 次模型调用、8 次工具调用、3 个来源；核验原文没有足够 checkpoint/checkpointer 说明。回答草稿修复后，事实审查仍收到空内容。

这条旧冒烟测试主动覆盖配置：词法记忆、输出上限 2048、planner/writer 超时 45 秒、外层 240 秒。它与下面按实际配置运行的矩阵不同，不能合并成同配置通过率。

## 已定位的问题

### 输出上限与思考配置

冻结第一条完整研究的 planner 消息，通过当前模型 Gateway 做两次诊断：

| 请求 | 耗时 | finish_reason | 输出／思考 Token | 可见输出 |
| --- | --- | --- | --- | --- |
| auto，max_tokens=2048 | 14.194 秒 | length | 2048／2048 | 空 |
| disabled，max_tokens=16000 | 8.339 秒 | stop | 1403／0 | 有结构化规划 |

完整 Workflow 原规划为 auto/16000：51.279 秒，输出 9287，其中思考 7550。可复现低输出额度被 reasoning 耗尽；API 成功返回不等于输出可解析。三个请求各执行一次，缓存、参数和随机输出有差异，不据此宣称总体提速比例，也没有端到端关闭思考的成对实验。

### 来源限制在搜索层未兑现

直接调用同一 Tavily 服务的三条诊断查询保留原始结果：

- 路径 `site:docs.python.org/3.11 ...` 返回博客、gRPC、Adobe 社区等站点，只有一个 Python changelog 候选。
- 域名 `site:docs.python.org ...` 能返回官方站点，但混入多种语言和版本。
- 显式 `include_domains=["docs.python.org"]` 返回的五条结果均来自该域名，仍混有 3.11、3.12 与最新版。

因此仅在搜索词里写站点和版本不构成保证。后续应将用户来源约束结构化，向服务传递域名过滤，并校验实际抓取 URL、版本和原文；定向 URL 也须经过现有安全策略。不能通过放松核验把不合格材料改成合格。

### 核验响应协议

Plan-and-Execute 的三次核验响应有 `coverage.unresolved_gaps`，而当前 schema 只允许顶层 `unresolved_gaps`；重建 Pydantic 校验均报 `extra_forbidden`。一次格式修复仍未修正此字段位置，终态保留 evaluation_unavailable。供应商的 stop 标记只能说明生成结束。

后续优先补明确字段层级示例与固定失败响应回归，评估供应商支持的结构化输出。维持有界修复，不无限重试，也不静默放宽领域 schema。

### 输出成本与阶段观测

Multi-Agent 样本总用量 128,679 Token，其中输入 65,791、输出 62,888；全局 100,000 预算只约束输入，不能宣称整个运行的总 Token 被限制在该值内。后续要根据真实输出成本决定是否补输出／金额额度和角色思考策略，而不是只增加输入预算。

同步语义记忆整理／索引也计入 wall time。此次保存的 `memory.index.completed` 和 `memory.consolidation.completed` 事件存在，但公开 details 为空：当前事件字段过滤没有保留它们的阶段计时信息。因此本报告不能精确列出该样本的索引耗时；不把 wall time 减去角色时间当作索引时间。后续应补齐安全的阶段计时字段，再决定是否异步化。

### 规划降级后的完成状态

量子题的兜底需求为“完整回答原始问题及全部用户约束”，核验却将一个代表性成果判为 covered；回答自行声明全领域覆盖不足，但结构化缺口为空、状态 completed。这里存在覆盖／完成语义不一致，事实审查也未改变状态。

后续优先让规划降级标记参与最终覆盖判断，保留可见范围缺口；检查回答声明范围与结构化终态的一致性。不能简单把任何降级都判失败，也不能把“已有一个有引用的事实”泛化成完整研究完成。这比继续增加 Agent 角色更直接影响交付可信度。

## 运行时交叉核对

四条生产研究样本全部通过 8 项只读核对：真实响应次数、已观察 Token、缺失 usage、运行保存值与 SQL 快照一致；重建连接和网关后保留原始开始时间与限制，没有因新网关配置扩大额度；已派发失败请求仍计入次数，输入消耗至少等于已观察输入。

| 样本 | SQL revision | 保存／恢复调用 | charged input | observed input | 缺失 usage 次数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python / Workflow | 10 | 5 | 19,283 | 19,283 | 0 |
| Python / Plan-and-Execute | 22 | 11 | 55,531 | 55,531 | 0 |
| Python / Multi-Agent | 26 | 13 | 65,791 | 65,791 | 0 |
| 量子研究 | 10 | 5 | 19,304 | 15,686 | 1 |

量子题未知请求保留了 3618 输入 Token 的估算消耗，没有退款；它不是远端实际计费数。重建时故意给新网关更大次数／输入／时间限制，恢复后仍采用保存的 20 次、100,000 输入和 600 秒原期限。

恢复核对只读取已完成真实运行的 SQL 快照，以新 SQLAlchemy engine 和新 RunBudgetModelGateway 恢复，没有再请求模型，也不是进程中断续跑、并发 Worker 接管或故障注入实验。

## 面试口径和证据

可以讲：“接入新模型后用真实研究和独立工具循环重测，保留 partial 与契约失败，通过角色 usage、工具轨迹和 SQL 快照区分生成、取材与恢复问题；低输出额度会被思考耗尽，site 查询也不能替代确定性来源限制。”

后续顺序建议：完成／覆盖语义一致性 → 确定性来源和版本约束 → 新模型输出契约与思考策略 → 计时字段与输出成本边界。先增加针对本次真实失败的回归与可复现对照，再评估性能优化。

当前样本数量少，不能写成模型准确率、P95、SLA 或相对旧模型提速成绩。旧 Doubao 样本继续保留原版本语义。本次没有更改生产研究算法或降低验收标准。

本地原始产物（目录由现有 Git 忽略）：

- [测试脚本](../../.local-notes/retest-harness-live.py)、[配置](../../.local-notes/harness-live-2026-10-10/configuration.json)、[模型探测](../../.local-notes/harness-live-2026-10-10/probe.json)
- [结果总表](../../.local-notes/harness-live-2026-10-10/summary.json)，各样本目录含 run.json、answer.md、模型消息／响应、研究终态与引用正文
- [现有真实 pytest 摘要](../../.local-notes/harness-live-2026-10-10/real-pytest-summary.json)、[独立文档工具／模型事件](../../.local-notes/harness-live-2026-10-10/document-live/events.json)
- [输出额度诊断](../../.local-notes/harness-live-2026-10-10/output-budget-diagnostic.json)、[检索诊断](../../.local-notes/harness-live-2026-10-10/search-diagnostic.json)、[恢复及响应契约核对](../../.local-notes/harness-live-2026-10-10/audit.json)
- [最终核对记录](../../.local-notes/harness-live-2026-10-10/verification.json)：矩阵 36 次准入、35 次有 usage、已观察 283,002 Token；不含探测、诊断和 pytest，不能当作全部 API 成本。

面试事实页见[实现与实测核对](../resume/04_事实与来源/02_实现与实测核对.md)。公开报告提供脱敏结论，原始消息和运行库保持本地。
