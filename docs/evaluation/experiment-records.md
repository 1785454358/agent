# Agent 实验运行与质量评分

这套工作流用本地文件保存实验，不新增服务。生产环境负责运行 Agent，独立 Ragas 环境负责评分。代码接入和离线测试通过，不代表真实任务质量达标。

## 已接入的边界

1. `manifest.json` 固定数据、源码（含未跟踪实现）、依赖版本、模型、Provider 路由哈希、上下文配置、预算和样本 ID。凭据不导出。
2. 发起请求前同时预留运行与批次额度。SDK 内部重试关闭；应用网关重试、评分器结构化生成请求均计入相应 Provider 尝试限额。
3. 先创建 claim，再执行；每个结果单独原子落盘。完整答案、实际证据正文、输入/输出消息、工具结果、错误类别和 usage 保留。
4. `--resume` 只在相同实验身份下复用已完成记录，包括已完成的失败记录，不把失败删掉重新跑。
5. 工具请求轨迹通过 JSON v1 提交规则评分；答案质量通过 JSON v2 交给独立 Ragas 0.4.3，生产 OpenAI SDK 不降级。

“Provider 尝试”是 SDK-facing 调用次数，不等于已经抵达服务器的 HTTP 请求数，更不等于账单收费次数。请求失败、取消、usage 不完整时，总 Token 为 null，另保留已观察到的 Token 小计；费用没有可靠价表时为 null。

## 真实资料与对照

首轮数据为 `real-pilot-v1`：1 道开发校准题，LangGraph 官方文档的两个真实摘录，固定到提交 `23961cff61a42b52525f3b20b4094d8d2fba1744`。原始文件哈希、摘录哈希、MIT 许可、来源核验状态保存在 data card 中。

资料本身是真实的，但工具后端为冻结本地语料，**不是实时联网搜索评测**。摘录来自同一份文档，不按两个独立来源计数。参考答案只交给评分器，不进入 Agent 输入。

Baseline 使用原问题搜索、抓取前至多三条结果，再通过项目正常回答链路生成带引用答案。Harness 使用 Workflow 的规划、工具研究、评估和回答链路。双方相同模型、资料、输出模式和上限，主对照关闭长期记忆。Baseline 不是商业 DeepResearch 产品，不能据此宣称超过市面产品。

## 复现命令

从仓库的 `backend` 目录执行；真实命令需要配置 `.env`，会发生外部付费调用。这里的上限属于已确认的小规模校准，不自动授权完整矩阵。不要更换新输出目录反复运行以绕过批次额度。

```powershell
.venv/Scripts/python.exe -m deeptrace.eval `
  --model real --modes workflow --include-baseline --repeats 1 `
  --response-mode report --max-model-calls 40 --max-tool-calls 24 `
  --max-provider-attempts 80 --max-batch-model-calls 80 `
  --max-batch-provider-attempts 160 --agent-iterations 12 `
  --max-output-tokens 2048 --run-timeout 240 `
  --dataset src/deeptrace/eval/data/datasets/real-pilot-v1.jsonl `
  --corpus src/deeptrace/eval/data/corpora/real-pilot-v1.jsonl `
  --run-prefix real-pilot-20261002 --out ../tmp/real-pilot-20261002
```

原命令加 `--resume` 验证复用；源码、数据、参数改变会拒绝续跑（独立评分环境的测试源码也参与实验身份）。本轮已在源码变化前验证；之后仅修正了一处评分测试的 import 排序，原始版本已在 `source_snapshot` 中保留。若要精确复现旧身份，应在独立副本使用快照，不覆盖现有工作区。先保存所有旧记录，再安排新实验身份；新实验不是免费重试。

```powershell
.venv-ragas/Scripts/python.exe evaluation/ragas_quality.py `
  --input ../tmp/real-pilot-20261002/quality_eval.json `
  --out ../tmp/real-pilot-quality-20261002 `
  --max-provider-attempts 24 --env-file .env
```

质量评分同样支持原命令加 `--resume`，逐指标缓存包括所有输入、参考答案、证据、评分模型、依赖和适配器源码哈希。已经完成的错误评分也保留；需要重评时应显式安排新评分身份和额度，不重跑 Agent。

## 指标含义与局限

| 指标 | 输入 | 口径 |
| --- | --- | --- |
| Ragas Faithfulness | 原问题、完整回答、实际选入研究结果的证据正文 | 回答陈述被证据支持的比例；不是引用逐条支持率 |
| Ragas FactualCorrectness | 完整回答、评分侧参考答案 | 原生 F1；参考事实不全会影响结果 |
| Ragas AgentGoalAccuracy | 原问题和最终回答、期望结果 | outcome-only 视图；不是虚构的跨分支工具会话 |
| 工具 Accuracy / F1 | 实际模型工具请求、人工/任务参考调用 | 无参考调用即 N/A；固定程序 Baseline 不冒充模型工具决策 |
| 引用有效性（已有工程指标） | 最终回答与提供的引用来源 | 引用格式/来源约束检查；不等于引用语义正确 |

不设随意加权总分或未经校准的行业通过线。模型裁判不是人工标注；相同模型自评需明确披露。没有证据、参考答案、有效指标输出或完整输入时保留 N/A/error，不填 0 或假定通过。

单题对照可以发现接入、资源和回答差异，但不能估计总体提升、置信区间或显著性。后续统计要先在题内聚合重复，再按题配对；同题重复不能当新增独立题。开发校准与测试成绩必须分开。

## 中断、安全与人工复核

硬进程崩溃可能留下 `.writer.lock` 或 claim。自动续跑会拒绝此类模糊状态，需先人工核对进程、服务商请求和原始文件，不能直接删除后重新付费。这里尚未实现自动 stale-lock 恢复。

离线 eval 测试禁止 HTTP。一次 RED 阶段曾在预算预检落地前触发旧 CLI 的真实模型入口，已停止对应测试进程；请求数、Token 和费用无法确认，没有可用比较结果，不能混入正式实验分母。

默认关闭云追踪和 Ragas 遥测。只使用公开资料及测试身份，不上传私有用户历史。记录虽不含 API key，完整提示词和证据仍可能含任务内容，不应将私有实验目录公开上传。

目前来源核验为 Agent 核验，不是独立人工金标。完整验收仍需：30 道治理后的资料题及开发/测试切分、公开任务子集、记忆 on/off 多轮实验、引用逐条语义复核、足够的配对统计和至少十对题的盲评。首轮校准不将这些项目冒称完成。

## 续建接口

已加入 `--response-max-chars`，为 Baseline / Harness 设置相同的初稿与纠正长度边界，写入实验身份。它不是 Token 收费硬限制；真实模型调整后尚未重新验证。

配对分析与 12×on/off 受控 SQLite 记忆实验已实现。分析同时核对评分目录的 `identity.json` 与完整输入哈希；记忆 runner 当前仅允许 scripted，不能称为真实语义记忆成绩。命令、实测和完整验收剩余项见 [2026-10-02 续建报告](benchmark-continuation-20261002.md)。
