# Memory Admission and Evidence Batching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

- [ ] 增加测试：实际策略第一次允许、第二次拒绝，显式保存应成功且真实 Store 有一条偏好；旧实现会因重复准入拒绝保存。

```python
class OncePolicy(MemoryWritePolicy):
    def can_store(self, record, *, source):
        allowed = not self.checked
        self.checked = True
        return allowed and super().can_store(record, source=source)
# monkeypatch lifecycle.MemoryWritePolicy 为该策略工厂，运行显式保存。
assert response.partial_reason == "memory_updated"
assert len(await store.list_namespace(("user", "user-1", "preferences"))) == 1
```

- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory/test_lifecycle.py -q`，确认重复准入测试 RED。
- [ ] 在 write.py 添加拒绝异常，remember 抛该异常；节点删预检，在 try 中仅调用 remember，分别处理拒绝和存储错误。

```python
class MemoryWriteRejected(ValueError):
    """The write boundary rejected admission, not a storage outage."""
```

- [ ] 补充拒绝不保存、Store ValueError 不冒充拒绝、取消继续传播、索引故障不推翻权威保存的兼容测试。
- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory -q`；审查并仅提交 write、lifecycle 和本任务测试。

### Task 2: SQL 严格批量读取

**Interfaces:** `SqlAlchemyEvidenceStore.get_many(tenant_id, evidence_ids) -> tuple[Evidence, ...]` 不变；最多 400 个唯一 ID 一批，空输入无 SQL，缺失仍 KeyError。

- [ ] 增加真实 SQLite 测试，使用 SQLAlchemy before_cursor_execute 监听读取。两个去重 ID 加重复输入应只查一次，SELECT 不带 body；401 个 ID 应两批；空输入无查询。

```python
records = await store.get_many("tenant-1", [second.id, first.id, second.id])
assert [r.id for r in records] == [second.id, first.id, second.id]
assert len(selects) == 1
assert "evidence_records.body" not in selects[0]
records[0].title = "changed"
assert records[2].title == "original"
```

- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/persistence/test_evidence_store.py -q`，确认旧逐 ID 查询 RED。
- [ ] 验证所有输入，去重分组；同一会话内执行 tenant + IN 查询并 defer(body)；按输入顺序返回独立 model_copy。缺失 KeyError 不改成部分返回。

```python
statement = select(EvidenceRecordRow).options(defer(EvidenceRecordRow.body)).where(
    EvidenceRecordRow.tenant_id == tenant,
    EvidenceRecordRow.evidence_id.in_(batch),
)
```

- [ ] 补充缺失 / 跨租户、重复副本、空输入、非法字符串 / 空标识符测试；同一语义也运行内存 EvidenceStore 测试。
- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/persistence/test_evidence_store.py tests/tools/test_evidence_store.py -q`；审查并提交 SQL Store 与测试。

### Task 3: 整理去重与全链路验收

**Interfaces:** `_consolidate_memory(state, runtime) -> {}` 不变；私有来源加载 helper 在 get_many KeyError 时逐唯一 ID 回退，其他异常由整理边界降级。已核验 ACTIVE 集合之外的候选不写。

- [ ] 增加 20 条 finding 共享来源的回归：委托真实 Evidence Store 并计数，核对真实 Memory Store 20 条事实、来源与 TTL；旧实现重复读取 20 次，应 RED。

```python
assert len(facts) == 20
assert reads == [[evidence.id]]
assert all(fact.source_evidence_ids == [evidence.id] for fact in facts)
```

- [ ] 候选先校验 MemoryRecord；建立一次 outcome 允许集合与去重来源集合；无候选直接返回。按核验集合写入，逐条写失败隔离，最后只索引已保存 ACTIVE 记录。
- [ ] KeyError 发出一次降级后逐 ID 查，缺失跳过；普通 RuntimeError 只降级、不逐条重试；取消不吞掉。
- [ ] 补混合有效 / 缺失 / 跨 workspace / superseded、超长与超过来源上限、无候选、20 条 finding 上限、单个 upsert 失败和删除事实不复活的行为覆盖。
- [ ] 在现有 context 下减少重复 runtime.context 与 namespace 切片，不改 recall 的优先级和候选过滤语义。
- [ ] Run: `.venv/Scripts/python.exe -m pytest tests/harness/memory tests/persistence/test_memory_store.py tests/persistence/test_evidence_store.py tests/tools/test_evidence_store.py tests/harness/test_workflow_response_slice.py tests/integration/test_recovery.py -q`。
- [ ] 更新 memory.md；Run: `.venv/Scripts/python.exe -m pytest -m "not real" -q --tb=short`。
- [ ] 修改源文件 Ruff 全规则，测试 I/F 与格式检查，git diff --check；进行正确性 / 安全 / 架构 / 性能 / 简洁性自审，不宣称真实 MySQL / Provider 已验证。
- [ ] 显式提交本任务文件，记录查询次数与实际测试结果，勾选完成步骤。

## 实际验收

完成时记录 RED / GREEN、数据库查询计数与完整回归结果。
