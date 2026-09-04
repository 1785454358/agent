# DeepTrace

DeepTrace 是命令行规划式深度研究 Agent：Planner 把宽泛问题拆成互补的子任务，Researcher 在每个子任务内执行真实搜索与网页抓取，压缩环节用本地 BGE-M3 向量相似度过滤出逐字原句（全程零 LLM），Writer 直接基于带编号来源的原文片段写作，引用由系统机械拼接、模型无法伪造出处。

阶段 4（Evidence/Claim/Verifier）已于 2026-09-03 移除：Claim 抽取与核验会让同一内容被 LLM 重复读取约 3 遍（占 Token 约 40%），且在真实 Provider 时限内从未产出可用的 `verified` 结论。Writer 改为直接消费压缩后的原句笔记。当前能力 = 阶段 1-3 的规划式研究链路 + 阶段 5 的 API/Web 仪表盘与研究记忆；阶段 6（系统评测）未开始。

## 特性

- **规划式研究**：Planner 生成带时间范围的互补子任务；解析失败重试一次后降级为单任务计划。
- **并行子任务**：按 `DEEPTRACE_TASK_CONCURRENCY`（默认 2）并行执行子任务，全局预算经网关竞争。
- **零 LLM 上下文压缩**：页面分块后由本地 BGE-M3 按双查询召回，再逐句过滤只保留最相关原句。
- **搜索+抓取融合**：搜索轮内自动抓取排名最靠前的搜索候选，直接产出研究笔记，省掉"只搜不抓"的往返。
- **机械引用**：Writer 只看到带编号来源的原句片段，引用编号由系统校验拼接，不能伪造出处。
- **确定性停止**：按轮数、连续空轮、抓取页数、运行时间、Provider Token 与可选费用上限停止，不依赖模型自判。
- **研究记忆**：成功抓取的页面写入 `memory/notes.jsonl`，后续运行命中同一 URL 时免网络抓取。
- **API 与仪表盘**：FastAPI 任务管理、SSE 实时事件流与运行持久化。

## API 服务与记忆（阶段 5）

```powershell
uv run python -m deeptrace.api        # http://127.0.0.1:8000 打开研究仪表盘
```

- `POST /researches {"question": "..."}` 创建研究任务（后台异步执行）
- `GET /researches/{id}` 查询状态、报告、来源、逐环节用量
- `GET /researches/{id}/events` SSE 实时事件流
- `POST /researches/{id}/cancel` 取消运行
- 运行记录持久化为 `runs/<id>.json`

`DEEPTRACE_USE_MEMORY=true` 开启研究记忆：成功抓取的页面按 URL 与内容哈希写入 `memory/notes.jsonl`，后续运行命中同一 URL 时免网络抓取（不占页面预算），直接进入召回与压缩。

## 运行

复制 `.env.example` 为 `.env`，填写真实 OpenAI-compatible 接口和 Tavily Key：

```powershell
uv sync
uv run playwright install chromium
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
```

Chromium 只在 HTTPX 无法提取足够正文时启用。受控代理或沙箱把公网域名映射到 `198.18.0.0/15` 时，可以显式设置 `DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY=true`；普通网络环境不要开启。

主要预算与并发环境变量及默认值如下：

```text
DEEPTRACE_MAX_RESEARCH_TASKS=4
DEEPTRACE_TASK_CONCURRENCY=2
DEEPTRACE_MAX_TASK_ROUNDS=3
DEEPTRACE_MIN_SOURCES_PER_TASK=2
DEEPTRACE_MAX_FETCHED_PAGES=20
DEEPTRACE_MAX_RUNTIME_SECONDS=600
DEEPTRACE_HARD_MAX_STEPS=12
```

可选的 `DEEPTRACE_INPUT_COST_PER_MILLION`、`DEEPTRACE_OUTPUT_COST_PER_MILLION` 和 `DEEPTRACE_MAX_COST_USD` 用于费用估算及上限；设置费用上限时必须同时提供输入、输出单价。`DEEPTRACE_EMBEDDING_MODEL_PATH` 指向本地 BGE-M3 模型目录。

## 目录结构

