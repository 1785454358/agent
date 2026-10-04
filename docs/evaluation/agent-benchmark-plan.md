# 最小评测方案：离线模拟环境 + 多策略 A/B

本文给出一个可落地的评测设计，用于回答两个问题：**三种研究策略各自值多少**，以及**整套 Harness 相对简单方案是否有增益**。方案刻意从最小的确定性基线长出来，不依赖任何 live API，可先在 CI 里跑。

## 目标与非目标

**目标**

- 在同一问题集、同一语料、同一模型、同一预算下，对比 Workflow、Plan-and-Execute、Multi-Agent 三种策略的质量、成本与可靠性。
- 得到一个可复现、可解释、样本量明确的研究质量信号，而不是只报"能跑通"。
- 把"失败、恢复、引用可信"这些治理能力变成可测量的指标。

**非目标**

- 不与通义 DeepResearch 在 HLE / BrowseComp 上做排名竞争。对方有专门训练的模型和合成数据，这不在本方案范围。
- 不追求大规模、多模型、多语言的全面覆盖。先做小而可解释，再谈扩展。

## 现状基线

已有 [`tests/integration/test_mode_evaluation.py`](../../backend/tests/integration/test_mode_evaluation.py)，它在脚本化数据集上对三种策略计算确定性的质量 / 成本 / 延迟代理：

- 通过 [`tests/strategies/fixtures.py`](../../backend/tests/strategies/fixtures.py) 的 `build_gateway_fixture` 注入 `ScriptedSearch` 与 `ScriptedFetcher`，完全离线。
- 断言 `termination == "completed"`、`answered`、`evidence_count == 1`，并约束 `executed_steps` 上限。

这个基线证明了流程可跑通，但有两个缺口：语料只有一条记录，且没有质量评分。本方案在它之上扩展，不替换。

## 分层设计

| 层 | 运行环境 | 模型 | 断言方式 | 是否进 CI |
| --- | --- | --- | --- | --- |
| Tier 0 | 脚本化单条数据 | 脚本 Gateway | 运行不变量 + 成本代理 | 是（现有） |
| Tier 1 | 离线语料 + 确定性适配器 | 脚本或确定性 stub | 金标证据覆盖、引用合法、成本 | 是 |
| Tier 2 | 同一离线语料 | 真实 OpenAI-compatible | LLM-as-judge 多维评分 + A/B 报告 | 否，`real` 标记 |

Tier 1 保证评测代码本身正确且可复现；Tier 2 才回答研究质量问题。两层共用同一语料、数据集和 runner。

## 离线模拟环境

参考通义"离线 Wikipedia + 工具沙箱"的思路，核心是让 `search_web` / `fetch_page` 在本地语料上确定性工作，从而完全摆脱 live API。

组件：

- **Corpus**：本地文档集合，JSONL，字段 `doc_id / url / title / body / tags`。可先手工构造 30–100 篇覆盖评测问题的小语料。
- **CorpusSearch**：对语料做关键词或 BM25 检索，返回 `{"results": [{"url", "title", "snippet"}]}`，与 `ScriptedSearch` 输出结构一致。
- **CorpusFetcher**：`url → RawDocument`，从语料读取，与 `ScriptedFetcher` 一致。
- **FaultInjector**：按配置对特定 URL 注入超时、空正文或 429，用于测量 ToolGateway 重试与 Agent 语义修复。

这三个适配器直接替换 [`build_gateway_fixture`](../../backend/tests/strategies/fixtures.py) 里的 `ScriptedSearch` / `ScriptedFetcher`，其余 `AgentToolGateway`、预算、缓存、Ledger、Evidence Store 全部复用生产实现，保证评测的是真实运行路径。

## 数据集

JSONL，每条：

```json
{
  "id": "q-001",
  "question": "问题文本",
  "gold_answer": "标准答案",
  "gold_urls": ["https://corpus.example/doc-3"],
  "category": "multi-hop",
  "hops": 2
}
```

