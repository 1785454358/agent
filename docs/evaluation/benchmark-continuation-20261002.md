# 评测系统续建：回答预算、配对统计与记忆生命周期

本轮完成三个可运行的工程模块：显式回答长度约束、离线配对统计、真实应用链路的记忆生命周期评测。没有新增真实 API 请求，没有覆盖首轮真实失败或重新刷分。当前仍不是完整 30 题测评验收。

## 一、回答长度成为实验参数

新增 `HarnessContext.response_max_content_chars`，评测 CLI 对应 `--response-max-chars`。有效值取显式参数与回答模式原有上限的较小值；首稿、一次纠正、确定性长度控制和失败兜底使用同一上限。参数参与实验身份，修改后不能续跑旧实验。

首轮 REPORT 允许 50,000 字符，但 Provider 请求输出为 2048 Token。两次 Baseline 响应在句中截断，缺失完整 JSON。现在可以为双方配置相同的简短回答上限，避免提示词要求与输出请求额度明显不匹配；不能把字符数换算成已验证的计费 Token 硬限制，也不能靠补 JSON 尾巴虚构答案。

回归测试用外部响应夹具复现未约束时的截断，再验证首稿约束与纠正共用 600 字符边界。本轮只验证该工程约束，**尚未用真实模型验证调整后的 Baseline 是否端到端通过**。

## 二、统计不再靠手工抄表

入口：`python -m deeptrace.eval.compare_cli`。输入是冻结的 `quality_eval.json`、独立 Ragas 输出 `quality_scores.json`、评分目录中的 `identity.json`，以及显式数据卡。

系统核对实验 manifest、裁判身份、裁判实际评过的完整输入哈希，以及数据集/语料哈希。分析不构造模型，不调用 Provider；输出目录必须为空。数据卡给每题指定 dataset、split、data_kind、category，开发校准、测试集与受控场景分别报告。

统计规则：

- 先在每题、每系统内部平均重复结果，再按题配对，不能把同题重复当独立样本。
- 主配对要求双方重复索引一致且全部有实际评分；缺失或错误不补 0，并公开排除题 ID。
- 系统均值是标明覆盖率的 available-case 题均值，不冒称所有尝试的总体均值。
- 分开输出 `all_output` 与 `completed_only`；失败仍在尝试数、完成数和失败原因分母中。
- 三个 Ragas 指标分别报告，不加随意总分；同时保留分类均值、延迟 p50/p95、usage 完整性和已观测小计。
- 标准库实现固定 seed 的题级配对 percentile bootstrap；0/1 对题的区间为 null。方法参照 [SciPy 对 paired bootstrap 的说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)，未新增 SciPy 依赖。

旧真实实验的离线复核结果保持不变：all-output 为 1 对，Goal / Factual F1 / Faithfulness 观察差值为 1.00 / 0.50 / 0.48，区间均为 null。completed-only 为 0 对，因为 Baseline 是 partial。这不是总体提升、显著性结论或商业 DeepResearch 对比。

报告：配对统计：`../../tmp/real-pilot-comparison-verified-20261002/comparison.md`（本地实验留样），完整统计与来源身份：`../../tmp/real-pilot-comparison-verified-20261002/comparison.json`（本地实验留样）。

## 三、长期记忆必须排除“聊天记录凑答案”

记忆评测使用生产 `ResearchApplicationService`、Harness、SqlAlchemyMemoryStore 与正常记忆写入/召回代码。每个 episode 独占一次性 SQLite，所有召回探针使用新 thread；探针之前的会话消息必须为空。用户偏好属于 user namespace，研究事实属于 workspace namespace，参照 [LangGraph 的跨线程 Store 职责](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/stores.mdx)，不将 Checkpointer 当长期记忆。

时间由 UTC 测试时钟控制。时间推进通过项目已有 `apply_lifecycle` / `set_status` 接口落地，删除通过已有 `forget` 接口执行；这是受控生命周期动作，不宣称项目已有自动清理调度器。显式偏好通过应用的“请记住”入口写入，事实通过研究后的正常 consolidation 写入，没有把参考答案直接塞进数据库。

| 分类 | 两个受控场景 |
| --- | --- |
| 偏好连续性 | 语言偏好、简洁程度；包含当前英文请求与历史中文偏好的冲突 |
| 跨会话召回 | 同一用户的语言与格式偏好跨工作区召回 |
| 背景复用 | 正常研究生成事实，另一新会话按关键词召回背景 |
| 到期信息 | 事实 TTL 恰好 30 天、超过 30 天后不得召回 |
| 更新与遗忘 | 同一偏好产生新版本、逻辑删除后不得召回 |
| namespace 隔离 | 不同用户偏好隔离、不同工作区事实隔离 |

12 个 episode 各跑 memory on/off，得到 **24 个 scripted 变体**，不是 24 道真实质量题。外部模型固定为脚本模型；搜索/抓取为显式 synthetic 资料。当前后端为 SQLite + lexical recall，不是 embedding/Chroma 语义召回。

实测：

