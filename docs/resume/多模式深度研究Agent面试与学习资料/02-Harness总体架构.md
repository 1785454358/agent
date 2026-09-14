# Harness 总体架构

这一篇用六张图串起公共运行协议、请求流程、数据所有权、三种策略、工具调用和故障恢复。

## Harness 总体架构图

这张图回答三种策略不同，为什么仍然属于一个系统。

```mermaid
flowchart TB
    U[用户或前端] --> API[FastAPI]
    API --> RT{运行模式}
    RT -->|本地| LR[Local Runtime]
    RT -->|分布式| DR[Distributed Runtime]
    DR --> RS[Redis Streams]
    RS --> WK[Worker]
    LR --> APP[Application Service]
    WK --> APP

    subgraph H[Agent Harness 治理层]
        APP --> TG[顶层 LangGraph]
        TG --> CTX[上下文与意图路由]
        CTX --> SR[研究策略注册与路由]
        SR --> WF[Workflow 子图]
        SR --> PE[Plan-and-Execute 子图]
        SR --> MA[Multi-Agent 子图]
        WF --> TOPIC[共用 Topic 子图]
        PE --> TOPIC
        MA --> TOPIC
        TOPIC --> TOOL[Tool Gateway]
        TG --> RESP[Answer Brief Report 响应子图]
        TG --> MEM[Memory 策略]
    end

    TOOL --> PROVIDER[搜索与抓取 Provider]
    TOOL --> EVIDENCE[Evidence Store]
    TG --> CP[Checkpoint]
    TOOL --> LEDGER[工具执行账本]
    TG --> EVENT[事件与指标]
    CP --> MYSQL[(MySQL 分布式)]
    EVIDENCE --> MYSQL
    LEDGER --> MYSQL
    MEM --> MYSQL
    MEM --> CHROMA[(Chroma 语义索引)]
    CHROMA --> BGE[本地 BGE-M3]
    CP -.本地模式.-> SQLITE[(SQLite)]
    EVIDENCE -.本地模式.-> SQLITE
```

讲图时从中间开始。顶层图管理公共生命周期，策略子图决定怎样研究，Gateway 管理外部调用，存储层管理可恢复事实。本地模式的 Checkpoint 和 Evidence 使用 SQLite，工具账本与长期记忆只在进程内保存，Chroma 可以使用本地持久目录。分布式模式把权威记录放入 MySQL，Chroma 只保存由 BGE-M3 生成的长期记忆语义索引。

## 单次请求时序图

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as FastAPI
    participant R as Runtime 或 Worker
    participant S as Application Service
    participant G as 顶层 LangGraph
    participant M as Memory
    participant P as 研究策略子图
    participant T as Topic 与 Tool Gateway
    participant E as Evidence Store
    participant W as 响应子图

    C->>A: question mode thread_id
    A->>R: create research
    R->>S: ApplicationResearchRequest
    S->>S: 校验身份并读取 Checkpoint
    S->>G: 新建 Turn 或恢复未完成运行
    G->>G: 初始化 管理上下文 识别意图
    G->>M: 按意图召回长期记忆
    M->>M: MySQL 过滤候选 Chroma TopK MySQL 回查
    alt 需要研究
        G->>P: ResearchInput
        P->>T: 搜索与抓取
        T->>E: 保存正文
        E-->>T: Evidence ID
        T-->>P: 受限预览与 Evidence ID
        P-->>G: ResearchOutcome
        G->>M: 保存有来源的事实
    else 使用已有上下文
        G->>G: 保留已有 Evidence 引用
    end
    G->>W: ResponseInput
    W->>E: 按 ID 读取受控正文
    W->>W: 生成并校验引用
    W-->>G: ResponseOutcome
    G-->>S: 完成本轮并写 Checkpoint
    S-->>R: 最终结果
    R-->>A: 状态和事件
    A-->>C: Answer Brief 或 Report
```

## State、Memory 与 Evidence 所有权图

```mermaid
flowchart LR
    D{数据的主要用途} -->|影响路由且需恢复| ST[LangGraph State]
    D -->|节点运行依赖| RC[Runtime Context]
    D -->|跨会话复用| LM[Long-term Memory Store]
    D -->|大体积原文| ES[Evidence Store]

    ST --> ST1[ConversationState]
    ST --> ST2[TurnState]
    ST1 --> A1[近期消息 结构化摘要]
    ST1 --> A2[Finding Evidence ID 未解决缺口]
    ST2 --> A3[意图 模式 本轮输入输出 状态]
    RC --> B1[ModelGateway Tool Gateway]
    RC --> B2[Store EventSink Clock]
    LM --> C1[MySQL 权威 Preference]
    LM --> C2[MySQL 权威 Fact]
    LM --> C3[Chroma content embedding memory_id]
    ES --> E1[正文 分块 哈希 版本 来源]
    ES -.Evidence ID.-> ST
    ES -.Evidence ID.-> LM
