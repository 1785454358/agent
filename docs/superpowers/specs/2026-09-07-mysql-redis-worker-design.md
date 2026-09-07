# ResearchPilot MySQL、Redis 与异步 Worker 设计

## 1. 背景与目标

ResearchPilot 当前由 FastAPI 进程直接创建并执行研究任务，运行态保存在进程内字典和 `asyncio.Queue` 中，最终记录写入本地 JSON 文件。这种实现适合快速开发，但存在以下边界：

- API 生命周期与长时间运行的 Agent 任务绑定，API 重启会丢失内存中的任务状态与实时事件。
- 单进程内的任务无法由独立 Worker 消费，不便于隔离 Web 请求与推理负载。
- JSON 文件不适合并发查询、状态更新和运行历史管理。
- SSE 依赖进程内队列，无法跨 API 实例或 Worker 进程传递事件。

本次改造目标是在不破坏现有轻量开发方式的前提下，新增一个可通过 Docker Compose 启动的基础设施模式：

- MySQL 作为研究运行、最终结果及事件历史的权威存储。
- Redis Streams 作为异步研究任务队列，Redis Pub/Sub 作为低延迟实时事件通道。
- FastAPI 与异步 Research Worker 解耦。
- 支持任务恢复、有限重试、取消控制、重复投递幂等和 SSE 断线续传。
- Basic、Deep、Multi-Agent 三种研究策略保持不变，由 Worker 继续通过现有统一构建入口调用。

本次实现不以生产级分布式高可用为目标，不在首期引入 Kubernetes、任务优先级、跨机器自动扩缩容或完整的搜索结果分布式缓存。

## 2. 总体架构

系统保留两种运行模式：

### 2.1 Local 模式

- 保留现有进程内任务执行、内存状态、`asyncio.Queue` 和 JSON 记录机制。
- 无需 MySQL、Redis 或 Worker 即可启动。
- 用于快速开发、单元测试和轻量演示。

### 2.2 Distributed 模式

```text
Web Client
    | HTTP / SSE
    v
FastAPI API
    |-- MySQL: run metadata, results and durable events
    |-- Redis Stream: research jobs
    `-- Redis Pub/Sub: live event subscription
                         |
                         v
                Async Research Worker
                    |-- Basic
                    |-- Deep
                    `-- Multi-Agent
```

通过配置项切换模式，建议使用：

```text
DEEPTRACE_RUNTIME_MODE=local|distributed
```

默认值为 `local`，从而保持现有启动方式、测试和前端协议兼容。`distributed` 模式要求 MySQL、Redis 和 Worker 可用，并采用数据库及消息队列实现运行生命周期。

## 3. 组件职责

### 3.1 FastAPI API

- 校验创建研究任务的请求。
- 在 MySQL 中创建 `pending` 运行记录。
- 将只包含运行标识和必要追踪信息的消息投递到 Redis Stream。
- 从 MySQL 查询运行列表、运行详情和最终结果。
- 接收取消请求，并设置持久状态与 Redis 取消标记。
- SSE 建连时先从 MySQL 补发历史事件，再订阅 Redis 实时事件。
- Local 模式继续沿用现有进程内执行路径。

API 不在 Distributed 模式内直接执行 Agent，以避免 Web 进程和长任务共享生命周期。

### 3.2 Research Worker

- 使用 Redis Consumer Group 消费研究任务。
- 通过 MySQL 原子状态更新领取任务，阻止重复消息导致重复执行。
- 按运行记录中的模式构建 Basic、Deep 或 Multi-Agent Agent。
- 将研究事件先持久化到 MySQL，再发布到 Redis 实时通道。
- 在现有安全边界检查取消标记，收到取消后正常收尾。
- 成功或失败后更新最终状态、报告、来源、缺口、用量和错误信息。
- 只有在最终状态已成功写入 MySQL 后才确认 Redis Stream 消息。

### 3.3 MySQL

MySQL 是 Distributed 模式的权威状态来源。首期只建立两张核心表，避免把 Agent 的短生命周期内部对象过度关系化。

#### `research_runs`

建议字段：

- `id`：字符串运行 ID，主键。
- `query`：用户研究问题。
- `mode`：`basic`、`deep` 或 `multi_agent`。
- `status`：`pending`、`running`、`completed`、`partial`、`failed`、`cancel_requested`、`cancelled`。
- `request_payload`：创建请求的 JSON 快照。
- `report`：最终报告正文。
- `sources`：来源列表 JSON。
- `unresolved_gaps`：未解决问题 JSON。
- `usage`：Token、耗时等统计 JSON。
- `error`：失败摘要或空值。
- `attempt_count`：Worker 执行次数。
- `version`：乐观锁版本。
- `created_at`、`started_at`、`finished_at`、`updated_at`。

