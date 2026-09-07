# ResearchPilot MySQL、Redis 与异步 Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ResearchPilot 增加可配置的 MySQL 持久化、Redis Streams 异步任务队列和独立 Research Worker，同时完整保留现有 Local 模式。

**Architecture:** API 通过统一 `ResearchRuntime` 接口工作；Local Runtime 继续使用进程内任务与 JSON，Distributed Runtime 将运行写入 MySQL 并投递 Redis Stream。独立异步 Worker 以至少一次语义消费任务，通过数据库条件更新保证业务幂等，并将持久事件和 Redis Pub/Sub 结合为可断线续传的 SSE。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic 2、SQLAlchemy 2 Async、asyncmy、Alembic、redis-py asyncio、Redis Streams、MySQL 8、Docker Compose、pytest、fakeredis、aiosqlite

**Spec:** `docs/superpowers/specs/2026-09-07-mysql-redis-worker-design.md`

## Global Constraints

- `DEEPTRACE_RUNTIME_MODE` 只允许 `local` 或 `distributed`，默认必须为 `local`。
- Basic、Deep、Multi-Agent 的 Agent 实现和统一 `build_real_agent` 路由不因本功能改变。
- MySQL 是 Distributed 模式的权威运行与事件存储；Redis 不保存最终报告的唯一副本。
- Redis Streams 采用至少一次消费，禁止宣称或模拟严格的恰好一次。
- Distributed API 不得直接执行 Agent；只有 Worker 可以执行研究任务。
- 事件必须先成功写入数据库，再发布 Redis 实时通知。
- 最终运行状态必须先成功写入数据库，再确认 Redis Stream 消息。
- Local 模式不得要求 MySQL、Redis、SQLAlchemy Engine 或 Worker 可用。
- 首期不实现网页抓取跨运行 Redis 缓存、Transactional Outbox、LangGraph 节点级恢复或生产级高可用。
- 所有代码变更必须先写失败测试；每项任务只提交列出的相关文件，禁止把现有脏工作区中的其他改动带入提交。

---

## File Structure

```text
backend/src/deeptrace/
├── api.py                         # HTTP/SSE 路由，仅依赖 ResearchRuntime
├── config/settings.py             # Local/Distributed 配置
├── runtime/
│   ├── __init__.py
│   ├── models.py                  # RunRecord、StoredEvent、JobMessage
│   ├── protocol.py                # ResearchRuntime 协议
│   ├── local.py                   # 现有进程内执行与 JSON 持久化
│   └── distributed.py             # MySQL + Redis API 运行服务
├── persistence/
│   ├── __init__.py
│   ├── database.py                # Async Engine 与 Session 工厂
│   ├── orm.py                     # SQLAlchemy 表模型
│   └── repository.py              # RunRepository 与 SQLAlchemy 实现
├── queue/
│   ├── __init__.py
│   ├── protocol.py                # ResearchBroker 协议
│   └── redis_streams.py           # Stream、Pub/Sub、取消标记
└── worker/
    ├── __init__.py
    ├── service.py                 # 单条消息执行、幂等、事件落库
    └── __main__.py                # Worker 消费循环入口

backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/20260907_01_create_research_runtime.py
backend/Dockerfile
docker-compose.yml
```

`runtime` 定义 API 看到的应用边界，`persistence` 和 `queue` 隔离基础设施细节，`worker` 是唯一执行 Agent 的 Distributed 组件。不要将 SQLAlchemy/Redis 依赖导入 Basic、Deep 或 Multi-Agent 包。

---

### Task 1: 运行领域模型、配置与依赖

**Files:**
- Create: `backend/src/deeptrace/runtime/__init__.py`
- Create: `backend/src/deeptrace/runtime/models.py`
- Create: `backend/tests/runtime/test_models.py`
- Modify: `backend/src/deeptrace/config/settings.py`
- Modify: `backend/src/deeptrace/models/result.py`
- Modify: `backend/src/deeptrace/basic/agent.py`
- Modify: `backend/src/deeptrace/deep/agent.py`
- Modify: `backend/src/deeptrace/multi_agent/agent.py`
- Modify: `backend/tests/basic/test_service.py`
- Modify: `backend/tests/deep/test_agent.py`
- Modify: `backend/tests/multi_agent/test_agent.py`
- Modify: `backend/tests/config/test_settings.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces: `RunMode`, `RunStatus`, `RunRecord`, `StoredEvent`, `JobMessage`。
- Produces: `Settings.runtime_mode`, `mysql_dsn`, `redis_url`, `redis_job_stream`, `redis_consumer_group`, `redis_consumer_name`, `redis_claim_idle_ms`, `worker_lease_seconds`, `worker_max_attempts`, `redis_cancel_ttl_seconds`。
- Consumes: 现有 `Settings.from_env()` 辅助解析函数和 API 的运行字段。

- [ ] **Step 1: 写领域模型和配置的失败测试**

```python
# backend/tests/runtime/test_models.py
from datetime import UTC, datetime

from deeptrace.runtime.models import JobMessage, RunRecord, StoredEvent


def test_run_record_has_stable_defaults() -> None:
    run = RunRecord(
        id="run-1",
        question="研究问题",
        mode="multi_agent",
        created_at=datetime.now(UTC),
    )
    assert run.status == "pending"
    assert run.attempt_count == 0
    assert run.version == 0
    assert run.sources == []
    assert run.unresolved_gaps == []


