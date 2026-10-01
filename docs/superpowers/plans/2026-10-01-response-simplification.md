# Response Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. 当前会话未提供这两项技能，采用本会话逐项执行、TDD 与独立自审的替代方式。

**Goal:** 删除响应生成的多路纠错，将业务生成限制为首次调用与至多一次合并纠错。

**Architecture:** 保留 ResponsePolicy 和 load_evidence → generate → validate 图结构。generate 只维护一个候选正文、一个问题列表和一个可选纠错；解码复用 harness.model_io，引用判断由既有 validator 完成。

**Tech Stack:** Python 3.11+、LangGraph、Pydantic、pytest、现有 ModelGateway。

**Spec:** `docs/superpowers/specs/2026-10-01-response-simplification-design.md`

## Global Constraints

- 不修改数据库、Runtime、部署模式、依赖版本、认证或前端。
- 不新增 schema 能力探测、Provider 切换或结构化输出配置。
- ANSWER / BRIEF / REPORT、构图入口、ResponseInput / ResponseOutcome 字段保持兼容。
- load_evidence → generate → validate 节点名与 Checkpoint 边界保持不变。
- 全部模型调用经过 ModelGateway，并保留 system instruction、原始任务、当前约束。
- evidence 正文只在局部使用，不复制进可恢复 State。
- context token 预算、纯文本格式处理、引用校验和 partial 降级保留。
- 保护现有未提交的 responses/citations.py、对应测试、评测、配置和索引文档；只暂存本次路径。

## Task 1：失败回归与单一生成流程

**Files:**

- Modify: `backend/src/deeptrace/responses/graph.py`
- Test: `backend/tests/responses/test_graph.py`
- Reuse: `backend/src/deeptrace/harness/model_io.py`

**Interfaces:**

- Consumes: `payload_text(response: Any) -> str`、现有 `_extract_content(raw_text: str) -> str`、`extract_citation_markers`、`_looks_incomplete`、`_cut_at_sentence`。
- Produces: 保持 `build_generate_node(policy, budget_config=None)` 的节点返回契约：可用时返回 ResponseDraft，否则返回 draft=None；无证据时返回现有 no_evidence Outcome。
- 内部候选问题用 `list[str]`，合并后组成纠错 prompt；不建立新服务类。

- [x] Step 1：新增失败回归。序列型模型替身仅替代外部模型，运行真实 response 图、Evidence Store 与 validator：

```python
responses = iter(["not JSON", json.dumps({"content": "长正文 [1]。" * 400})])
model = ScriptedModelGateway({"responder": lambda prompt: next(responses)})
result = await _run_response(build_answer_graph(), model, _response_input(ids), fixture)
assert len(model.calls) == 2
assert len(result["outcome"].content) <= 2000
assert result["outcome"].cited_evidence_ids == ids
```

另覆盖“无引用 + 超长 + 悬空”同时触发、纠错解析失败保留首稿、真实 AIMessage 文本块。序列耗尽时不产生额外有效模型结果，使错误的第三次调用被检测。

- [x] Step 2：在 backend 目录运行新增测试，记录正确的失败原因（多次调用 / content blocks 解析错误）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/responses/test_graph.py -q --tb=short
```

- [x] Step 3：实现最小流程。移除响应模块重复解码，删除 fit_length 和两条独立纠错分支；按下列控制流写入 generate：

```python
content = ""
issues = []
try:
    content = await invoke_model()
except (ValidationError, ValueError, TypeError):
    issues.append("无法解析或正文为空")
if content:
    if not extract_citation_markers(content):
        issues.append("正文没有引用标记")
    if len(content) > policy.max_content_chars:
        issues.append("超过篇幅上限")
    if _looks_incomplete(content):
        issues.append("正文不完整")
if issues:
    try:
        content = await invoke_model(corrective_suffix=combined_requirements)
    except (ValidationError, ValueError, TypeError):
        logger.warning("Correction unparseable; retaining original candidate")
if not content:
    return {"draft": None}
output_incomplete = _looks_incomplete(content)
output_truncated = len(content) > policy.max_content_chars
if output_truncated:
    content = _cut_at_sentence(content, policy.max_content_chars)
```

`combined_requirements` 由已发现问题、现有 JSON / 引用约束与 policy.max_content_chars 构造，包含不完整时的完整句要求。不捕获 transport / cancellation 为普通格式错误。观测仍调用既有 _record_generation_observability。

- [x] Step 4：运行响应、集成与 Harness 响应测试，确认单次 / 无调用、篇幅、budget、纯文本、引用、跨 workspace 与 Checkpoint 兼容：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/responses tests/integration/test_workflow_response_exit_gate.py tests/harness/test_workflow_response_slice.py -q --tb=short
```

- [x] Step 5：自审取消 / transport 传播和重复正文读取，检查 diff。只提交 graph.py 与 test_graph.py 的实现和回归。

## Task 2：全仓库验收与文档

**Files:**

- Modify: `docs/architecture/agent-harness.md`
- Modify: 当前 spec / plan 的状态与验收记录

**Interfaces:**

- Consumes: Task 1 的稳定构图接口与单一纠错行为。
- Produces: 可对照代码阅读的响应边界说明，以及实际测试结果。

- [x] Step 1：文档说明每次 generate 至多两次业务调用；Gateway 重试和 Checkpoint 重放不计入这个局部保证。说明一次修复后确定性篇幅处理和原有引用降级。
- [x] Step 2：在 backend 执行全仓库离线测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not real" -q --tb=short
```

- [x] Step 3：使用 code-review-and-quality 自审，运行明确路径的 Ruff、格式检查和 git diff --check。不得通过删除业务保护、放宽引用 validator 或更改用户文件换取通过。
- [x] Step 4：记录结果，显式暂存文档路径并提交；交付响应简化结果，明确旧 Topic 和记忆整理为独立后续工作。

## 计划自审

- 每个设计要求都有对应测试或 Task 2 验收。
- 只引入简单候选问题列表，不新增框架；现有解码与业务解析职责不混淆。
- 首稿不可解析且纠错失败返回现有降级；首稿可用且纠错失败保留首稿。
- 调用数、输出与引用一起验证；不能仅靠模型替身存在或源码字符串断言。

## 实施验收

- 首轮新增回归：5 项按预期失败，分别证明多路径导致第三次调用、纠错未合并要求、文本块解码不支持。
- 响应 / 集成 / Harness 响应测试：`53 passed`。
- 全仓库 `not real`：`517 passed, 2 deselected`（42.02 秒）。
- 改动源文件 Ruff check、源文件和测试的格式检查通过；测试 I / F 检查通过；`git diff --check` 无空白问题。
- 生产响应模块净减少 55 行；没有新增框架、类、依赖或 Provider 配置。
- 自审确认首次生成与可选一次纠错是唯一两处业务模型调用；引用 validator、正文局部复用、预算、公开构图接口与节点边界保持。
- 取消测试的最初断言与当前 LangGraph 的包装规则不符。核查本地框架源码后改为断言 NodeCancelledError 保留 CancelledError 原因；未修改生产取消逻辑以迎合错误测试。
- 仅响应图和本次回归进入实现提交；用户既有引用 / 评测 / 配置修改保持不变。
- 旧 Topic 和记忆入口整理未在本项中改动；需要各自的消费迁移和设计验收，不以响应测试通过代替它们的完成。