```text
src/deeptrace/
├── agent/             # Planner、Researcher、Writer 与门面
├── config/            # 环境变量、默认值和配置校验
├── context/           # 分块、BGE-M3、召回与压缩
├── models/            # 跨模块可序列化数据模型
├── observability/     # Token 估算、账本、费用和格式化
├── orchestration/     # LangGraph State、预算、并行任务与节点
├── prompts/           # Planner、Researcher、Writer 提示词
├── tools/
│   ├── scraper/       # HTTPX、Trafilatura、BS4、Playwright 与 URL 安全
│   └── search/        # Tavily 搜索与来源排序
├── memory.py          # 跨运行研究记忆（阶段 5）
├── api.py             # FastAPI 服务与 Web 仪表盘（阶段 5）
├── __init__.py        # 稳定公共 API
└── cli.py             # 命令行入口
```

依赖方向固定为：

```text
models / prompts / config
          ↓
context / tools / observability
          ↓
orchestration
          ↓
agent
          ↓
cli / api（api 额外接入 memory.py 与运行持久化）
```

## 核心模块

| 模块 | 主要职责 |
|---|---|
| `agent/planner.py` | 生成结构化研究计划；解析失败重试一次后降级为单任务计划 |
| `agent/researcher.py` | 在当前子任务边界内选择搜索、抓取或显式完成任务 |
| `agent/writer.py` | 基于带编号来源的原文片段写作，引用编号校验与机械拼接；失败走确定性降级 |
| `agent/service.py` | `ResearchAgent`、`AgentResult`、预算与记忆初始化和 LangGraph 门面 |
| `orchestration/` | LangGraph State、全局预算、并行子任务管线、研究决策轮与工具执行 |
| `context/` | 800/100 分块、BGE-M3 向量注册表、双查询 max 召回、零 LLM 的句子级向量压缩 |
| `tools/search/` | Tavily 搜索、重复查询检测与来源排序 |
| `tools/scraper/` | URL 安全、HTML 发布时间元数据、HTTPX/Trafilatura/BS4/Playwright 抓取降级链 |
| `models/` | 可序列化的计划、任务、笔记、章节和 Token 模型 |
| `prompts/` | 统一管理 Planner、Researcher、Writer 提示词 |
| `observability/` | 逐轮 Token 账本、估算与按角色用量汇总 |
| `config/` | Settings 和环境变量验证 |
| `memory.py` | 页面级记忆的 JSONL 读写与文档互转 |
| `api.py` | 任务管理、SSE 事件流、运行持久化与 Web 仪表盘 |

长提示词只放在 `prompts/`。模型 JSON 经过本地修复与 Pydantic 严格校验，以兼容不支持工具式结构化输出的 OpenAI-compatible Provider。阶段 4 的 Claim 级验证已移除，Writer 直接基于带编号来源的原文片段写作；数据库与规模化评测尚未实现。

## 核心流程

```text
Planner（生成子任务）
  → 并行执行子任务（并发 = task_concurrency）
      每个子任务循环（至多 max_task_rounds 轮）：
        研究决策（search_web / fetch_webpage / complete_research_task）
          → 搜索 + 有界抓取（最多 3 页，含自动抓取 top 搜索候选）
          → BGE-M3 分块召回 → 零 LLM 句子级向量压缩 → 原句笔记
      循环在任务完成 / 预算或连续空轮停止时结束
  → 逐任务生成章节结果
    → Writer ← 各章节带编号来源的原文片段（引用由系统机械拼接）
```

子任务并行执行，共享全局预算；每轮最多实际抓取 3 个排序后的候选。压缩与 GPT-Researcher 同思路：入选块拆句后按本地 BGE-M3 向量与双查询的相似度过滤，只保留最相关的原句作为笔记要点与证据摘录，全程零 LLM 调用；时间关系由入选句子中的日期规则确定性分类（in_range / retrospective / unknown / out_of_range）。同一页面遇到新子问题时复用正文、chunks 和内存向量，只重新筛选并生成带 `task_id`、`section_id` 的新笔记。系统按任务轮数、连续空轮、来源覆盖、网页数、步骤、运行时间、Provider Token 和可选费用预算确定性停止。

Writer 只消费研究计划、各章节结果与笔记，真实使用过的笔记 id 才反向生成来源列表，不会泄漏未被引用的抓取页；个别子任务失败时保留原因并生成标明缺口的部分报告。CLI 与 API 汇总 Planner、Researcher、Compression、Writer 的 Provider Token 用量与估算费用。

## 本地验证

```powershell
uv run pytest -m "not real"
uv run python -m compileall src tests
```

普通测试不调用外部 API。真实端到端验证直接运行 `uv run deeptrace "问题"`，必须使用真实 LLM、Tavily、网页抓取和本地 BGE-M3；`partial` 或 `failed` 状态会返回非零退出码。