def test_job_and_event_are_serializable() -> None:
    job = JobMessage(message_id="1-0", run_id="run-1")
    event = StoredEvent(
        id=7,
        run_id="run-1",
        event_type="planning.started",
        payload={"message": "开始规划", "details": {}},
        created_at=datetime.now(UTC),
    )
    assert job.run_id == "run-1"
    assert event.model_dump(mode="json")["id"] == 7
```

在 `backend/tests/config/test_settings.py` 增加：

```python
def test_distributed_runtime_settings(monkeypatch, tmp_path) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "distributed")
    monkeypatch.setenv("DEEPTRACE_MYSQL_DSN", "mysql+asyncmy://app:pw@mysql/app")
    monkeypatch.setenv("DEEPTRACE_REDIS_URL", "redis://redis:6379/0")
    settings = Settings.from_env()
    assert settings.runtime_mode == "distributed"
    assert settings.mysql_dsn.endswith("@mysql/app")
    assert settings.redis_job_stream == "deeptrace:research:jobs"
    assert settings.worker_max_attempts == 3


def test_invalid_runtime_mode_is_rejected(monkeypatch, tmp_path) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPTRACE_RUNTIME_MODE", "cluster")
    with pytest.raises(RuntimeError, match="DEEPTRACE_RUNTIME_MODE"):
        Settings.from_env()
```

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/runtime/test_models.py tests/config/test_settings.py -q`

Expected: FAIL，提示 `deeptrace.runtime.models` 不存在或 `Settings` 缺少新字段。

- [ ] **Step 3: 添加依赖并实现最小模型与配置**

执行：

```powershell
cd backend
uv add "sqlalchemy[asyncio]>=2.0" "asyncmy>=0.2" "alembic>=1.13" "redis>=5.0"
uv add --dev "aiosqlite>=0.20" "fakeredis>=2.26" "pytest-asyncio>=0.24"
```

`runtime/models.py` 使用 Pydantic 模型，并保持 API 当前字段名称：

```python
RunMode = Literal["basic", "deep", "multi_agent"]
RunStatus = Literal[
    "pending", "running", "completed", "partial", "failed",
    "cancel_requested", "cancelled",
]


class RunRecord(BaseModel):
    id: str
    question: str
    mode: RunMode = "basic"
    status: RunStatus = "pending"
    termination_reason: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    error: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int = 0
    version: int = 0
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None


class StoredEvent(BaseModel):
    id: int
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class JobMessage(BaseModel):
    message_id: str
    run_id: str
```

为使 MySQL 能直接持久化各模式的缺口，在 `AgentResult` 末尾新增向后兼容字段：

```python
unresolved_gaps: list[str] = field(default_factory=list)
```

Basic 使用 `final.get("unresolved_gaps", [])`，Deep 使用已有局部变量 `unresolved`，Multi-Agent 使用 `final.get("final_gaps", [])` 填充该字段。现有测试构造器不传该字段时仍保持兼容，并分别在三种 Agent 的已有结果测试中断言映射正确。

在 `Settings` 增加对应字段，Local 默认值不得读取外部连接；`from_env()` 中仅当模式为 `distributed` 时要求非空 MySQL DSN 和 Redis URL。新增 `_choice()` 辅助函数校验枚举值。

`.env.example` 增加明确注释和安全示例，不填写真实密码：

```dotenv
DEEPTRACE_RUNTIME_MODE=local
DEEPTRACE_MYSQL_DSN=mysql+asyncmy://researchpilot:researchpilot@mysql:3306/researchpilot
DEEPTRACE_REDIS_URL=redis://redis:6379/0
DEEPTRACE_REDIS_JOB_STREAM=deeptrace:research:jobs
DEEPTRACE_REDIS_CONSUMER_GROUP=research-workers
DEEPTRACE_REDIS_CONSUMER_NAME=worker-1
DEEPTRACE_REDIS_CLAIM_IDLE_MS=60000
DEEPTRACE_WORKER_LEASE_SECONDS=120
DEEPTRACE_WORKER_MAX_ATTEMPTS=3
DEEPTRACE_REDIS_CANCEL_TTL_SECONDS=86400
```

- [ ] **Step 4: 运行目标测试和配置回归**

Run: `cd backend && uv run pytest tests/runtime/test_models.py tests/config/test_settings.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/pyproject.toml backend/uv.lock backend/.env.example backend/src/deeptrace/config/settings.py backend/src/deeptrace/models/result.py backend/src/deeptrace/basic/agent.py backend/src/deeptrace/deep/agent.py backend/src/deeptrace/multi_agent/agent.py backend/src/deeptrace/runtime/__init__.py backend/src/deeptrace/runtime/models.py backend/tests/config/test_settings.py backend/tests/runtime/test_models.py backend/tests/basic/test_service.py backend/tests/deep/test_agent.py backend/tests/multi_agent/test_agent.py
git commit -m "feat: add distributed runtime models and settings"
```

---

### Task 2: SQLAlchemy 数据库模型与运行仓储

**Files:**
- Create: `backend/src/deeptrace/persistence/__init__.py`
- Create: `backend/src/deeptrace/persistence/database.py`
- Create: `backend/src/deeptrace/persistence/orm.py`
- Create: `backend/src/deeptrace/persistence/repository.py`
- Create: `backend/tests/persistence/test_repository.py`

