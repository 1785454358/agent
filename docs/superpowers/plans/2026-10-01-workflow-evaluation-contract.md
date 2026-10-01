# Workflow Evaluation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Workflow 评估 JSON 契约，保持严格校验和完成标准，并验证一次真实端到端研究。

**Architecture:** evaluate_node 提供完整 schema 和有效示例，仅在 JSON/schema 校验失败后通过现有 ModelGateway 纠正一次。纠正数据有界、不可信，第二次失败维持 partial；不改变研究工具、状态结构、来源过滤或生产预算。

**Tech Stack:** Python / Pydantic / LangGraph / pytest / Ruff。

**Spec:** [approved design](../specs/2026-10-01-workflow-evaluation-contract-design.md)

所要求的两个执行子技能当前不可用，因此在当前线程逐项执行；用户已确认实施，不重复审批。

## Task 1: 契约与有限纠正

- [x] 在 `backend/tests/strategies/workflow/test_nodes.py` 使用真实 EvidenceStore 和脚本模型补测试：错误字段/非法 JSON 后恢复、两次失败降级、有效 false 不重试、纠正仍过滤来源、无来源不调用、错误数据有界、传输/取消错误不重试。
- [x] 从 backend 执行 `.venv/Scripts/python.exe -m pytest tests/strategies/workflow/test_nodes.py -q`，确认新行为用例 RED（6 failed / 10 passed）。
- [x] 仅修改 `backend/src/deeptrace/strategies/workflow/nodes.py` 的评估路径：完整 schema、合法 JSON 示例、最多两次调用、错误仅 type/loc、有限原始输出。
- [x] 执行节点/图/响应集成回归（46 passed）；Ruff、格式和 diff 检查；自审改动，不触碰用户评测模块。
- [x] 执行 `.venv/Scripts/python.exe -m pytest -q -m "not real"`（573 passed, 2 deselected，51.84 秒）。
- [x] 执行一次 `.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -s -m real --tb=short --show-capture=no`。预算保持 12 轮/2048 输出/40 模型/24 工具/240 秒；必须 completed、搜索/抓取/引用和 checkpoint 一致才算通过（1 passed，114.53 秒，首次格式失败经一次纠正恢复）。
- [x] 在 `docs/architecture/2026-10-01-run-result-verification.md` 记录实测，更新 spec 与本计划；仅提交本任务文件，保留用户已有改动。
