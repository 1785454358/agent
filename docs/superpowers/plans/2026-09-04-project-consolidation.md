# DeepTrace Project Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前未提交的简化研究架构、并行执行、API、Memory 和文档调整收口为经过自动化与一次真实 API 回归验证的稳定 Git 基线。

**Architecture:** 保留 Planner → 并行 Researcher → 本地 BGE-M3 原句压缩 → Writer 的主链路，以及 FastAPI、SSE、运行持久化和可选 Research Memory。阶段 4 Evidence/Claim/Verifier 保持删除状态；真实日志、运行结果和 Memory 正文留在本地并由 Git 忽略。

**Tech Stack:** Python 3.12、Pydantic 2、LangChain、LangGraph、FastAPI、Uvicorn、HTTPX、Tavily、BGE-M3、pytest、uv

**Spec:** `docs/superpowers/specs/2026-09-04-project-consolidation-design.md`

**执行状态：** 已完成。首次真实回归暴露 Writer Provider 调用无超时的问题；完成测试驱动修复后进行了唯一一次复测，结果记录在 `docs/q.md`。

## Global Constraints

- 不恢复 Evidence Store、Claim Extractor、Verifier 或相关状态、提示词与测试。
- Token 只统计，不作为停止条件；页面、时间、步骤和可选费用仍是安全边界。
- 不删除本地日志、`runs/` 或 `memory/*.jsonl` 数据，只通过 `.gitignore` 排除。
- 不提交 `backend/.env`、真实 API Key、真实运行正文或日志。
- 保留 `backend/bench_run.py`，删除未使用的 `backend/main.py` 脚手架。
- 现有旧文档和参考实现删除按工作区状态提交，不恢复。
- 真实研究只运行一次，通过 API 路径覆盖 Agent、SSE 事件、持久化和 Writer。

---

### Task 1: 收口并提交后端稳定基线

**Files:**
- Modify: `backend/.gitignore`
- Delete: `backend/main.py`
- Modify: `backend/tests/agent/test_service.py`
- Modify: `backend/tests/test_cli.py`
- Commit: all other tracked and intentional untracked files under `backend/` except generated runtime data

**Interfaces:**
- Consumes: 当前工作区中已完成的简化研究链、并行任务、API、Memory 和测试实现。
- Produces: 一个不包含运行数据、可通过全部非真实测试的后端提交。

- [ ] **Step 1: 验证当前忽略规则不足（RED）**

Run from repository root:

```powershell
git check-ignore backend/api_server.log backend/bench_output_v7.log backend/run.log backend/runs/68a74691b549.json backend/memory/notes.jsonl
```

Expected: command exits with code 1 or omits one or more paths, proving current `.gitignore` does not protect all runtime artifacts.

- [ ] **Step 2: 确认 `backend/main.py` 是未使用脚手架**

Run:

```powershell
rg -n "backend\.main|from main import|import main|Hello from backend" backend docs -g '!*.log' -g '!runs/**' -g '!memory/**'
```

Expected: only `backend/main.py` itself contains `Hello from backend`; package scripts and tests do not import it.

- [ ] **Step 3: 更新运行产物忽略规则并删除脚手架**