```

- 继续执行必须知道的业务事实进入 State。
- 客户端、连接、Gateway 和时钟进入 Runtime Context。
- 体积大、生命周期独立的内容进入专用 Store，State 只留引用。

## 三种研究策略子图

```mermaid
flowchart TB
    IN[统一 ResearchInput]

    subgraph W[Workflow]
        W1[plan_queries] --> W2[Send 并发 research_topic]
        W2 --> W3[evaluate]
        W3 --> W4[finalize]
    end
    subgraph P[Plan-and-Execute]
        P1[plan] --> P2[select_task]
        P2 -->|有任务| P3[execute_task]
        P3 --> P2
        P2 -->|任务完成| P4[evaluate]
        P4 -->|需要补查且未超限| P5[replan]
        P5 --> P2
        P4 -->|完成或受阻| P6[finalize]
    end
    subgraph M[Multi-Agent]
        M1[supervisor_plan] --> M2[Send 并发 researcher]
        M2 --> M3[aggregate]
        M3 --> M4[supervisor_evaluate]
        M4 -->|需要补查且未超限| M5[follow_up]
        M5 --> M2
        M4 -->|完成或到达边界| M6[finalize]
    end

    IN --> W1
    IN --> P1
    IN --> M1
    W2 -.复用.-> T[Topic 子图]
    P3 -.复用.-> T
    M2 -.复用.-> T
    W4 --> OUT[统一 ResearchOutcome]
    P6 --> OUT
    M6 --> OUT
```

| 策略 | 决策方式 | 并发方式 | 适用问题 | 主要成本 |
| --- | --- | --- | --- | --- |
| Workflow | 一次生成查询，固定向前执行 | 查询和页面抓取并行 | 边界清晰、快速覆盖 | 灵活性较低 |
| Plan-and-Execute | 执行后评估并有界重规划 | 当前按任务顺序，任务内抓取并行 | 多步骤、资料缺口补全 | 调用次数与时延更高 |
| Multi-Agent | Supervisor 拆分和评估 | 多个 Researcher 并行 | 多方向独立覆盖 | 协调和重复研究成本更高 |

当前 Plan-and-Execute 使用查询列表逐项执行，并未实现依赖 DAG。Multi-Agent 的 Researcher 复用受控 Topic 子图，自主范围受到图和工具权限约束。这些边界在面试中要说准确。

## Tool Gateway 执行管道

```mermaid
flowchart LR
    R[ToolRequest 与 ToolCaller] --> A[解析工具和调用权限]
    A --> B[参数模型校验]
    B --> C[URL 来源与安全校验]
    C --> D[执行账本 claim]
    D -->|已完成| RP[Replay]
    D -->|已有执行者| FL[等待 Follower 结果]
    D -->|取得所有权| E[原子预留层级预算]
    E -->|不足| X[budget_exhausted]
    E --> F[缓存与 Singleflight]
    F --> G[Provider 超时执行]
    G --> H[结果规范化]
    H --> I{产生正文}
    I -->|是| J[Evidence Store 入库]
    I -->|否| K[ToolResult]
    J --> K
    K --> L[提交或释放预算]
    L --> N[完成执行账本]
    N --> O[记录受控事件]
```

| 机制 | 解决的问题 |
| --- | --- |
| Cache | 相同输入的数据能否复用 |
| Singleflight | 同一时刻的相同请求能否只访问一次 Provider |
| Execution Ledger | 同一个逻辑 `call_id` 是否已经完成，恢复后能否 Replay |

Gateway 先校验再占预算，因为无权限、参数错误或 URL 不安全的请求不应消耗额度。校验通过后必须先预留预算，再执行并发调用，否则多个 Researcher 可能一起穿透上限。

## 崩溃恢复时间线

```mermaid
sequenceDiagram
    participant W1 as Worker A
    participant C as Checkpoint
    participant L as Tool Ledger
    participant P as Provider
    participant Q as Redis Streams
    participant W2 as Worker B

    W1->>C: 保存节点 N 前状态
    W1->>L: claim call_id
    W1->>P: 外部调用
    P-->>W1: 返回成功
    W1->>L: 写 ToolResult 与消耗
    W1--xC: 下个 Checkpoint 前崩溃
    Q->>W2: 重投或回收任务
    W2->>C: 恢复到节点 N
    W2->>L: 相同 call_id claim
    L-->>W2: Replay 已提交结果
    W2->>L: 汇总历史消耗
    L-->>W2: 重建 Run Mode Agent 预算
    W2->>C: 继续并保存状态
    W2->>Q: 最终持久化后 ACK
```

Checkpoint 保存图状态和下一执行位置。执行账本保存工具调用的逻辑身份、所有权、结果和预算消耗。两者共同使用才能支持外部调用节点的可靠重放。

Provider 已成功但 Worker 在账本提交前崩溃时，恢复后仍可能再次调用。搜索和抓取属于读操作，重复一般可接受。支付、发信等写操作还需要 Provider 幂等键、事务发件箱或补偿机制。

[返回阅读目录](00-阅读目录.md)