**Interfaces:**
- Consumes: `RunRecord`, `RunStatus`, `StoredEvent`。
- Produces: `create_session_factory(dsn: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]`。
- Produces: `RunRepository` 协议和 `SqlAlchemyRunRepository`，方法签名如下。

```python
class RunRepository(Protocol):
    async def create(self, run: RunRecord) -> None: ...
    async def get(self, run_id: str) -> RunRecord | None: ...
    async def list(self, limit: int = 100) -> list[RunRecord]: ...
    async def claim(self, run_id: str, worker_id: str, lease_seconds: int) -> RunRecord | None: ...
    async def renew_lease(self, run_id: str, worker_id: str, lease_seconds: int) -> bool: ...
    async def request_cancel(self, run_id: str) -> RunRecord | None: ...
    async def append_event(self, run_id: str, event: RunEvent) -> StoredEvent: ...
    async def events_after(self, run_id: str, event_id: int, limit: int = 500) -> list[StoredEvent]: ...
    async def complete(self, run_id: str, worker_id: str, result: AgentResult) -> RunRecord | None: ...
    async def fail(self, run_id: str, worker_id: str, error: str) -> RunRecord | None: ...
    async def cancel(self, run_id: str, worker_id: str, error: str) -> RunRecord | None: ...
```

- [ ] **Step 1: 写仓储失败测试**

使用 `sqlite+aiosqlite:///:memory:` 创建真实异步数据库，覆盖 MySQL 之外的仓储语义：

```python
@pytest.mark.asyncio
async def test_repository_claim_is_idempotent(repository) -> None:
    run = make_run("run-1")
    await repository.create(run)
    claimed = await repository.claim("run-1", "worker-1", 60)
    duplicate = await repository.claim("run-1", "worker-2", 60)
    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt_count == 1
    assert duplicate is None


@pytest.mark.asyncio
async def test_repository_persists_ordered_events(repository) -> None:
    await repository.create(make_run("run-1"))
    first = await repository.append_event(
        "run-1", RunEvent(event_type="planning.started", message="开始")
    )
    second = await repository.append_event(
        "run-1", RunEvent(event_type="planning.completed", message="完成")
    )
    events = await repository.events_after("run-1", first.id)
    assert [item.id for item in events] == [second.id]
    assert events[0].payload["message"] == "完成"
```

