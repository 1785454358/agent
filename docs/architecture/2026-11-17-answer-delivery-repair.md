# 回答交付修复

目标：取证不完整时仍交付有依据的解释，避免将已有原文误判为无资料；不通过伪造 completed 掩盖未解决的问题。

根因证据：2026-11-16 的 insufficient_evidence-test-01 已有 eligible 原文，但 findings 为空。response load 与材料装配均按 accepted findings 再过滤来源，最终跳过模型并输出 31 字通用兜底。

方案：来源准入与结论准入分别执行。ACTIVE、eligible 的授权原文可供写作和末端复核；只有 accepted findings 可作为已核验结论。没有 accepted findings 时仍按问题选择原文，即使运行剩余预算要求关闭额外扩展，也保留基本原文窗口。研究未完成状态不变，回答说明可见证据范围与缺失条件。

实施顺序（本会话执行，沿用现有架构）：

- [x] 先增加空 accepted 集合、部分 accepted 集合的回答链路回归；确认旧实现失败。
- [x] 修复 responses/graph.py 和 responses/evidence.py，保留来源隔离、状态校验、引用校验与预算限制；运行 responses / research / integration 回归。
- [x] 实际运行北京旅行、技术解释和材料不支持结论的问题，保存原始答案、状态和用量；记录仍存问题。

真实运行额外暴露预算正则跨越普通文字的问题，已用原始句子先复现再修复。另补充末端审查格式失败时的原文摘录退化，保持 partial，不发布坏草稿。最终非联网回归：1685 passed、1 deselected。

本次验证记录：`docs/benchmarks/2026-11-17-answer-delivery/README.md`。

边界：不因 schema 错误发布明显未经审查的泛化断言，不把未核实报价当真实价格，不改变持久化数据中的历史结果。
