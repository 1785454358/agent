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
和确定性缺口补查仍然保留。

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

## 启动

```powershell
cd backend
# 复制 .env.example 为 .env，并配置兼容原生 tools/tool_calls 的模型、Tavily 与本地 BGE-M3
uv sync
uv run playwright install chromium
uv run python -m deeptrace.api
```

打开 http://127.0.0.1:8000，在模式选择中切换 Basic / Deep / Multi-Agent。

```powershell
uv run researchpilot --mode deep "比较几种 Agent 架构，并说明各自适用场景与局限"
uv run researchpilot --mode multi_agent "梳理 2025 年 AI 热点，并区分技术、产业与监管方向"
uv run pytest -m "not real"
uv run python bench_deep.py --output runs/deep-smoke.json
```

## 实现与验证

- [后端配置与 API](backend/README.md)
- [Deep 架构设计](docs/superpowers/specs/2026-09-05-deep-research-design.md)
- [Supervisor Multi-Agent 架构设计](docs/superpowers/specs/2026-09-06-supervisor-multi-agent-design.md)
- [文档索引](docs/README.md)

当前已实现单 Agent 的规划、执行和重规划闭环。模式不涉及模型训练或内部
推理展示；事件展示的是可核对的计划、工具选择和结果。研究质量仍取决于
来源与模型判断，复杂问题的质量/成本对照评测尚待建立。