同时测试 `list()` 按 `created_at` 倒序、`request_cancel()` 只接受非终态、`renew_lease()` 只允许当前 Worker 续租、租约过期后另一 Worker 可重新领取、旧 Worker 无法写入终态、`complete()` 映射全部 `AgentResult` 用量字段、未知运行返回 `None`。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/persistence/test_repository.py -q`

Expected: FAIL，提示 `deeptrace.persistence` 不存在。

- [ ] **Step 3: 实现 ORM 和仓储**

`orm.py` 定义 `Base(DeclarativeBase)`、`ResearchRunRow` 和 `RunEventRow`。跨 SQLite/MySQL 测试统一使用 `JSON`、`Text`、`String`、`DateTime(timezone=True)`，状态以字符串保存，不使用数据库 Enum。

`claim()` 必须是条件更新，不得先查后改：

```python
statement = (
    update(ResearchRunRow)
    .where(
        ResearchRunRow.id == run_id,
        or_(
            ResearchRunRow.status == "pending",
            and_(
                ResearchRunRow.status == "running",
                ResearchRunRow.lease_expires_at < now,
            ),
        ),
    )
    .values(
        status="running",
        started_at=now,
        updated_at=now,
        attempt_count=ResearchRunRow.attempt_count + 1,
        version=ResearchRunRow.version + 1,
        lease_owner=worker_id,
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
)
result = await session.execute(statement)
if result.rowcount != 1:
    await session.rollback()
    return None
await session.commit()
return await self.get(run_id)
```

`complete()`、`fail()` 和 `cancel()` 必须带 `lease_owner == worker_id` 条件，防止租约失效的旧 Worker 覆盖新 Worker 结果。所有仓储方法自行开启短 Session 和事务。异常文本只保存经过上层清洗的摘要，不在仓储内保存 Provider 原始请求对象。

- [ ] **Step 4: 运行仓储测试**

Run: `cd backend && uv run pytest tests/persistence/test_repository.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/persistence backend/tests/persistence/test_repository.py
git commit -m "feat: persist research runs with sqlalchemy"
```

---

### Task 3: Redis Streams Broker

**Files:**
- Create: `backend/src/deeptrace/queue/__init__.py`
- Create: `backend/src/deeptrace/queue/protocol.py`
- Create: `backend/src/deeptrace/queue/redis_streams.py`
- Create: `backend/tests/queue/test_redis_streams.py`

**Interfaces:**
- Consumes: `JobMessage`, `StoredEvent`。
- Produces: `ResearchBroker` 协议。

```python
class ResearchBroker(Protocol):
    async def ensure_group(self) -> None: ...
    async def enqueue(self, run_id: str) -> str: ...
    async def read(self, *, block_ms: int = 5000) -> list[JobMessage]: ...
    async def reclaim_stale(self) -> list[JobMessage]: ...
    async def ack(self, message_id: str) -> None: ...
    async def publish_event(self, event: StoredEvent) -> None: ...
    def subscription(self, run_id: str) -> AsyncContextManager[AsyncIterator[int]]: ...
    async def request_cancel(self, run_id: str) -> None: ...
    async def is_cancel_requested(self, run_id: str) -> bool: ...
    async def clear_cancel(self, run_id: str) -> None: ...
    async def aclose(self) -> None: ...
```

- [ ] **Step 1: 写 Redis Broker 失败测试**

使用 `fakeredis.aioredis.FakeRedis(decode_responses=True)` 注入客户端：

```python
@pytest.mark.asyncio
async def test_enqueue_read_and_ack(fake_redis) -> None:
    broker = RedisResearchBroker(fake_redis, stream="jobs", group="workers", consumer="w1")
    await broker.ensure_group()
    message_id = await broker.enqueue("run-1")
    jobs = await broker.read(block_ms=1)
    assert jobs == [JobMessage(message_id=message_id, run_id="run-1")]
    await broker.ack(message_id)
    assert (await fake_redis.xpending("jobs", "workers"))["pending"] == 0


@pytest.mark.asyncio
async def test_cancel_marker_has_ttl(fake_redis) -> None:
    broker = RedisResearchBroker(fake_redis, cancel_ttl_seconds=60)
    await broker.request_cancel("run-1")
    assert await broker.is_cancel_requested("run-1") is True
    assert 0 < await fake_redis.ttl("deeptrace:research:cancel:run-1") <= 60
```

另测：重复 `ensure_group()`、事件频道只发布持久事件 ID、`subscription()` 退出时关闭 Pub/Sub、`reclaim_stale()` 使用 `XAUTOCLAIM` 返回遗留消息、`aclose()` 关闭 Redis 资源。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/queue/test_redis_streams.py -q`

Expected: FAIL，提示 `deeptrace.queue` 不存在。

- [ ] **Step 3: 实现 Redis Broker**

关键实现约束：

```python
async def enqueue(self, run_id: str) -> str:
    return await self._redis.xadd(self._stream, {"run_id": run_id})


async def publish_event(self, event: StoredEvent) -> None:
    await self._redis.publish(self._event_channel(event.run_id), str(event.id))


async def request_cancel(self, run_id: str) -> None:
    await self._redis.set(
        self._cancel_key(run_id), "1", ex=self._cancel_ttl_seconds
    )
```

`subscription()` 只产出数据库事件 ID，不把完整事件负载视为可靠消息，并通过异步上下文管理器确保订阅退出时执行 `unsubscribe()` 与 `pubsub.aclose()`。`read()` 和 `reclaim_stale()` 忽略缺少 `run_id` 的畸形消息并确认它们，避免毒消息永久阻塞队列。

- [ ] **Step 4: 运行 Broker 测试**

Run: `cd backend && uv run pytest tests/queue/test_redis_streams.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/queue backend/tests/queue/test_redis_streams.py
git commit -m "feat: add redis streams research broker"
```

---

### Task 4: 统一 Runtime 协议并迁移 Local 模式

**Files:**
- Create: `backend/src/deeptrace/runtime/protocol.py`
- Create: `backend/src/deeptrace/runtime/local.py`
- Create: `backend/tests/runtime/test_local.py`
- Modify: `backend/src/deeptrace/runtime/__init__.py`
- Modify: `backend/src/deeptrace/api.py`
- Modify: `backend/tests/api/test_api.py`

**Interfaces:**
- Consumes: `RunRecord`, `StoredEvent`，现有 `build_real_agent(settings, on_event, mode)`。
- Produces: `ResearchRuntime` 协议。

```python
class ResearchRuntime(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def create(self, question: str, mode: RunMode) -> RunRecord: ...
    async def list(self) -> list[RunRecord]: ...
    async def get(self, run_id: str) -> RunRecord | None: ...
    async def cancel(self, run_id: str) -> RunRecord | None: ...
    def events(self, run_id: str, after_event_id: int = 0) -> AsyncIterator[StoredEvent]: ...
```

- [ ] **Step 1: 写 Local Runtime 失败测试**

将现有 API 的 `FakeAgent` 复用或移入 fixture，增加：

```python
@pytest.mark.asyncio
async def test_local_runtime_executes_and_persists(tmp_path) -> None:
    runtime = LocalResearchRuntime(
        settings=object(), runs_dir=tmp_path, agent_factory=fake_agent_factory
    )
    await runtime.start()
    run = await runtime.create("研究问题", "basic")
    terminal = await wait_for_terminal(runtime, run.id)
    assert terminal.status == "completed"
    assert (tmp_path / f"{run.id}.json").exists()
    await runtime.stop()


@pytest.mark.asyncio
async def test_local_runtime_replays_then_streams_events(tmp_path) -> None:
    runtime = LocalResearchRuntime(object(), tmp_path, eventful_agent_factory)
    run = await runtime.create("问题", "basic")
    events = [item async for item in runtime.events(run.id)]
    assert [item.event_type for item in events] == ["planning.completed", "done"]
```

继续保留现有 API Local 模式测试，确保响应字段和 JSON 内容兼容。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/runtime/test_local.py tests/api/test_api.py -q`

Expected: FAIL，提示 `LocalResearchRuntime` 不存在。

- [ ] **Step 3: 提取 Local Runtime 并让 API 依赖协议**

把当前 `registry`、`_RunState`、`_execute()`、JSON `_persist()` 和 `_apply_result()` 从 `api.py` 移入 `runtime/local.py`。Local 事件分配进程内递增 ID，并将 `StoredEvent.payload` 保持为当前前端认识的 `RunEvent.model_dump()` 加 `ts`。

`create_app()` 增加可注入参数且保持旧调用有效：

```python
def create_app(
    settings: Settings | None = None,
    *,
    runs_dir: Path | str | None = None,
    runtime: ResearchRuntime | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_env()
    selected_runtime = runtime or LocalResearchRuntime(app_settings, runs_dir or "runs")
```

使用 FastAPI lifespan 调用 `runtime.start()` 和 `runtime.stop()`。本任务只迁移 Local 行为，不选择 Distributed Runtime。

- [ ] **Step 4: 运行 Local 与 API 回归测试**

Run: `cd backend && uv run pytest tests/runtime/test_local.py tests/api/test_api.py tests/multi_agent/test_entrypoints.py -q`

Expected: PASS，现有前端/API 合约不变。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/runtime backend/src/deeptrace/api.py backend/tests/runtime/test_local.py backend/tests/api/test_api.py
git commit -m "refactor: isolate local research runtime"
```

---

### Task 5: Distributed Runtime 的任务创建、查询与取消

**Files:**
- Create: `backend/src/deeptrace/runtime/distributed.py`
- Create: `backend/tests/runtime/test_distributed.py`
- Modify: `backend/src/deeptrace/runtime/__init__.py`

**Interfaces:**
- Consumes: `RunRepository`、`ResearchBroker`、`ResearchRuntime`。
- Produces: `DistributedResearchRuntime(repository, broker)`。
- Guarantee: `create()` 只保存并投递，不构建或执行 Agent。

- [ ] **Step 1: 写 Distributed Runtime 失败测试**

用内存 Fake Repository/Broker 精确验证调用顺序：

```python
@pytest.mark.asyncio
async def test_create_persists_before_enqueue() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls)
    broker = FakeBroker(calls)
    runtime = DistributedResearchRuntime(repository, broker, id_factory=lambda: "run-1")
    run = await runtime.create("问题", "deep")
    assert run.status == "pending"
    assert calls == ["repository.create:run-1", "broker.enqueue:run-1"]


@pytest.mark.asyncio
async def test_cancel_updates_database_and_broker() -> None:
    repository = FakeRepositoryWithRun(make_run("run-1"))
    broker = FakeBroker([])
    runtime = DistributedResearchRuntime(repository, broker)
    run = await runtime.cancel("run-1")
    assert run.status == "cancel_requested"
    assert broker.cancelled == ["run-1"]
```

另测 `start()` 创建 Consumer Group、`get/list` 委托 Repository、投递失败保留 pending 记录并抛出 `JobDispatchError`、终态取消不写 Redis。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/runtime/test_distributed.py -q`

Expected: FAIL，提示 `DistributedResearchRuntime` 不存在。

- [ ] **Step 3: 实现 Distributed Runtime**

`events()` 实现无遗漏切换：

```python
async def events(self, run_id: str, after_event_id: int = 0):
    cursor = after_event_id
    for event in await self._repository.events_after(run_id, cursor):
        cursor = event.id
        yield event
    async with self._broker.subscription(run_id) as notifications:
        for event in await self._repository.events_after(run_id, cursor):
            cursor = event.id
            yield event
        async for notified_id in notifications:
            for event in await self._repository.events_after(run_id, cursor):
                cursor = event.id
                yield event
            run = await self._repository.get(run_id)
            if run is not None and run.status in TERMINAL_STATUSES and cursor >= notified_id:
                break
```

`stop()` 关闭 Broker，不关闭由应用统一持有的数据库 Engine。

- [ ] **Step 4: 运行 Distributed Runtime 测试**

Run: `cd backend && uv run pytest tests/runtime/test_distributed.py tests/queue/test_redis_streams.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/runtime/distributed.py backend/src/deeptrace/runtime/__init__.py backend/src/deeptrace/queue/protocol.py backend/src/deeptrace/queue/redis_streams.py backend/tests/runtime/test_distributed.py backend/tests/queue/test_redis_streams.py
git commit -m "feat: add distributed research runtime"
```

---

### Task 6: 异步 Research Worker、幂等和重试

**Files:**
- Create: `backend/src/deeptrace/worker/__init__.py`
- Create: `backend/src/deeptrace/worker/service.py`
- Create: `backend/src/deeptrace/worker/__main__.py`
- Create: `backend/tests/worker/test_service.py`

**Interfaces:**
- Consumes: `RunRepository`、`ResearchBroker`、`build_real_agent`、`JobMessage`。
- Produces: `ResearchWorker.process(job: JobMessage) -> None`、`ResearchWorker.run_forever() -> None`。
- Produces: `build_worker(settings: Settings) -> ResearchWorker`。

- [ ] **Step 1: 写 Worker 失败测试**

```python
@pytest.mark.asyncio
async def test_worker_persists_events_and_result_before_ack() -> None:
    calls: list[str] = []
    repository = FakeRepository(calls, run=make_run("run-1"))
    broker = FakeBroker(calls)
    worker = ResearchWorker(
        repository, broker, object(), eventful_agent_factory, worker_id="worker-1"
    )
    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))
    assert calls == [
        "claim:run-1:worker-1",
        "append_event:planning.completed",
        "publish_event:planning.completed",
        "complete:run-1",
        "ack:1-0",
    ]


