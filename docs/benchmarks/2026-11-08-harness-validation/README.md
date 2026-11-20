# Harness 修改后验证（2026-11-08）

结论：统一终止契约、三策略 API、持久化恢复及前端均通过验证；真实服务链路能够完成带引用的回答，但两次真实运行表现不同，不能据此宣称回答完整性已经稳定。全量离线测试存在 4 条 SQLite 后台线程关闭警告，未消除。

## 检查结果

| 检查 | 结果 | 范围与限制 |
| --- | --- | --- |
| 后端全量离线回归 | 1674 passed，2 deselected，4 warnings | `tests -m 'not real'`，覆盖 API、应用、Harness、Gateway、策略、Checkpoint、Memory、SQL、Worker、评测、部署配置等 |
| 前端测试 | 54 passed / 12 files | Vitest |
| 前端构建 / lint | 均通过 | TypeScript、Vite、ESLint |
| 三策略 API 冒烟 | 9 / 9 场景通过 | 生产装配、真实 Gateway、预算、SQL Checkpoint、Ledger、Evidence Store、本地 Runtime 与 ASGI HTTP；模型、搜索与抓页传输使用确定性适配器 |
| 数据库迁移 | 通过 | 全量测试包含旧 Schema 升级、回退、再升级；使用临时 SQLite，未改部署数据库，未验证真实 MySQL / Redis 部署 |
| 真实模型与网页工具，第一次 | 严格成功测试失败 | 研究评估完成；答案审核列出 3 个未回答项，返回 `answer_review_incomplete`，未被当成完整成功 |
| 真实模型与网页工具，第二次 | 1 passed | 重新运行相同 Workflow 冒烟测试，通过真实搜索、抓取、模型、引用与终态检查；未修改审核门禁 |

## API 场景

Workflow、Plan-and-Execute、Multi-Agent 各验证三种情况：

1. 正常完成：`completed / completed / sufficient`。
2. 工具预算为零：`partial / budget_exhausted / insufficient`。
3. 研究覆盖已通过，回答审核仍有缺口：`partial / response_error / sufficient`，原始原因保留 `answer_review_incomplete`。

以上顺序为 `status / finish_reason / research_sufficiency`。每个场景还验证 SSE `done`、JSON 持久化和重启后的字段恢复。HTTP 使用 FastAPI TestClient，无独立浏览器或外部监听端口。结果见 [api-results.json](api-results.json)，复跑脚本为 [verify_api.py](verify_api.py)。

## 验证中补齐的缺口

真实调用暴露出已有回答终止原因未被归类的问题。新增映射：

- `answer_review_incomplete / answer_review_unavailable / generation_failed` → `response_error`。
- `response_context_limit / response_evidence_context_limit` → `context_limit`。

先增加 5 条测试，确认均因返回 unknown 失败，再补齐映射。随后全量离线回归通过。保留旧原因字符串，不改回答审核条件，也不将 partial 提升为 completed。

## 真实调用观察

第一次运行中，评估模型把 `sufficient` 放进 coverage 子对象，测试中的直接 Schema 检查记录了错误；生产的 `parse_reference_evaluation` 将此已知字段错位归一化，研究结果仍为 completed。因此该日志不是本次最终失败的根因。

最终审核列出的缺口是并发写入冲突的完整语义、存储清理策略、版本兼容细节。规划器给简单的机制解释题生成了这些更宽的检查要求，最终审核仍认为材料没有充分展开。这里说明规划范围与回答覆盖可能不稳定；尚无修改前对照，不能归因于本轮 Harness 改动。

第二次相同真实测试通过，说明真实服务链路可用；两次样本不构成稳定性或回答质量评测。

## SQLite 警告

两次全量回归均记录到 4 条 `aiosqlite` 后台线程在 event loop 关闭后尝试投递结果的警告。警告出现的测试位置不同，不能直接据此定位资源创建位置。恢复测试和回答审核测试共 12 项以 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 单独重跑均通过。

检查发现部分既有测试辅助函数创建 SQL engine 后未显式 dispose，可作为后续排查线索；尚未通过逐连接追踪确认全部警告来源。本轮没有修改这些辅助函数，也未屏蔽警告。

## 原始记录

- [最终后端 JUnit](backend-junit.xml)
- [第一次真实测试 JUnit](live-junit.xml)、[研究与回答](live-outcomes.json)、[最终审核](live-review.json)
- [第二次真实测试 JUnit](live-repeat-junit.xml)、[研究与回答](live-repeat-outcomes.json)
- [API 结果](api-results.json)

本次仅补齐原因映射和测试，保留工作区已有改动，未提交 Git，也未变更部署数据库。