- `gold_urls` 用于计算证据覆盖，不要求答案逐字一致。
- `category` 与 `hops` 用于分层报告，观察不同策略在不同难度下的差异。
- 拆分：`smoke`（3–5 题，Tier 1 用）与 `full`（Tier 2 用）。

## Runner

对每个 `(question, mode)` 组合：构建独立 `HarnessContext`，通过 [`ResearchApplicationService.invoke`](../../backend/src/deeptrace/application/research.py) 走完整 [顶层 Graph](../../backend/src/deeptrace/harness/graph.py)，采集：

- `ResearchOutcome`（`termination_reason`、`evidence_ids`、`findings`、`executed_steps`）
- `ResponseOutcome`（`partial_reason`、引用）
- `AgentOutcome`（status、stop_reason、budget 快照、未完成计划）
- 事件流（`tool.completed` 等）与计时

控制项：固定时钟（`FixedClock`）、`temperature=0`、每模式固定预算、语料固定。每个组合单独持久化为 JSON，便于离线复算。

## 指标

**确定性指标（Tier 1 + Tier 2）**

| 指标 | 含义 |
| --- | --- |
| `termination_reason` 分布 | 完成 / 无来源 / 达到上限 / 证据不足 |
| `partial_reason` | 答案是否可用 |
| `evidence_count`、`unique_domains` | 检索广度 |
| `gold_evidence_coverage` | 命中金标 URL 的比例 |
| `citation_validity` | 引用是否全部在允许证据集内 |
| `model_calls`、`tool_calls`、`fetched_pages`、`wall_ms` | 成本 |
| 错误码分布 | 失败模式与熔断触发情况 |

**LLM-as-judge 指标（仅 Tier 2，1–5 分）**

- `faithfulness`：结论是否被引用证据支持
- `answer_correctness`：与 `gold_answer` 的一致性
- `source_coverage`：资料广度与质量
- `citation_accuracy`：引用与论断是否对应
- `coherence`：报告结构

评判时把证据正文一并给 judge，且**不告知模式名称**，避免偏向。每个组合重复 `k=3` 次，报告均值与极差。

## 对照与严谨性

- **四号对照**：加入一个单循环 ReAct 配置，用来验证 LangChain open_deep_research 的结论（单循环是否已足够），避免只比较自己的三种策略而自说自话。
- **无检索对照**：关闭 `search_web`，界定检索带来的增益上界。
- **故障注入对照**：注入固定失败，测量恢复与部分成功能力，这是纯质量评分看不到的 Harness 价值。
- 所有对比保证同问题、同语料、同模型、同预算，并明确写出样本量，避免把小样本结论说成普适结论。

## 故障注入场景

`EvalFaults` 在离线语料上注入确定性故障，用于验证三层修复的归属：

| 故障模式 | 触发路径 | 期望行为 |
| --- | --- | --- |
| `transient_once` | 首次抛可重试超时，之后成功 | ToolGateway 内部退避重试，`tool.retry` 事件计数 > 0，最终 completed |
| `empty` | 页面返回空正文 | 属 agent-recoverable，网关不重试；Agent Loop 换下一个来源 |
| `transient_always` | 每次都超时 | 网关重试耗尽后返回结构化失败，循环继续或收尾 |
| `raise` | 未处理异常 | 映射为 fatal 工具失败，记录且不重试 |
| `search_queries` | 指定查询强制搜索失败 | 无来源时产出 partial，不崩溃 |

对应断言见 `tests/eval/test_faults.py`，全部离线、秒级。

## 目录与接口草案