@pytest.mark.asyncio
async def test_worker_acks_duplicate_without_running_agent() -> None:
    repository = FakeRepository(claim_result=None)
    factory = Mock()
    broker = FakeBroker()
    worker = ResearchWorker(repository, broker, object(), factory, worker_id="worker-1")
    await worker.process(JobMessage(message_id="1-0", run_id="run-1"))
    factory.assert_not_called()
    assert broker.acked == ["1-0"]
```

另测：Agent 构造失败写入脱敏 `failed`；`complete()` 失败时不 ack；取消标记在执行前转为 `cancelled`；运行中出现取消标记会取消 Agent task 并写入 `cancelled`；租约续期失败会停止旧 Agent 且不确认消息；`CancelledError` 关闭 Agent；达到最大 attempt 后失败并 ack；`run_forever()` 启动时先处理 `reclaim_stale()`，再阻塞读取新消息。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/worker/test_service.py -q`

Expected: FAIL，提示 `deeptrace.worker` 不存在。

- [ ] **Step 3: 实现 Worker 与有序事件落库**

现有 Agent 的 `on_event` 是同步回调。Worker 用单个 `asyncio.Queue[RunEvent | None]` 和一个 drain task 保证顺序：

```python
def on_event(event: RunEvent) -> None:
    event_queue.put_nowait(event)


async def drain_events() -> None:
    while (event := await event_queue.get()) is not None:
        stored = await repository.append_event(run.id, event)
        await broker.publish_event(stored)
```

