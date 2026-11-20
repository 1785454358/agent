# 多来源研究场景实测（2026-11-19）

行业研究、竞品分析与技术调研各 2 题，Workflow、Plan-and-Execute、Multi-Agent 各执行 6 题，共 18 次真实联网运行。17 次完成、1 次部分完成，目标层未捕获异常 0 次。15 次通过正确性与证据支持双 0.8 门槛，13 次同时满足指定的两组官方来源要求。

[题目及参考要点](cases.jsonl) · [逐次结果与 Trace ID](results.json) · [LangSmith 数据集](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/datasets/da53c1cd-a975-47ff-9ebc-e7668d10d113) · [Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/c3a264ab-2512-47ec-b6d0-2db166e6f92d) · [Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/e9fca17e-3f72-4ef2-a3af-0483bd8c84c5) · [Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/da28f11c-f66c-4e00-8b09-6fa495301e9a)

## 策略与质量

| 策略 | 完成 / 部分完成 | 双 0.8 门槛 | 覆盖两组官方来源 | 两项均通过 | 模型预算 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Workflow | 6 / 0 | 6/6 | 5/6 | 5/6 | 6/6 |
| Plan-and-Execute | 6 / 0 | 5/6 | 4/6 | 4/6 | 6/6 |
| Multi-Agent | 5 / 1 | 4/6 | 5/6 | 4/6 | 6/6 |
| **合计** | **17 / 1** | **15/18** | **14/18** | **13/18** | **18/18** |

| 题目 | 双 0.8 门槛 | 两项均通过 |
| --- | ---: | ---: |
| 行业研究 · 2024–2025 全球电动乘用车市场 | 3/3 | 3/3 |
| 行业研究 · 数据中心用电需求 | 3/3 | 3/3 |
| 竞品分析 · AWS Lambda Event Functions 与 Google Cloud Run services | 3/3 | 3/3 |
| 竞品分析 · Cloudflare R2 Standard 与 Amazon S3 Standard | 3/3 | 3/3 |
| 技术调研 · PostgreSQL 17 事务隔离与写偏差 | 2/3 | 0/3 |
| 技术调研 · Kubernetes 节点维护与滚动更新 | 1/3 | 1/3 |

## 调用、耗时与 Token

| 策略 | 端到端 P50 / P95 | 模型调用总数 / 每题 P50 | 每题输入 / 输出 / 总 Token P50 | 网关观测总 Token | 工具成功 / 调用 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Workflow | 41.2 / 87.2 秒 | 34 / 6 | 16,068 / 2,794 / 19,114 | 113,116 | 213 / 217 |
| Plan-and-Execute | 40.2 / 50.9 秒 | 34 / 6 | 17,149 / 2,546 / 19,695 | 111,280 | 209 / 212 |
| Multi-Agent | 48.1 / 73.8 秒 | 33 / 5.5 | 15,943 / 2,689 / 18,632 | 101,700 | 208 / 211 |
| **合计** | **40.4 / 87.2 秒** | **101 / 6** | **17,113 / 2,689 / 19,365** | **326,096** | **630 / 640** |

- 101 次研究模型调用中，100 次常规 usage 完整，覆盖 17/18 次运行。网关观测到 279,642 输入、46,454 输出，共 326,096 Token。输出截断异常另带 6,169 输入、16,000 输出 Token。核对后研究侧已知总量为 **348,265 Token**。表中每题 Token 中位数仅使用 17 条常规用量完整的记录，输入、输出和总量各自计算中位数。
- 裁判记录 18 次模型子调用，126,972 输入、95,402 输出，共 222,374 Token，均有 usage。裁判 Trace 耗时 P50 为 30.3 秒。
- 640 次工具调用成功 630 次。10 次失败包括 PDF 超页 3 次、PDF 解析超时 2 次、响应超限 2 次以及内容不足 3 次。研究模型子调用异常 1 次。

## Trace 归因

