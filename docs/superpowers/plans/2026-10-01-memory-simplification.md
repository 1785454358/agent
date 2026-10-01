# Memory Admission and Evidence Batching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 去掉重复记忆准入，去重核验证据，消除 SQL 元数据读取 N+1，保持记忆保护与公共契约。

**Architecture:** remember 统一准入与版本写入；lifecycle 组织有限候选和证据检查；SQL Evidence Store 在 tenant 范围批量读取元数据。缺失证据只阻止依赖它的事实，索引与自动整理继续允许降级。

**Tech Stack:** Python、pytest-asyncio、SQLAlchemy、SQLite、现有 LangGraph Memory / Evidence Store。

**Spec:** `docs/superpowers/specs/2026-10-01-memory-simplification-design.md`；用户回复“开始”，确认实施。

## Global Constraints

- 不新增 Memory Agent、记忆服务层、异步队列、框架依赖或配置选项。
- 不修改 EvidenceStore 协议、数据库 schema 或迁移文件。
- 版本、tombstone、30 天 FACT TTL、召回接口、偏好优先和 token 预算保留。
- 自动整理最多前 20 条 finding；MemoryRecord 每条来源最多 20 个，合法来源集合最多 400 个。
- SQL 每批最多 400 个唯一 ID，返回排序与重复项、严格 KeyError 语义不变；不加载正文。
- KeyError 才逐 ID 回退；其他证据存储故障不做逐条重试。
- 不删除历史记忆、向量、兼容类型或公开工具函数；不覆盖或提交用户现有引用 / 评测 / 配置修改。
- 命令从 backend 执行：`.venv/Scripts/python.exe -m pytest`。无执行子技能，按用户开始要求在本会话执行；不为执行方式再次暂停。

## 文件职责

- `backend/src/deeptrace/harness/memory/write.py`：MemoryWriteRejected 与一次准入。
- `backend/src/deeptrace/harness/memory/lifecycle.py`：显式保存分类、有限候选、去重来源与失败隔离；仅简化 context / namespace 使用，不重建召回服务。
- `backend/src/deeptrace/persistence/evidence_store.py`：有界 tenant-scoped IN 查询、元数据映射与独立返回副本。
- `backend/tests/harness/memory/test_lifecycle.py`：真实存储的保存、整理结果；必要时使用委托真实组件的查询计数或故障注入。
- `backend/tests/persistence/test_evidence_store.py`：真实 SQLite 查询探针及严格读取契约。
- `docs/architecture/memory.md`：当前入口和批量语义；本计划记录实际验收。

### Task 1: 单一准入

**Interfaces:** `MemoryWriteRejected(ValueError)` 保留错误消息 `memory_write_rejected`；remember 签名不变。节点对规则拒绝返回 memory_rejected，对存储异常返回 memory_unavailable。

- [x] 增加测试：委托现有准入策略并记录次数，显式保存成功且真实 Store 有一条偏好；旧实现检查两次，新增断言明确 RED。

```python
checks = []
class TracedPolicy(MemoryWritePolicy):
    def can_store(self, record, *, source):
        checks.append(source)
        return super().can_store(record, source=source)
# monkeypatch lifecycle.MemoryWritePolicy 为 TracedPolicy，运行显式保存。
assert response.partial_reason == "memory_updated"
assert len(await store.list_namespace(("user", "user-1", "preferences"))) == 1
assert checks == ["user_request"]
```

- [x] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory/test_lifecycle.py -q`，确认重复准入测试 RED。
- [x] 在 write.py 添加拒绝异常，remember 抛该异常；节点删预检，在 try 中仅调用 remember，分别处理拒绝和存储错误。

```python
class MemoryWriteRejected(ValueError):
    """The write boundary rejected admission, not a storage outage."""