Agent 结束后先向事件队列放入 `None` 并等待 drain task，再写最终结果。任何事件落库失败都不得写成功终态或确认消息。

执行 Agent 时同时启动监视协程，每秒检查一次 `broker.is_cancel_requested(run.id)`，并以小于租约三分之一的间隔调用 `repository.renew_lease()`；取消命中或续租失败时取消研究 task。取消命中后等待 Agent 的 `finally/aclose()` 完成，再写入 `cancelled`；续租失败说明任务已被其他 Worker 接管，旧 Worker 不写终态也不确认消息。监视协程必须在正常完成和异常路径中取消并等待，避免泄漏后台任务。

异常信息统一清洗：

```python
safe_error = f"运行失败（{type(exc).__name__}），请检查服务与模型配置"
```

`run_forever()` 每轮最多处理配置允许的并发数；首期默认单 Worker 内串行消费，横向并发通过启动多个 Worker 进程获得，避免与 Multi-Agent 内部并发叠加导致资源失控。

- [ ] **Step 4: 运行 Worker 测试**

Run: `cd backend && uv run pytest tests/worker/test_service.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/worker backend/tests/worker/test_service.py
git commit -m "feat: execute research jobs in async worker"
```

---

### Task 7: API 模式选择、持久查询和可续传 SSE

**Files:**
- Modify: `backend/src/deeptrace/api.py`
- Create: `backend/tests/api/test_distributed_api.py`
- Modify: `backend/tests/api/test_api.py`

**Interfaces:**
- Consumes: `ResearchRuntime`、`LocalResearchRuntime`、`DistributedResearchRuntime`、Session factory、Repository、Redis Broker。
- Produces: 与现有前端兼容的 `/researches`、`/researches/{id}`、`/cancel`、`/events`。

- [ ] **Step 1: 写 Distributed API 失败测试**

注入 Fake Runtime，避免 API 单元测试连接真实中间件：

```python
def test_distributed_api_delegates_creation_without_agent(tmp_path) -> None:
    runtime = FakeRuntime(run=make_run("run-1"))
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        response = client.post(
            "/researches", json={"question": "研究问题", "mode": "multi_agent"}
        )
    assert response.json() == {"id": "run-1", "status": "pending"}
    assert runtime.created == [("研究问题", "multi_agent")]


def test_sse_uses_last_event_id_header() -> None:
    runtime = FakeRuntime(events=[make_event(8), make_event(9), make_done_event(10)])
    with TestClient(create_app(settings=object(), runtime=runtime)) as client:
        with client.stream(
            "GET", "/researches/run-1/events", headers={"Last-Event-ID": "7"}
        ) as response:
            body = "".join(response.iter_text())
    assert runtime.after_event_id == 7
    assert "id: 8\n" in body
    assert "event: done\n" in body
```

另测：不存在运行返回 404；取消返回 `cancel_requested`；事件 payload 继续保持前端所需 `event_type/message/details/ts`；Local 旧测试不变。

增加 `GET /health`，固定返回 `{"status": "ok"}`，供 Docker Compose 在 API 完成数据库迁移并开始监听后判断健康。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/api/test_distributed_api.py tests/api/test_api.py -q`

Expected: FAIL，SSE 尚未输出 `id`，API 尚未完整委托 Runtime。

- [ ] **Step 3: 精简 API 并增加生产 Runtime 工厂**

路由只负责 HTTP 转换：

```python
@app.post("/researches")
async def create_research(request: ResearchRequest) -> dict[str, Any]:
    run = await selected_runtime.create(request.question.strip(), request.mode)
    return {"id": run.id, "status": run.status}


