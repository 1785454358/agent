# Isolated Agent Tool Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实 Ragas 工具指标评测可导出的 Agent 轨迹，同时保留权威应用终态与显式未知值。

**Architecture:** 生产评测 runner 捕获模型工具请求和实际 ToolGateway 结果，导出 schema_version=1 的本地 JSON。独立 backend/.venv-ragas 的评分脚本不导入 deeptrace，通过 Ragas collections 评分并生成独立 JSON/Markdown。不修改生产 SDK、不引入评测服务、不调用真实 API。

**Tech Stack:** Python / pytest / Pydantic（主环境）/ Ragas 0.4.3（独立环境）/ JSON。

**Spec:** [approved design](../specs/2026-10-01-agent-evaluation-design.md)

## Global Constraints

- 原生产 .venv、项目依赖约束和真实 API 限额不变。
- 当前只做工具评测；不扩题、不做记忆消融、不执行真实 judge。
- 保留现有用户评测资产，修改只增量合入，不把整套未提交代码作为本次新增提交。
- 缺少参考调用标为未测，缺少框架显式报错，不把 null 变为 0。
- 工具指标衡量请求匹配，不把它误称实际执行成功率；实际工具结果另列。
- 默认排除并显式统计内部 write_todos；未知工具保留，避免过滤错误请求。F1 集合去重不代表重复执行无成本。
- 多分支分别记录，非严格指标不依赖并发完成顺序；严格顺序只支持单研究分支，跨分支严格任务显式未测。
- 要求的执行子技能当前不可用，在当前线程按任务逐项执行与审查。

### Task 1: 运行记录与轨迹导出

**Files:** 新建 `backend/src/deeptrace/eval/trajectory.py`、`backend/tests/eval/test_trajectory.py`、`backend/tests/eval/test_result_contract.py`；增量修改 eval/env.py、runner.py、dataset.py、__main__.py。

**Interfaces:** `TrajectoryRecorder.record_model(role, messages, response)` 记录角色、研究查询分支和工具请求；`record_execution(caller, request, result)` 记录 request/call/caller 身份与真实结果。`build_tool_eval_export(records, questions, corpus, model_kind)` 返回版本化 JSON envelope，不把参考答案交给被测模型。

- [x] 先写行为测试：脚本 Workflow 的 status=completed 与请求/成功抓取均被记录；responder 输出非法时 research completed 但整体 partial，汇总 completed=0；工具失败和未知模型工具请求不消失。

```python
records = await run_matrix(questions, corpus, model_factory=InvalidResponder, modes=(ResearchMode.WORKFLOW,))
assert records[0].status == "partial"
assert records[0].research_termination_reason == "completed"
assert score_records(records, questions).modes[0].completed == 0
```

- [x] 运行 `.venv/Scripts/python.exe -m pytest tests/eval/test_trajectory.py tests/eval/test_result_contract.py -q`，观察缺失行为失败（最初 5 failed，随后通过；观察补充先 2 failed 再通过）。
- [x] env 的现有计数包装器增量记录轨迹；runner 直接消费 ApplicationRunResult；取消传播，其他顶层执行异常生成 failed 记录后继续矩阵。
- [x] EvalQuestion 增加 `reference_tool_calls: list[ReferenceToolCall] | None = None`、`strict_tool_order: bool = False`；原有三题不自动伪造 gold 调用，未经标注为未测。
- [x] `--out` 除原报告/records 外生成 tool_eval.json，包含题目与语料内容哈希、model_kind 和每条状态/轨迹/参考。测试通过后保留用户原有文件未提交状态。

### Task 2: 独立 Ragas 工具评分

**Files:** 新建 `backend/evaluation/ragas_tools.py`、requirements.in、requirements.lock、tests/test_ragas_tools.py；修改 .gitignore 排除 .venv-ragas。

**Interfaces:** `async score_export(payload) -> dict`，输入 Task 1 envelope；每指标输出 name/status/value/reason/error，result=value 在 0–1，缺失或失败为 null。`render_report(report) -> str` 分模式展示适用、失败、覆盖率与均值，保留系统失败计数。

- [x] 写正确/错误参数/缺失/额外/换序工具测试，字面预期：正确 accuracy=1/F1=1；两项中一项错参数 accuracy=0.5/F1=0.5；缺失两项中一项 accuracy=0/F1≈0.6667；额外一项 accuracy=0/F1≈0.8；默认换序不减分，单分支 strict 换序 accuracy=0。

```python
payload = {
    "schema_version": 1,
    "samples": [{
        "question_id": "q", "mode": "workflow", "run_id": "r",
        "status": "completed", "question": "checkpoint",
        "reference_tool_calls": [{"name": "search_web", "args": {"query": "checkpoint"}}],
        "trajectory": {"model_turns": [{"role": "researcher", "branch": "q", "tool_calls": [{"name": "search_web", "args": {"query": "wrong"}}]}]},
    }],
}
report = await score_export(payload)
assert report["results"][0]["metrics"]["tool_call_f1"]["value"] == 0.0
```

- [x] 以独立 `uv venv .venv-ragas --python .venv/Scripts/python.exe` 建环境；固定 ragas==0.4.3、pytest==9.1.1、兼容 langchain-community==0.4.1；uv pip compile 生成锁文件，再用 uv pip install 安装到 .venv-ragas。不使用生产环境安装命令。
- [x] 独立环境运行 `.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q`，确认测试 RED（初始 12 failed）；再实现懒加载的标准库/Ragas 脚本；导入前设置 RAGAS_DO_NOT_TRACK=true。
- [x] 参考为 null 或轨迹缺失时显式 not_applicable；并发严格顺序不可解释时 not_applicable；逐指标异常为 null/error，不吞掉或改成零。Ragas 不存在时命令失败，不回退 legacy_custom。
- [x] 验证框架实际执行与上述区分度，补重复调用与 failed execution 保留测试；不声称工具调用分数证明目标或答案正确（最终 18 passed）。

### Task 3: 报告未知值、全量回归与交接

**Files:** 增量修改 eval/runner.py、scoring.py、report.py；新建 tests/eval/test_metric_reporting.py 和 docs/evaluation/isolated-ragas-tools.md。

**Interfaces:** legacy judge 保留原 1–5 类型；记录 judge_attempted/judge_error，未测或全部失败时均值为 None；报告标识 legacy_custom，与独立 Ragas 0–1 报告分开。

- [x] 先补未测/judge 全失败/部分失败用例并观察 RED（5 failed）；实现覆盖率、失败数与 N/A，不算入零。
- [x] `.venv/Scripts/python.exe -m pytest tests/eval -q` 与独立 Ragas 测试通过（29 / 18 passed）；全量主环境离线 585 passed, 2 deselected，49.68 秒。
- [x] 运行生产 CLI 导出一题离线轨迹，再用独立评分 CLI 读取（两个工具指标均 1）；原三题缺少人工 gold 调用，实际报告 0/3 已测、N/A；不冒充质量得分。
- [x] Ruff、格式、git diff --check；使用 code-review-and-quality 自审安全、错误分支、界面边界与复杂度；记录版本、测试与局限。
- [x] 提供可运行命令与文档，不在本轮提交包含用户原始未提交内容的整套 eval 文件。