```

- [x] 补充拒绝不保存、Store ValueError 不冒充拒绝、取消继续传播、索引故障不推翻权威保存的兼容测试。
- [x] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory -q`；审查并仅提交 write、lifecycle 和本任务测试。

### Task 2: SQL 严格批量读取

**Interfaces:** `SqlAlchemyEvidenceStore.get_many(tenant_id, evidence_ids) -> tuple[Evidence, ...]` 不变；最多 400 个唯一 ID 一批，空输入无 SQL，缺失仍 KeyError。

- [x] 增加真实 SQLite 测试，使用 SQLAlchemy before_cursor_execute 监听读取。两个去重 ID 加重复输入应只查一次，SELECT 不带 body；401 个 ID 应两批；空输入无查询。

```python
records = await store.get_many("tenant-1", [second.id, first.id, second.id])
assert [r.id for r in records] == [second.id, first.id, second.id]
assert len(selects) == 1
assert "evidence_records.body" not in selects[0]
records[0].title = "changed"
assert records[2].title == "original"
```

- [x] Run: `.venv/Scripts/python.exe -m pytest tests/persistence/test_evidence_store.py -q`，确认旧逐 ID 查询 RED。
- [x] 验证所有输入，去重分组；同一会话内执行 tenant + IN 查询并 defer(body)；按输入顺序返回独立 model_copy。缺失 KeyError 不改成部分返回。

```python
statement = select(EvidenceRecordRow).options(defer(EvidenceRecordRow.body)).where(
    EvidenceRecordRow.tenant_id == tenant,
    EvidenceRecordRow.evidence_id.in_(batch),
)
```

- [x] 补充缺失 / 跨租户、重复副本、空输入、非法字符串 / 空标识符测试；同一语义也运行内存 EvidenceStore 测试。
- [x] Run: `.venv/Scripts/python.exe -m pytest tests/persistence/test_evidence_store.py tests/tools/test_evidence_store.py -q`；审查并提交 SQL Store 与测试。

### Task 3: 整理去重与全链路验收

**Interfaces:** `_consolidate_memory(state, runtime) -> {}` 不变；私有来源加载 helper 在 get_many KeyError 时逐唯一 ID 回退，其他异常由整理边界降级。已核验 ACTIVE 集合之外的候选不写。

- [x] 增加 20 条 finding 共享来源的回归：委托真实 Evidence Store 并计数，核对真实 Memory Store 20 条事实、来源与 TTL；旧实现重复读取 20 次，应 RED。

```python
assert len(facts) == 20
assert reads == [[evidence.id]]
assert all(fact.source_evidence_ids == [evidence.id] for fact in facts)
```