Apply this exact `.gitignore` content while preserving the existing cache rules:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
*.py[cod]
*.log
runs/
memory/*.jsonl
```

Delete only `backend/main.py`. Do not delete any log, run JSON or Memory file from disk.

- [ ] **Step 4: 修复补丁格式告警**

Remove the extra blank line at EOF from:

- `backend/tests/agent/test_service.py`
- `backend/tests/test_cli.py`

Run:

```powershell
git diff --check
```

Expected: no whitespace errors. Line-ending conversion warnings are informational and do not fail the command.

- [ ] **Step 5: 验证新忽略规则（GREEN）**

Run:

```powershell
git check-ignore backend/api_server.log backend/bench_output_v7.log backend/run.log backend/runs/68a74691b549.json backend/memory/notes.jsonl
git status --short
```

Expected: all five runtime paths are printed by `git check-ignore`; `git status` no longer lists `*.log`, `runs/`, `memory/` or `backend/main.py`.

- [ ] **Step 6: 运行后端自动化验证**

Run from `backend/`:

```powershell
uv lock --check
uv run pytest -m "not real" -q
uv run python -m compileall -q src tests
uv run deeptrace --help
```

Expected: lock check passes; 86 tests pass; compileall and CLI help exit 0. Windows 捕获终端可能显示中文乱码，但退出码必须为 0。

- [ ] **Step 7: 暂存全部有效后端改动**

Run from repository root:

```powershell
git add -A -- backend
git status --short
git diff --cached --name-status
```

Expected: API、Memory、`bench_run.py`、`.python-version`、测试、依赖和阶段 4 删除均已暂存；`.env`、日志、`runs/`、`memory/*.jsonl` 和已删除的 `backend/main.py` 不出现在暂存清单中。

- [ ] **Step 8: 检查暂存内容和敏感信息**

Run:

```powershell
git diff --cached --check
git diff --cached | Select-String -Pattern 'sk-[A-Za-z0-9_-]{12,}|TAVILY_API_KEY\s*=\s*[^"''\s]|OPENAI_API_KEY\s*=\s*[^"''\s]'
```

Expected: no whitespace errors and no secret match. `.env.example` may contain empty placeholders only.

- [ ] **Step 9: 提交后端稳定基线**

Run:

```powershell
git commit -m "feat: ship simplified parallel research service"
```

Expected: commit succeeds and includes only backend project files, not runtime data.

---

### Task 2: 真实 API 回归、文档收口与最终提交

**Files:**
- Modify: `docs/q.md`
- Commit: current tracked and intentional untracked files under `docs/`
- Delete/Commit: current deletions under `reference_implementation/`

**Interfaces:**
- Consumes: Task 1 committed backend, existing `.env`,真实 LLM API、Tavily 和 `D:\Dev\Models\bge-m3`。
- Produces: 一条可追溯的真实 API 回归记录和与当前架构一致的文档提交。

- [ ] **Step 1: 启动隔离端口的真实 API 服务**

Run from `backend/` in a persistent terminal session:

```powershell
$env:PYTHONUNBUFFERED='1'
uv run uvicorn deeptrace.api:create_app --factory --host 127.0.0.1 --port 8010
```

Expected: Uvicorn reports application startup complete on `http://127.0.0.1:8010`. Keep the returned session id so the process can be stopped after validation.

- [ ] **Step 2: 创建唯一一次真实研究任务**

Run in a second terminal:

```powershell
$body = @{ question = '2024 年 AI Agent 领域有哪些热点新闻？' } | ConvertTo-Json
$created = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8010/researches' -ContentType 'application/json; charset=utf-8' -Body $body
$created | ConvertTo-Json -Depth 5
```

Expected: response contains a non-empty run `id` and initial status `queued` or `running`. Save the exact id returned by the server; do not invent it.

- [ ] **Step 3: 验证 SSE 端点可用**

Continue in the same second terminal so `$created.id` contains the exact server response:

```powershell
curl.exe --no-buffer --max-time 10 "http://127.0.0.1:8010/researches/$($created.id)/events"
```

Expected: output contains at least one SSE `data:` frame or the request remains connected until curl's 10-second client timeout. HTTP 404/500 is failure.

- [ ] **Step 4: 轮询到终态**

Continue in the same second terminal:

```powershell
$deadline = (Get-Date).AddMinutes(15)
do {
    $record = Invoke-RestMethod -Uri "http://127.0.0.1:8010/researches/$($created.id)"
    Write-Output ("{0:o} status={1} events={2}" -f (Get-Date), $record.status, $record.events.Count)
    if ($record.status -in @('completed', 'partial', 'failed', 'cancelled')) { break }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)
$record | ConvertTo-Json -Depth 20
```

Expected within 15 minutes: status is `completed` or `partial`; answer is non-empty; sources are non-empty; events include `planning.completed`, `writing.completed`, and `run.completed`; usage includes Planner、Researcher、Compression、Writer roles. `failed`、`cancelled` or deadline expiry is failure and must enter systematic debugging before any fix.

- [ ] **Step 5: 验证持久化并停止服务**

Continue from `backend/` in the same second terminal:

```powershell
Test-Path "runs/$($created.id).json"
Get-Content -Raw -Encoding utf8 "runs/$($created.id).json" | ConvertFrom-Json | Select-Object id,status,termination_reason
```

Expected: `Test-Path` returns `True`; persisted id and terminal status match the API response. Then send Ctrl-C to the Uvicorn session and verify it exits.

- [ ] **Step 6: 记录真实回归结果**

Append a dated section to `docs/q.md` containing only:

- run id
- question
- terminal status and termination reason
- elapsed time
- source count
- Planner、Researcher、Compression、Writer and total Provider Token
- persistence and SSE result

Do not copy the report body, source page content, API keys or `.env` values into documentation.

- [ ] **Step 7: 验证文档状态与废弃边界**

Run from repository root:

```powershell
rg -n "阶段 4.*已移除|阶段 5.*已完成|阶段 6.*未开始" docs/README.md docs/roadmap/deeptrace-evolution.md docs/architecture/deeptrace-target-architecture.md backend/README.md
rg -n "已废弃|废弃历史|不反映当前架构" docs/superpowers/specs/2026-09-01-stage-04-evidence-verification-design.md docs/superpowers/plans/2026-09-01-stage-04-evidence-verification.md
rg -n "DEEPTRACE_ENABLE_CLAIMS|开始证据核验|_initial_stage_four_state|_format_stage_four_summary" docs/README.md docs/roadmap docs/architecture backend/README.md backend/src backend/tests
```

Expected: active documents agree on the current stage status; both stage 4 historical files are marked deprecated; the final residual scan returns no active matches.

- [ ] **Step 8: 暂存文档和参考实现清理**

Run:

```powershell
git add -A -- docs reference_implementation
git status --short
git diff --cached --name-status
git diff --cached --check
```

Expected: all intentional docs changes, old docs deletions, `docs/q.md`, stage 4 deprecation markers and reference implementation deletions are staged. No backend runtime artifact is staged.

- [ ] **Step 9: 提交文档收口**

Run:

```powershell
git commit -m "docs: align project history with current architecture"
```

Expected: commit succeeds.

- [ ] **Step 10: 最终仓库检查**

Run:

```powershell
git status --short --branch
git log -3 --oneline --decorate
git ls-files | Select-String -Pattern '(^|/)(runs|memory)/|\.log$|(^|/)\.env$'
```

Expected: branch is clean apart from ignored local runtime data; the latest three commits are design、backend、documentation; no runtime log、run JSON、Memory正文或 `.env` is tracked.