```text
backend/
  src/deeptrace/eval/
    __init__.py
    env.py       # Corpus / CorpusSearch / CorpusFetcher / EvalFaults / build_eval_context
    dataset.py   # EvalQuestion / CorpusDocument / 加载与校验
    scripted.py  # ScriptedResearchModel / ScriptedJudgeModel：零外部调用
    real.py      # build_real_model_factory：Tier 2 真实模型网关
    judge.py     # JudgeScore / judge_record：LLM-as-judge
    runner.py    # build_eval_graph / run_matrix / RunRecord
    scoring.py   # 确定性指标 + judge 聚合
    report.py    # markdown 渲染
    __main__.py  # python -m deeptrace.eval
    data/
      corpora/smoke.jsonl
      datasets/smoke.jsonl
  tests/
    eval/
      test_dataset.py
      test_env.py
      test_smoke_matrix.py   # @pytest.mark.eval
      test_faults.py         # 故障注入与恢复路径
      test_judge.py          # judge 与 repeats 接线
    real/
      test_eval_quality.py   # @pytest.mark.real
```

评测资产放在 `deeptrace.eval` 包内（`data/`），因此 `python -m deeptrace.eval` 无需参数即可运行，也保证打包后可用；规模较大的 full 数据集在 M2 再考虑移出包外。

关键接口：

- `build_eval_context(corpus, *, model_gateway, run_id, faults=None, retry_attempts=3) -> EvalEnvironment`：复用生产 `AgentToolGateway` 与预算/缓存/账本/证据存储，只替换 search / fetch 适配器和 model gateway，返回可直接喂给 `ResearchApplicationService` 的 `HarnessContext`，并暴露调用计数与事件。
- `run_matrix(questions, corpus, *, model_factory, modes=None, run_prefix, faults=None, repeats=1, judge_factory=None) -> list[RunRecord]`。
- `build_real_model_factory(settings=None)`：Tier 2 的 `ChatModelGateway` 工厂，沿用生产模型信封校验。
- `score_records(records, questions) -> ScoreReport`。

## 运行方式

```powershell
cd backend
# Tier 1：离线确定性基线
uv run python -m deeptrace.eval
# 指定模式、重复 k 次、并用（脚本）judge 评分
uv run python -m deeptrace.eval --modes workflow --repeats 2 --judge
# Tier 2：真实模型 + 真实 judge（需要 .env 凭据）
uv run python -m deeptrace.eval --model real --judge --repeats 3 --out runs/eval
```

## CI 集成

- 新增 pytest marker `eval`，默认 CI 跑 Tier 1 的 `smoke` 数据集（确定性、秒级）。
- Tier 2 使用现有 `real` marker，需要凭据时手动或定时触发，入口为 `tests/real/test_eval_quality.py`。
- `pyproject.toml` 的 `markers` 增加 `"eval: 离线确定性评测"`，与现有 `real` 并列。

## 里程碑

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| M1 | 小语料 + 三个适配器 + smoke 数据集 + 确定性覆盖指标 + 报告骨架 | 已实现 |
| M2 | 真实模型工厂 + k 次重复 + LLM judge + markdown 报告 | 已实现，真实调用待凭据 |
| M3 | 故障注入 + 单循环 ReAct 对照 + 多次方差报告 | 故障注入已实现，其余待做 |

M1 已落地：`uv run python -m deeptrace.eval` 输出三种策略在同一 smoke 语料上的确定性对比，3 个问题 × 3 种策略全部 `completed`、gold coverage 与 citation validity 均为 1.0。

M2 的接线已完成（`--model real`、`--judge`、`--repeats`），并配 `@pytest.mark.real` 测试，但**尚未在本机用真实凭据跑过**，因此不报告任何真实研究质量数字。

M3 的故障注入已实现并离线验证：`transient_once` 触发网关重试、`empty` 触发 Agent 换源、硬失败产出 partial 且不崩溃。单循环 ReAct 对照与多次方差报告仍待做。

这些都是流程与覆盖基线，不是研究质量结论。

## 面试口径

- 可以说"已有脚本化数据集上的确定性质量 / 成本代理对比，并设计了离线模拟评测方案"。
- 不要说"已完成系统化在线研究质量评测"。
- 引用具体分数时必须注明样本量、语料来源、模型和运行次数。
- 与通义等项目的 benchmark 数字对比时，注明那是对方公开结果，不作为本项目结论。