- [x] 候选先校验 MemoryRecord；建立一次 outcome 允许集合与去重来源集合；无候选直接返回。按核验集合写入，逐条写失败隔离，最后只索引已保存 ACTIVE 记录。
- [x] KeyError 发出一次降级后逐 ID 查，缺失跳过；普通 RuntimeError 只降级、不逐条重试；取消不吞掉。
- [x] 补混合有效 / 缺失 / 跨 workspace / superseded、超长与超过来源上限、无候选、20 条 finding 上限、单个 upsert 失败和删除事实不复活的行为覆盖。
- [x] 在现有 context 下减少重复 runtime.context 与 namespace 切片；保留无 context / 无 Store 的兼容保护，不改 recall 的优先级和候选过滤语义。
- [x] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory tests/persistence/test_memory_store.py tests/persistence/test_evidence_store.py tests/tools/test_evidence_store.py tests/harness/test_workflow_response_slice.py tests/integration/test_recovery.py -q`。
- [x] 更新 memory.md；Run: `.venv/Scripts/python.exe -m pytest -m "not real" -q --tb=short`。
- [x] 修改源文件 Ruff 全规则，测试 I/F 与格式检查，git diff --check；进行正确性 / 安全 / 架构 / 性能 / 简洁性自审，不宣称真实 MySQL / Provider 已验证。
- [x] 显式提交本任务文件，记录查询次数与实际测试结果，勾选完成步骤。

## 实际验收

日期：2026-10-01，三个任务完成。生产改动仅 write.py、lifecycle.py、SQL evidence_store.py；无依赖 / schema / 配置变化，没有提交用户的引用、评测、配置及其他文档修改。

### TDD 与查询计数

- Task 1 RED：重复准入断言失败；旧实现 checks 为两次。单一入口修改后，记忆专项 39 passed。
- Task 2 RED：3 failed、10 passed。旧 SQL 实现对两个唯一 ID 加重复项查 3 次，401 个唯一 ID 查 401 次，空列表没有校验非法 tenant。修改后证据专项首轮 18 passed。
- Task 3 RED：5 failed、12 passed。旧整理对 20 条共享来源查 20 次，对超出 MemoryRecord 限制的候选仍先查来源，普通存储故障逐条重试。
- Task 3 GREEN：正常共享来源只调用一次 get_many，真实 Store 保存 20 条 FACT，TTL 为当前时间加 30 天；21 条 finding 只处理前 20 条。
- SQL 查询探针：重复输入只查一次；401 个唯一 ID 分两批，SQLite 参数数为 401 / 2（含 tenant 参数）；SELECT 均不加载 body。空列表零查询，严格缺失、跨租户及同 ID 不同租户、独立副本契约保留。
- 缺失回退：一个批次后，每个唯一 ID 至多单独核验一次；有效 sibling 保留，missing / foreign / superseded 不写。普通异常只降级，不做逐事实重试。

### 自审修正与边界

按 code-review-and-quality 的正确性、可读性、架构、安全和性能五轴自审。技能引用的安全 / 性能附录本地不存在，使用其主文档检查项和实际测试完成审查，不宣称独立第二模型审阅。

1. Harness EvidenceStore 协议没有 get；回退改用既有单 ID get_many，不扩展公开协议。仅提供协议读取能力的委托真实 Store 测试先出现 2 failed、1 passed，修正后通过。
2. LangGraph 可以在 context 缺失时先检查模式注册；初次全回归暴露一个 AttributeError。三个记忆节点新增无 context / 无 Store 测试：修正前 3 failed、3 passed，保留边界保护后通过；既有模式未注册测试恢复正确 KeyError。没有修改该测试或注册行为来绕过问题。
3. 确认候选校验先于来源读取、合法来源最多 400；只有 KeyError 回退，其他异常不伪装成核验成功。
4. SQL 使用参数绑定且含 tenant 条件；没有暴露 body 或新增正文注入路径。namespace 检查不等同于新增认证系统。
5. 重放不刷新 TTL / 版本；删除 FACT 不复活且不重新索引；单个 upsert / 候选失败隔离；取消传播。偏好优先、词汇 / 语义回退和 token 预算沿用原有行为。

### 最终验收

```powershell
# backend 目录
.venv/Scripts/python.exe -m pytest tests/harness/memory tests/persistence/test_memory_store.py tests/persistence/test_evidence_store.py tests/tools/test_evidence_store.py tests/harness/test_workflow_response_slice.py tests/integration/test_recovery.py -q --tb=short
# 98 passed in 24.35s
.venv/Scripts/python.exe -m pytest -m "not real" -q --tb=short
# 547 passed, 2 deselected in 43.36s
```

- 修改源文件 Ruff 全规则通过；修改测试 I / F 通过；五个修改 Python 文件格式通过；任务范围 git diff --check 通过。
- 原有事务 / tombstone 回归没有重写，继续纳入上述验收。
- 非真实环境验收含 SQLite 和脚本化外部边界；真实 MySQL 多进程锁、Chroma 服务、Embedding / LLM Provider 未运行。
- 代码提交：`2641455`（单一准入）、`06c3582`（SQL 批量元数据）、`95d7c26`（整理去重与兼容边界）。