#### `run_events`

建议字段：

- `id`：单调递增事件 ID，主键，同时作为 SSE `id`。
- `run_id`：关联研究运行并建立索引。
- `event_type`：例如 `planning.started`、`tool.completed`、`run.completed`。
- `payload`：完整结构化事件 JSON。
- `created_at`：事件时间。

研究计划、研究员任务和工具调用继续作为事件载荷保存。只有出现明确的独立查询需求后，才考虑拆分为额外业务表。

### 3.4 Redis

Redis 仅承担易失但需要低延迟或跨进程协调的职责，不作为最终运行记录的权威存储。

建议键空间：

```text
deeptrace:research:jobs
deeptrace:research:events:{run_id}
deeptrace:research:cancel:{run_id}
```

- `deeptrace:research:jobs`：Redis Stream 任务队列。
- Consumer Group：由 Worker 实例共同消费并维护 pending entries。
- `deeptrace:research:events:{run_id}`：Pub/Sub 实时事件频道。
- `deeptrace:research:cancel:{run_id}`：带 TTL 的取消标记。

首期不将 Redis 用作跨任务网页缓存。当前研究链路已经存在单次运行内的去重与复用逻辑，分布式缓存需要额外设计缓存键、内容版本、TTL 和时效性策略，留待后续优化。

## 4. 核心运行流程

### 4.1 创建与执行

1. API 在一个数据库事务中创建 `pending` 运行记录。
2. 事务提交后，API 将运行 ID 投递至 Redis Stream。
3. Worker 读取消息，通过条件更新把 `pending` 或允许恢复的状态改为 `running`。
4. 条件更新失败表示任务已被其他 Worker 领取或已处于终态，当前 Worker 直接确认重复消息。
5. Worker 执行现有研究 Agent，并处理其事件回调。
6. 每个事件写入 `run_events` 后发布至对应 Redis 频道。
7. Agent 结束后，Worker 将最终结果写入 `research_runs`。
8. 数据库提交成功后，Worker 确认 Redis Stream 消息。

### 4.2 SSE 历史补发与实时推送

1. 客户端连接 SSE，可携带 `Last-Event-ID`。
2. API 查询 `run_events.id > Last-Event-ID` 的历史事件并依次发送。
3. API 订阅当前运行的 Redis Pub/Sub 频道。
4. 为避免“查完历史、尚未订阅”窗口内遗漏事件，订阅建立后再次查询一次数据库增量，再进入实时转发。
5. Pub/Sub 消息只负责唤醒和低延迟传递；如发现事件 ID 跳跃，以 MySQL 补查为准。
6. 运行进入终态后，API 发送最终事件并关闭或允许客户端关闭连接。

### 4.3 取消

1. API 将可取消运行更新为 `cancel_requested`。
2. API 写入带 TTL 的 Redis 取消标记。
3. Worker 在研究轮次、工具调用或阶段切换等现有安全检查点检查取消状态。
4. Worker 停止后写入 `cancelled` 及最后统计信息。
5. 对仍处于 `pending` 且未领取的任务，Worker 消费时直接识别取消状态并结束，不启动 Agent。

## 5. 一致性、幂等与故障处理

系统采用 Redis Streams 的“至少一次”投递语义，不宣称严格的“恰好一次”。业务层通过运行 ID 和条件状态更新实现幂等。

### 5.1 重复投递

- `research_runs.id` 唯一。
- Worker 领取时使用带状态与版本条件的原子更新。
- 已运行、已取消或已完成的重复消息不会再次启动 Agent。

### 5.2 Worker 异常退出

- 未确认消息保留在 Consumer Group 的 pending entries 中。
- Worker 启动后可领取超过可见性超时的遗留消息。
- `attempt_count` 达到配置上限后不再自动执行，将运行标记为 `failed` 并记录原因。
- 首期恢复采用整次研究任务重试，不尝试恢复 LangGraph 中间节点；后续可通过 LangGraph Checkpointer 改进。

### 5.3 数据库与 Redis 双写窗口

创建任务涉及 MySQL 提交与 Redis 投递两个系统，首期采用可修复的一致性方案：