@app.get("/researches/{run_id}/events")
async def stream_events(
    run_id: str,
    last_event_id: int = Header(0, alias="Last-Event-ID"),
) -> StreamingResponse:
    if await selected_runtime.get(run_id) is None:
        raise HTTPException(404, "运行不存在")

    async def generator():
        async for event in selected_runtime.events(run_id, last_event_id):
            if event.event_type == "done":
                yield f"id: {event.id}\nevent: done\ndata: {{}}\n\n"
                break
            data = json.dumps(event.payload, ensure_ascii=False)
            yield f"id: {event.id}\ndata: {data}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")
```

新增 `_build_runtime(settings, runs_dir)`：Local 返回 `LocalResearchRuntime`；Distributed 创建 Engine、Repository、Redis client 和 `DistributedResearchRuntime`，并将 Engine disposal 注册进 lifespan。禁止在 Distributed 分支调用 `build_real_agent`。

- [ ] **Step 4: 运行 API 与所有模式入口回归**

Run: `cd backend && uv run pytest tests/api tests/multi_agent/test_entrypoints.py -q`

Expected: PASS。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/src/deeptrace/api.py backend/tests/api/test_api.py backend/tests/api/test_distributed_api.py
git commit -m "feat: route api through configurable runtime"
```

---

### Task 8: Alembic、Docker Compose 与服务健康检查

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260907_01_create_research_runtime.py`
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `docker-compose.yml`
- Create: `.env.docker.example`
- Create: `backend/tests/deployment/test_compose_config.py`
- Modify: `backend/src/deeptrace/worker/__main__.py`

**Interfaces:**
- Consumes: SQLAlchemy `Base.metadata`、`build_worker(settings)`、FastAPI `deeptrace.api:app`。
- Produces: MySQL 8、Redis 7、API、Worker 四服务本地部署。

- [ ] **Step 1: 写部署文件失败测试**

```python
from pathlib import Path
import yaml


