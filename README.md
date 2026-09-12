# ResearchPilot

面向复杂问题的自主研究 Agent，支持快速工作流、Plan-and-Execute 和 Supervisor Multi-Agent 协作研究。
原项目名 DeepTrace；Python 包 `deeptrace`、旧命令与 `DEEPTRACE_*` 配置继续兼容。

## 三种研究模式

| 模式 | 流程 | 用途 |
| --- | --- | --- |
| Basic | 一次规划 → 并行搜索抓取 → 原文筛选 → Writer | 快速的一轮研究；策略参考 GPT-Researcher |
| Deep | 制定计划 → ReAct 工具执行 → 反馈重规划 → Writer | 多步骤研究、资料缺口补全与失败调整 |
| Multi-Agent | LangGraph Plan → 并行 ReAct Researcher → Supervisor Replan → Writer | 多方向并行覆盖、定向补查与独立失败隔离 |

Multi-Agent 的顶层控制流由 LangGraph 显式编译为
`Plan → Execute → Replan →（必要时再次 Execute）→ Writer`。默认首批最多派发
3 个任务并同时执行。每个 Researcher 只有两次研究工具决策和一次强制收尾决策，
单次决策最多执行一个研究工具。只要仍有具体缺口、研究员名额、至少两次网络额度
和后续主管轮次，任何仍带有未解决叶子缺口的结束建议都会被拒绝并转为定向补查。
当任务表已经无缺口，或研究员、网络额度、主管轮次形成硬终止边界时，系统直接
进入 Writer，不再调用一次无法改变结果的 Supervisor。可行动阶段的无效结构修复
和确定性缺口补查仍然保留。补查以一个具体叶子缺口生成一个 Researcher 任务，
子任务只覆盖它实际承接的父缺口。每次研究工具调用都必须声明对应的检查项；
初始任务可围绕该项建立资料基础，补查任务则直接检索具体缺口，不重新宽搜主题。
无效检查项会在网络请求和额度扣减前被拒绝。

Deep 的 Planner 生成目标、完成条件与依赖；Executor 根据实际工具结果决定
搜索、阅读网页、检索历史资料或结束任务。任务受阻、产生缺口或计划执行结束
时触发重规划，调整剩余任务。第一版按依赖顺序执行任务，单轮独立工具可并行。

工作记忆包含任务进度、已读原文及查询记录。可选长期记忆支持 BGE-M3
语义检索历史页面、时效过滤与主动重新抓取；并非只按相同 URL 命中缓存。
研究过程只以循环次数和工具调用次数限制执行；耗时与 Token 只作统计。
达到研究次数上限后仍正常调用 Writer。单次请求保留故障超时。
报告采用数字层级标题和按正文首次出现排序的引用。中文报告包含开头总述、带承接
内容的主题分析、必要时的研究局限和正文末尾的综合结论；URL 统一放在“参考内容”。
该调整仍使用一次 Writer 调用，没有增加 Critic 或润色 Agent。

## 本地模式

```powershell
cd backend
# 复制 .env.example 为 .env，并配置兼容原生 tools/tool_calls 的模型、Tavily 与本地 BGE-M3
uv sync
uv run playwright install chromium
uv run python -m deeptrace.api
```

打开 http://127.0.0.1:8000，在模式选择中切换 Basic / Deep / Multi-Agent。

本地模式沿用进程内异步任务和 `runs/*.json`，无需安装 MySQL、Redis 或 Worker。

## 分布式模式

```powershell
Copy-Item .env.docker.example .env.docker
# 填写模型、Tavily 和 BGE-M3 的宿主机路径后启动
docker compose --env-file .env.docker up --build
```

分布式模式把 API 与研究执行分开。API 将运行记录写入 MySQL，再把任务投递到
Redis Stream。独立 Worker 消费任务，持续保存研究事件和最终报告。MySQL 保存
权威状态，Redis 负责任务投递、取消信号和 SSE 实时唤醒。Worker 使用租约、条件
更新和有限重试处理重复投递，浏览器断线后可通过事件 ID 补收进度。

下面两条命令可分别查看运行记录与队列长度。

```powershell
docker compose --env-file .env.docker exec mysql mysql -uresearchpilot -p researchpilot -e "SELECT id, mode, status, attempt_count FROM research_runs ORDER BY created_at DESC LIMIT 20;"
docker compose --env-file .env.docker exec redis redis-cli XLEN deeptrace:research:jobs
```

普通停止不会删除 MySQL 和 Redis 数据。

```powershell
docker compose --env-file .env.docker down
```

只有确认需要清空本地数据库和队列时才执行 `docker compose --env-file .env.docker down -v`。

```powershell
uv run researchpilot --mode deep "比较几种 Agent 架构，并说明各自适用场景与局限"
uv run researchpilot --mode multi_agent "梳理 2025 年 AI 热点，并区分技术、产业与监管方向"
uv run pytest -m "not real"
uv run python bench_deep.py --output runs/deep-smoke.json
```

## 实现与验证

- [后端配置与 API](backend/README.md)
- [Agent Harness 总体设计](docs/superpowers/specs/2026-09-10-langgraph-agent-harness-refactor-design.md)
- [Agent Harness 交付路线图](docs/superpowers/plans/2026-09-10-langgraph-agent-harness-roadmap.md)
- [当前阶段实施计划](docs/superpowers/plans/2026-09-12-workflow-response-vertical-slice.md)
- [文档索引](docs/README.md)

项目正按路线图迁移到统一 Agent Harness。旧 Basic、Deep 和 Multi-Agent
执行路径在对应策略子图完成前仍保持可运行，但不再作为目标架构文档。
