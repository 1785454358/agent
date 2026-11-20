# LangSmith Tracing & Evals

项目使用 LangSmith 统一管理调用树、数据集、实验、评分与对照分析。自建 Trace SQL 存储、Trace 查询 API、诊断面板、独立评分容器和旧 `deeptrace.eval` 框架已经移除。

## 配置

在 `backend/.env` 中配置（不要提交密钥）：

```dotenv
LANGSMITH_API_KEY=<your-key>
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=deeptrace
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

启动真实研究后，在项目 `deeptrace` 按 metadata 中的 `run_id`、`thread_id` 和 `mode` 搜索。LangGraph 原生记录节点和分支，LangChain 原生记录模型调用耗时及服务商返回的 Token；`research.run` 关联运行结果，Tool Gateway 的 SDK span 记录工具执行、缓存、重放和失败，每次实际工具尝试另有子节点。错误结果不会改变工具原有返回契约。缺失的服务商 usage 不能当作零消耗。

应用入口只上传问题、运行标识和结果；工具入口排除宿主授权、客户端实例、上下文和非允许参数。问题、模型消息和抓取内容可能包含业务正文，可通过 `LANGSMITH_HIDE_INPUTS=true` / `LANGSMITH_HIDE_OUTPUTS=true` 隐藏上传内容。SDK 负责传输和存储；正常关闭 Runtime 会有界刷新 SDK 队列。

Checkpoint、Memory、Tool Ledger 和产品进度事件仍留在应用内：它们分别承担恢复、跨任务知识、执行幂等与预算、前端进度展示，不能用观测平台代替。

## 数据集与实验

从 `backend` 目录运行：

```powershell
uv run python -m deeptrace.evaluation sync-dataset
uv run python -m deeptrace.evaluation run --mode workflow --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode plan_execute --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode multi_agent --max-examples 1 --judge
```

默认数据集 `deeptrace-grounded-v1` 包含现有的 **30 道**参考题及同一份经过 SHA-256 校验的完整冻结文档集，保留开发/测试划分、参考答案、评分要求、来源定位、提交版本与许可信息。JSONL 使用 LangSmith 原生 `inputs/outputs/metadata` 格式。稳定 UUID 保证重复同步更新同一示例，不删除云端额外示例。自定义数据可使用 `sync-dataset --file path/to/examples.jsonl --dataset dataset-name`。

默认同步会把完整的 14 份公开文档装入原生 example inputs，目标通过共享 Runtime 的限定来源模式读取，Gateway 禁止范围外取证。旧 `deeptrace-research-v1` 曾仅传问题并联网执行，存在资料条件不一致，保留为历史诊断，不再作为默认验收。联网能力另由 `deeptrace-web-smoke-v1` 验证。具体规则与命令见 [核心 Runtime 验收](acceptance.md)。历史自建报告中的旧命令不再适用于当前版本。

每个评测样本和重复运行都有独立 run/thread 身份，关闭跨任务记忆，并使用临时 Checkpoint/Evidence 数据库。参考答案由 LangSmith 传给 evaluator，不进入研究目标。默认并发 1、重复 1，可用 `--concurrency 1..6`、`--repetitions 1..10` 调整。省略 `--max-examples` 将执行整个数据集，会调用真实模型和搜索服务。

使用 `--split dev` / `--split test` 选择划分，`--dataset-version <timestamp-or-tag>` 固定 LangSmith 数据版本。实验 metadata 记录 Git revision、工作树是否有改动、模型、预算、来源目标、完成规则和裁判开关；未提交工作树的 revision 不能独立复原全部代码。目标异常或 failed 结果会让命令失败；partial 仍作为有效评测结果写入，完成率为零。

编排迁移对比使用 `--orchestrator legacy|controller` 显式选择内核；省略时沿用 `DEEPTRACE_RESEARCH_ORCHESTRATOR`。该参数只覆盖本次实验的装配配置。实验名包含编排器和对外模式，例如 `deeptrace-controller-plan_execute`；metadata 的 `research_orchestrator` 记录实际使用的值，避免把相同 mode 下的新旧内核混为一组。

先用同一版本的一题检查完整路径，再扩大到同一划分的多次采样。下面两条命令必须使用同一个已存在的数据版本，并保持模型、预算、题目选择与裁判配置一致：

```powershell
$datasetVersion = "<timestamp-or-tag>"
uv run python -m deeptrace.evaluation run --mode plan_execute --orchestrator legacy --dataset-version "$datasetVersion" --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode plan_execute --orchestrator controller --dataset-version "$datasetVersion" --max-examples 1 --judge
```

这些命令会调用真实模型并向 LangSmith 写入实验；本地 pytest 的编排选择与 metadata 回归使用替代服务，不产生云端实验。一题路径通过不能证明整体质量不退化；默认切换与旧策略删除仍需完整配对评测及逐题检查。

样本按 `metadata.id` 排序后才应用 `--max-examples`，不依赖云端最新上传顺序。用 `--case-id single_hop-dev-01` 指定可回答题，或 `--case-id insufficient_evidence-test-03` 复现不可推导题。后者的正确答案是说明概念资料无法提供实测精度或财务 ROI；不能用该题的 Runtime completed 指标单独评判策略能力。[planning_limit 定位与优化记录](../benchmarks/2026-11-09-planning-limit/README.md)保留具体原因、候选回退与复测结果。

LangSmith `aevaluate` 负责执行、关联 Trace、存储反馈及实验比较；项目只提供目标适配器和以下业务反馈：

| 指标 | 含义 |
| --- | --- |
| `execution_completed` | Runtime 是否 completed；partial/failed 不算成功 |
| `evidence_sufficient` | 生产证据核验是否充分；未知或不需要时为未评分 |
| `tool_success_rate` | Gateway 成功返回次数 / 调用次数；包含缓存、重放和被拒绝调用；没有调用则未评分 |
| `answer_correctness_v4` | 问题与参考要求的满足程度，0..1 |
| `answer_groundedness_v4` | 基于原生 Trace 中 Writer 实际可见原文的证据支持，按最终引用 URL 映射校验 |
| `task_accepted_v4` | 正确性及证据支持均 ≥0.8、来源与预算检查通过；门禁可用 `--require-acceptance` 启用 |

延迟、Token、调用错误在 LangSmith Trace 中查看；工具重试率可根据 `tool.provider_attempt` 与 `tool.execute` 区分。使用同一数据集版本、划分、模型、预算、Prompt 代码版本和裁判配置比较实验；开发题用于迭代，测试题用于保留验证。不要用单题满分推断总体质量，也不要将当前 30 道题写成 50+。

CI 的确定性测试不调用云服务；`.github/workflows/langsmith-evaluation.yml` 提供手动真实评测，需配置同名模型、搜索和 LangSmith Secrets，以及 `OPENAI_MODEL` / `OPENAI_BASE_URL` Variables。

## 存储迁移

分布式部署执行 `uv run alembic upgrade head`。新增迁移 `20261109_02` 删除旧 `trace_events` / `trace_spans` 表；历史迁移保留。降级只能重建表结构，不能恢复旧 Trace 数据。Local 不再创建 `execution_traces.db`，已有文件不会被启动过程自动删除。

## 简历表述

> 接入 LangSmith 构建跨 Workflow、Plan-and-Execute 与 Multi-Agent 的全链路 Tracing，关联模型耗时与 Token、工具执行及失败重试；迁移 30 道带参考答案和来源的评测样本，基于 LangSmith Datasets / Experiments 实现端到端评测，分别跟踪执行完成率、证据充分性、工具成功率与答案正确性，支持 Prompt 和检索策略的实验对照。

完整任务矩阵与失败修复记录见 [核心 Runtime 验收](acceptance.md)。裁判阈值是诊断规则，不代表准确率；真实质量仍需结合逐题原文、失败原因和使用场景评估。