def test_compose_declares_required_services_and_health_dependencies() -> None:
    compose = yaml.safe_load(Path("../docker-compose.yml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"mysql", "redis", "api", "worker"}
    assert compose["services"]["api"]["environment"]["DEEPTRACE_RUNTIME_MODE"] == "distributed"
    assert compose["services"]["api"]["depends_on"]["mysql"]["condition"] == "service_healthy"
    assert compose["services"]["worker"]["command"] == ["python", "-m", "deeptrace.worker"]


def test_migration_contains_both_runtime_tables() -> None:
    migration = Path("alembic/versions/20260907_01_create_research_runtime.py").read_text(encoding="utf-8")
    assert 'op.create_table("research_runs"' in migration
    assert 'op.create_table("run_events"' in migration
    assert 'op.create_index("ix_run_events_run_id_id"' in migration
```

将 `pyyaml>=6` 加入 dev dependency，以解析 Compose 测试。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/deployment/test_compose_config.py -q`

Expected: FAIL，部署文件尚不存在。

- [ ] **Step 3: 实现迁移和容器编排**

迁移必须创建设计中的两张表、运行创建时间索引和 `(run_id, id)` 事件复合索引，`downgrade()` 以相反顺序删除。

Docker Compose 核心配置：

```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_DATABASE: researchpilot
      MYSQL_USER: researchpilot
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:-researchpilot}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root-local-only}
    healthcheck:
      test: ["CMD-SHELL", "mysqladmin ping -h localhost -uroot -p$$MYSQL_ROOT_PASSWORD"]
      interval: 5s
      timeout: 3s
      retries: 20
  redis:
    image: redis:7.4-alpine
    command: ["redis-server", "--appendonly", "yes"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
  api:
    build: ./backend
    command: ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn deeptrace.api:app --host 0.0.0.0 --port 8000"]
  worker:
    build: ./backend
    command: ["python", "-m", "deeptrace.worker"]
```

API、Worker 都设置 Distributed 环境、MySQL DSN 和 Redis URL。API 增加访问 `/health` 的容器健康检查；Worker 除等待 MySQL、Redis 健康外，还等待 API 健康，从而确保 Alembic 迁移已完成后再查询队列表。两者挂载只读 BGE 模型目录：`${DEEPTRACE_EMBEDDING_MODEL_HOST_PATH}:/models/bge-m3:ro`，并设置容器内模型路径。`.env.docker.example` 解释 Windows 路径写法和必须提供的 OpenAI/Tavily 配置。

Dockerfile 使用 Python 3.12 slim、锁文件安装和非 root 用户；安装 Playwright Chromium 及其系统依赖。API 暴露 8000 端口，MySQL 和 Redis 不映射宿主端口，除非本地调试显式覆盖。

- [ ] **Step 4: 验证静态配置与 Compose 解析**

Run: `cd backend && uv add --dev "pyyaml>=6" && uv run pytest tests/deployment/test_compose_config.py -q`

Run: `docker compose --env-file .env.docker.example config --quiet`

Expected: pytest PASS，Compose 配置解析成功。若示例凭据无法用于真实 Agent，只运行 `config --quiet`，不得发起外部模型调用。

- [ ] **Step 5: 提交本任务**

```powershell
git add -- backend/pyproject.toml backend/uv.lock backend/alembic.ini backend/alembic backend/Dockerfile backend/.dockerignore backend/src/deeptrace/worker/__main__.py backend/tests/deployment/test_compose_config.py docker-compose.yml .env.docker.example
git commit -m "feat: add mysql redis compose deployment"
```

---

### Task 9: 恢复扫描、集成冒烟与项目文档

**Files:**
- Create: `backend/tests/integration/test_distributed_runtime.py`
- Modify: `backend/src/deeptrace/worker/service.py`
- Modify: `backend/tests/worker/test_service.py`
- Modify: `README.md`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes: 完整 Distributed Runtime、Repository、Broker、Worker。
- Produces: `ResearchWorker.recover_stale()`，以及可复现的启动和验证说明。

- [ ] **Step 1: 写 pending 恢复与端到端失败测试**

```python
@pytest.mark.asyncio
async def test_recover_stale_requeues_unclaimed_or_expired_runs() -> None:
    repository = FakeRepository(
        recoverable=[make_run("run-1"), make_expired_running_run("run-2")]
    )
    broker = FakeBroker()
    worker = ResearchWorker(
        repository, broker, object(), fake_agent_factory, worker_id="worker-1"
    )
    await worker.recover_stale(older_than_seconds=60)
    assert broker.enqueued == ["run-1", "run-2"]
```

`test_distributed_runtime.py` 使用 SQLite Repository、Fake Redis 和 Fake Agent 串起：API 创建 → Worker 消费 → 事件落库 → 最终结果查询 → SSE 从指定事件 ID 补发。测试不得调用外部网络或真实模型。

- [ ] **Step 2: 运行测试确认红灯**

Run: `cd backend && uv run pytest tests/worker/test_service.py tests/integration/test_distributed_runtime.py -q`

Expected: FAIL，`recover_stale()` 或 Repository 的可恢复运行扫描接口不存在。

- [ ] **Step 3: 实现有限恢复扫描并补齐文档**

在 `RunRepository` 增加精确接口：

```python
async def recoverable_before(self, cutoff: datetime, limit: int = 100) -> list[RunRecord]: ...
```

Worker 启动时先 `ensure_group()`、领取 Redis pending entries，再扫描数据库中长期未投递的 `pending` 运行，以及 `lease_expires_at < now` 的 `running` 运行并重新投递。扫描每次最多 100 条；重新领取时由数据库条件更新生成新租约，旧 Worker 因续租失败不能覆盖结果。重复消息可以安全确认，后续恢复以 MySQL 的 pending 状态或过期租约为准。

README 必须分别给出：

```powershell
# Local 模式
cd backend
uv run python -m deeptrace.api

# Distributed 模式
Copy-Item .env.docker.example .env.docker
docker compose --env-file .env.docker up --build
```

并说明：运行 `docker compose exec mysql mysql ...` 查看 `research_runs`；使用 `docker compose exec redis redis-cli XLEN deeptrace:research:jobs` 查看队列；停止命令为 `docker compose down`，只有用户明确需要清空数据时才使用 `docker compose down -v`。

- [ ] **Step 4: 运行完整自动化验证**

Run: `cd backend && uv run pytest -m "not real" -q`

Expected: 全部非真实服务测试 PASS，数量不低于改造前的 210 个测试加本计划新增测试。

Run: `cd backend && uv run python -m compileall -q src`

Expected: 退出码 0。

Run: `docker compose --env-file .env.docker config --quiet`

Expected: 退出码 0。

若本机 Docker 正在运行且 `.env.docker` 已提供真实本地配置，再运行：

```powershell
docker compose --env-file .env.docker up -d mysql redis
docker compose --env-file .env.docker run --rm api uv run alembic upgrade head
docker compose --env-file .env.docker ps
```

Expected: MySQL 与 Redis 为 healthy，迁移成功。不得在没有用户真实 API 配置时启动研究任务。

- [ ] **Step 5: 检查变更没有混入无关文件**

Run: `git status --short`

Expected: 仅显示本任务的 README、Worker、Repository/协议及测试改动，或明确属于用户的既有脏文件；提交时只逐项列出本任务文件。

- [ ] **Step 6: 提交本任务**

```powershell
git add -- README.md backend/README.md backend/src/deeptrace/persistence/repository.py backend/src/deeptrace/worker/service.py backend/tests/persistence/test_repository.py backend/tests/worker/test_service.py backend/tests/integration/test_distributed_runtime.py
git commit -m "feat: recover and document distributed research runtime"
```

---

## Final Review Gate

- [ ] 对照设计文档逐项确认：双模式、MySQL 权威存储、Redis Stream、Pub/Sub、取消、幂等、有限重试、SSE 补发、Docker Compose 均有测试或验证记录。
- [ ] 运行 `git diff --check HEAD~9..HEAD`，确认没有空白错误。
- [ ] 运行 `cd backend && uv run pytest -m "not real" -q`，记录最终测试数量。
- [ ] 使用 `git log --oneline -9` 检查九个提交边界清晰。
- [ ] 不把未经压测的吞吐量、可用性或成本下降比例写入 README 或简历。
- [ ] 实现验证完成后，再更新 `docs/resume/researchpilot-project-experience.md`，加入已经真实落地的 MySQL/Redis/API-Worker 能力。