- MySQL 先保存 `pending` 记录，再投递 Redis。
- 投递失败时 API 返回明确错误，并保留可重投的 `pending` 记录。
- Worker 或独立恢复扫描可重新投递长期处于 `pending` 且无活跃任务的运行。

不在首期实现完整 Transactional Outbox，但 Repository 和 Queue 接口需为后续引入 Outbox 留出边界。

### 5.4 Redis Pub/Sub 丢失

Pub/Sub 不保证离线消息。所有事件先写 MySQL，SSE 可通过事件 ID 从数据库补发，因此 Redis 实时消息丢失不会造成历史缺失。

## 6. 代码边界

建议新增独立基础设施层，避免 MySQL 或 Redis 客户端渗入 Agent 策略代码：

```text
backend/src/deeptrace/
├── persistence/
│   ├── models.py
│   ├── repositories.py
│   └── database.py
├── queue/
│   ├── protocol.py
│   └── redis_streams.py
├── runtime/
│   ├── local.py
│   └── distributed.py
└── worker/
    ├── service.py
    └── __main__.py
```

具体原则：

- Agent 继续通过已有事件回调输出，不直接依赖 SQLAlchemy 或 Redis。
- API 依赖运行服务接口，不在路由函数中编写消息队列细节。
- Repository 和 Queue 使用协议接口，单元测试使用内存替身。
- 数据库迁移由 Alembic 管理。
- MySQL 使用 SQLAlchemy 2.x 异步接口和异步 MySQL 驱动。
- Redis 使用支持 asyncio 的官方 Python 客户端。

## 7. 配置与部署

Distributed 模式新增配置：

- 运行模式。
- MySQL DSN、连接池大小和连接超时。
- Redis URL、Stream 名、Consumer Group 和 Consumer 名。
- pending 消息领取超时、最大执行次数和取消标记 TTL。

Docker Compose 提供：

- `mysql`：持久化卷和健康检查。
- `redis`：持久化配置和健康检查。
- `api`：等待依赖健康后启动 FastAPI。
- `worker`：与 API 使用同一镜像，通过不同入口启动。

敏感配置只通过环境变量传入，示例值写入 `.env.example`，真实凭据不进入 Git。

## 8. 测试与验收

实现遵循测试驱动开发，至少覆盖：

### 8.1 单元测试

- MySQL Repository 的创建、条件领取、终态更新和事件分页。
- Redis Queue 的投递、消费、确认、遗留消息领取和取消标记。
- Distributed Runtime 的创建、查询、取消与重复投递。
- Worker 的成功、失败、重试耗尽和重复消息处理。

### 8.2 API 测试

- Distributed 模式创建任务后只投递、不在 API 进程执行。
- 列表和详情从 Repository 读取。
- SSE 能补发历史事件并继续接收实时事件。
- `Last-Event-ID` 不产生重复或遗漏。
- Local 模式现有行为全部回归通过。

### 8.3 集成与冒烟测试

- Docker Compose 四个服务健康启动。
- 创建 Basic、Deep 或 Multi-Agent 任务后由 Worker 完成。
- 重启 API 不影响 Worker 中的任务。
- Worker 在消息确认前退出，重启后能够重新领取任务。
- 前端能够持续显示研究事件并读取最终报告。

## 9. 简历表述边界

完成并验证本设计后，可表述为：

> 基于 MySQL 与 Redis Streams 构建研究任务持久化和异步调度机制，完成 API/Worker 解耦，支持任务恢复、失败重试、取消控制及 SSE 实时事件推送；通过 Docker Compose 实现本地一键部署。

不应在仅完成本地 Compose 的情况下宣称生产级高可用、海量并发或大规模分布式部署。后续若实现 Transactional Outbox、LangGraph Checkpointer、跨任务检索缓存和多 Worker 压测，再补充对应能力与量化数据。

## 10. 非目标与后续演进

首期非目标：

- 替换或修改 Basic、Deep、Multi-Agent 的研究策略。
- 将 Agent 内部所有状态拆为关系表。
- 引入 Celery、Kafka 或 Kubernetes。
- 生产级跨区域容灾。
- 未验证的性能数据或成本收益声明。

后续演进方向：

- Transactional Outbox，消除数据库提交后消息投递失败的人工恢复窗口。
- LangGraph Checkpointer，实现节点级中断恢复。
- Redis 搜索与抓取缓存，结合内容时效和查询归一化降低重复调用成本。
- 多 Worker 并发压测、队列积压指标、告警和管理界面。