| memory | episode 数 | 指定正向记忆命中 | 约束违规 | 跨 namespace 命中 |
| --- | ---: | ---: | ---: | ---: |
| off | 12 | 0/7 | 0 | 0 |
| on | 12 | 7/7 | 0 | 0 |

另有 5 个到期/删除/隔离的负向探针，每个变体均未召回禁用内容。memory off 的 7 个正向漏召回保留为 false，不伪造通过；它们是对照现象，不是关闭记忆模式的运行故障。

每个探针检查：新 thread、namespace、指定目标、禁用内容、记录是否 active 且未到期、召回内容是否实际进入模型输入、关闭记忆时是否为空、当前请求优先规则是否可见。**规则可见不代表模型真的服从；召回命中不代表回答正确。** `answer_quality` 保持 null。

同一 episode 的逻辑模型与工具额度跨所有阶段共享，不随新 thread 重置。当前 runner 只接受 scripted gateway，Provider 尝试为 0；这不替代真实模型下的 Provider 限额验证。写入失败保留 partial / violation，不能用 memory off 的预期不可用行为掩盖 memory on 故障。

应用的显式记忆操作当前返回 `partial / memory_updated` 控制结果，关闭时为 `partial / memory_unavailable`，逐轮原样保留；episode 的 completed 只表示控制流程走完，必须同时查看 violations，不能将它叫“模型任务正确”。

报告：记忆对照：`../../tmp/memory-lifecycle-20261002/report.md`（本地实验留样），逐轮 SQLite 状态、实际召回与模型轨迹：`../../tmp/memory-lifecycle-20261002/memory_records.json`（本地实验留样）。

## 四、追踪结论更正

首轮报告曾建议“检查已抓取的 Store 证据为何未进入 outcome”。本轮追踪完整 `tool_results` 与工具参数发现：三个研究分支重复抓取 Threads / Checkpoints 入口，**从未抓取 Store 摘录**。这不是 Store 原文在存储或导出时丢失，应归类为检索覆盖与停止判定问题。

因此本轮未改证据存储逻辑，也未把 gold 资料补进旧回答或评分。本轮没有修复检索策略覆盖不足和逐条引用语义检查；原始 Faithfulness=0.48 仍有效。

## 五、可复现与验证

从 `backend` 目录执行以下离线命令；新输出路径用于新实验，原路径加 `--resume` 用于完全相同身份的复用：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.memory_runner --out ../tmp/memory-lifecycle-20261002
.venv/Scripts/python.exe -m deeptrace.eval.memory_runner --out ../tmp/memory-lifecycle-20261002 --resume
.venv/Scripts/python.exe -m deeptrace.eval.compare_cli --input ../tmp/real-pilot-20261002/quality_eval.json --scores ../tmp/real-pilot-quality-20261002/quality_scores.json --metadata src/deeptrace/eval/data/real-pilot-v1-analysis-card.json --out ../tmp/real-pilot-comparison-verified-20261002
.venv/Scripts/python.exe -m pytest -q -m "not real"
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
```

统计命令已有非空输出时会拒绝，不会覆盖。记忆结果支持逐 episode 落盘、严格身份续跑；未完成 claim 需要人工检查，不能自动重发。真实首轮数据的离线分析不受当前生产源码改变影响，但研究本身不能用改变后的源码续跑旧身份。

记忆实验身份：`25d2f8d4313b8270faec30508cf8bcb86f66eeb688563f7d9c81a006e7e05df0`。

记忆结果 SHA-256：`d136e32b8b453695a4091199f7b57075681e36ce635722e56cd9a6fa94a58606`。

153 个源码、依赖和数据文件已复制到该实验 `source_snapshot`，逐文件校验 manifest 哈希，不含 `.env`。原真实研究与 Ragas 评分文件哈希仍分别为 `7011c0bc…` 与 `ca483928…`，原始结果未变。记忆续跑未执行新 episode，结果字节一致。

验证：全项目离线回归 **670 passed / 2 real tests deselected**；独立评分环境 **28 passed**。Ruff 对修改源码检查 E/F/I/UP/B/SIM/C4（排除既存 C420），新增/修改测试检查 F/I，通过。按 TDD 先复现截断、缺失/重复统计、错误身份与写入故障，再修复；按代码审查技能做正确性、简单性、架构、安全、性能审查。补充安全/性能清单文件缺失，使用该技能主文件检查项作为替代，没有引入新依赖或服务。

测试不是任务样本数；脚本结果不能冒充真实 API 验证。本轮真实 API 新增数为 **0**，旧正式实验的 30 次研究 + 16 次评分不变；旧离线 RED 阶段意外触发事件的未知用量仍单独披露，不并入正式计数。

## 六、还需完成的验收

30 道有治理的资料题及 12/18 切分、5 道公开任务、真实模型下的记忆收益与语义召回、逐条引用语义评分、至少十对题的人工盲评、CI 和完整真实矩阵仍未完成。下一轮先补数据治理及离线检查，再确认新的真实校准范围和额度；旧批次数值余额不自动授权新增实验。
