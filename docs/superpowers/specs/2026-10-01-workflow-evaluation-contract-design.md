# Workflow 评估器输出契约修复

日期：2026-10-01。状态：提案待确认，不含已实施声明。

## 已确认原因

真实测试增加到 12 轮后，三个研究分支均 completed、任务清单全部完成、搜索和抓取成功。但评估器输出在 finish_reason=stop 时仍出现 WorkflowEvaluation 的 string_type 校验错误，整体因此 partial/evaluation_unavailable。不是本轮迭代预算不足，也没有输出截断的证据。此前仅记录错误类型，尚不能断言具体是哪个字段；下一次诊断已支持 loc/input_type。

## 方案

推荐保留严格 Pydantic 契约，明确有效 JSON 示例和字段类型，格式错误时最多进行一次带校验错误的有限纠正。

备选是只改 prompt：代码更少，但仍可能偶发结构不合法；不采用宽松转换任意字段或把校验失败视为 completed，这会掩盖真实失败。

## 最小范围

仅修改 `backend/src/deeptrace/strategies/workflow/nodes.py` 的 evaluate_node 和相关测试。不引入框架、全局解析兼容层、新状态机或 Provider 专用依赖，不改用户现有评测模块。

1. prompt 明确字段类型和有效示例，例如 findings 的 id 为字符串 `finding-1`、claim 为字符串、evidence_ids 为现有资料 ID 的字符串数组、confidence 为 0–1 数值；unresolved_gaps 为字符串数组；sufficient 为布尔值。
2. 首次返回仍严格 `WorkflowEvaluation.model_validate_json(payload_text(response))`。验证失败时保留错误路径/类型，原始输出作为不可信数据，不允许覆盖系统指令。
3. 最多一次纠正模型调用，使用同一任务/约束/证据 ID、完整 schema 和有限长度原始响应；不重新规划、搜索或抓取。每次调用仍走 ModelGateway，受真实测试总调用上限约束，不新增无界 retry。
4. 纠正后仍严格校验并继续现有来源过滤；仍失败则保留 evaluation_unavailable/partial，不静默造 findings 或 sufficient=true。
5. 只修格式，不降低“研究完成”标准，不用重试去强迫语义判定 sufficient=true。格式正确但证据不充分的响应不会再调用模型“劝它通过”。

## 验证

先写 failing regression：首次错误字段类型，第二次合法结果时得到真实有效 evaluation；第二次仍错只调用两次并保持 partial；格式正确而 sufficient=false 不重试。外部模型用脚本边界，EvidenceStore 等使用真实组件。记录模型调用数与研究阶段步骤的区别，不把一次额外 LLM 调用自动等同于新的研究步骤。

离线回归、Ruff、格式与 diff 检查完成后，再在 12 轮 / 2048 输出 / 40 模型 / 24 工具 / 240 秒上限内执行一次真实单题，要求 search/fetch/cited answer、completed 和 checkpoint 一致性全部通过；不能仅凭来源存在宣布通过。

这是一项新的生产行为修复，需要用户确认后进入 writing-plans 与 TDD，未在预算调优过程中直接实施。