- **PostgreSQL 17。** Workflow 和 Plan-and-Execute 引用了 `current` 文档，答案通过语义门槛，但缺少 17 版的指定来源。Multi-Agent 的 Writer 在输出达到 16,000 Token 时触发 `LengthFinishReasonError`，该次模型调用耗时 57.7 秒，Runtime 记录 `partial / response_error` 并返回有限结果。三次均未通过包含来源要求的验收。
- **Kubernetes。** Plan-and-Execute 缺少 Deployments 文档，证据支持 0.75。Multi-Agent 引用了两类文档，裁判指出它遗漏了滚动更新产生的不可用副本仍计入 PDB 预算，以及部分细节缺少原文支撑，证据支持 0.72。Workflow 两项均通过。
- **行业 PDF。** 数据中心用电题三种模式均通过，耗时 45.9–87.2 秒。该题的单次 Trace 记录了 PDF 超限和解析超时。

## 运行口径

- 测试对象为当前工作区的统一研究 Runtime，三种模式手动指定。Workflow 顺序收集，Plan-and-Execute 顺序收集并复用已授权来源，Multi-Agent 有界并行收集。三组各自并发 1，三组同时启动。
- 固定 LangSmith 题集 `deeptrace-multi-source-20261119-v1`，按 UTC 时间戳 `2026-11-19T11:05:46.439133+00:00` 读取同一版本。每题每模式一次，公开网页实际搜索和抓取。目标只收到题目，参考要点与官方来源仅用于评分。每次运行使用独立 run/thread，关闭跨样本记忆。
- 研究模型和裁判均为 `deepseek-v4.1-flash`，研究侧关闭 thinking。每次研究的模型上限为 20 次，输入预算 100,000 Token。另有工具上限 240 次、研究时间上限 600 秒。表中的模型预算通过项按评测适配器检查调用数和输入预算。
- 端到端耗时取 LangSmith 目标根 Trace 的首尾时间，覆盖检索、阅读和交付，排除裁判。P95 取最近秩。模型调用数取 Gateway 准入的调用尝试，包含失败尝试。已观测 Token 来自服务商 usage，缺失值保留为 null，完整用量样本单独计算每题中位数。
- 正确性和证据支持均用 0.8 门槛。裁判按参考要点检查正确性，按 Writer 实际看到的原文和最终引用 URL 检查证据支持。来源检查另核对最终引用是否覆盖每题要求的两组官方资料，具体 URL 匹配规则和裁判评语见 [逐次结果](results.json)。
- 6 道题为有参考答案的场景试测，使用 LLM 裁判且每种配置只采样一次。网页状态、响应和调用耗时会变化。这次使用有本地改动的工作区，Git HEAD 与源码指纹均写入结果。

## 复现

在 `backend` 目录运行。该数据集版本已经同步。

```powershell
$version = '2026-11-19T11:05:46.439133+00:00'
foreach ($mode in 'workflow', 'plan_execute', 'multi_agent') {
    uv run python -m deeptrace.evaluation run --dataset deeptrace-multi-source-20261119-v1 --dataset-version $version --mode $mode --concurrency 1 --judge
}
```

上面的循环依次运行三组。复现本轮的并发环境时，可在三个终端分别同时启动每个模式。


## 工程回归

后端离线回归 1,778 项通过，1 项真实外部测试未选中。34 条告警中有一条来自 SQLite 测试后台线程在事件循环关闭时抛出的告警。未捕获异常 0 次统计的是本轮联网目标运行。

## 简历表述

> **评测与归因**｜基于 LangSmith 对行业研究、竞品分析、技术调研的 6 个多来源场景开展 18 次真实联网评测，追踪模型调用、Token、延迟及工具错误。单次端到端 P50 40.4 秒、模型调用 P50 6 次，13/18 次同时通过正确性与证据支持双 0.8 门槛及指定来源校验，18/18 次通过模型预算检查。
