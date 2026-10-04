# 评测数据治理：30 道真实资料题与 5 道公开任务

本轮完成可复现的数据资产和运行入口，没有新增付费研究或评分调用。**数据准备完成不等于质量实测完成**：真实模型结果仍是此前的 1 道开发校准题 × Baseline/Harness；记忆结果仍是 24 个受控脚本变体。

## 1. 真实资料题

资产：[bundle.json](../../backend/src/deeptrace/eval/data/benchmarks/research-v1/bundle.json)。14 份未改写的官方 MDX 文档，30 道 Agent 编写的问题/参考答案，47 处逐字来源片段。

| 类别 | 开发 | 测试 | 考察内容 |
| --- | ---: | ---: | --- |
| single_hop | 2 | 3 | 单一来源中的机制与接口 |
| multi_hop | 2 | 3 | 跨文档组合 State、Context、Store、HITL 等 |
| comparison | 2 | 3 | API、持久化、上下文管理、结构化输出的取舍 |
| version_boundary | 2 | 3 | Python/JS、包版本和功能支持边界 |
| conflicting_evidence | 2 | 3 | 看似冲突的语言、输入类型和语义范围差异 |
| insufficient_evidence | 2 | 3 | 不编造文档未提供的性能、费用与安全保证 |
| 合计 | 12 | 18 | 30 题 |

开发集使用 LangGraph runtime 来源组，测试集使用 LangChain Agent 来源组；来源 URL 和组不跨切分。两组属于同一发布方，概念相关，**不是跨发布方或广泛主题泛化测试**。正式测试集冻结后，不应根据其运行结果反复调整提示词；若已经调优，应更换新的保留集并记录版本。

每题保存问题、参考答案、成功要求、不确定性规则、来源 ID、行号、逐字引用、审查类型与时间。参考中的部署建议是建议，不是项目已实现的能力。

来源固定为 [LangChain 官方文档提交](https://github.com/langchain-ai/docs/tree/99dd9a9e38d59b9bff54354f6c3ef790c1be946d)，保留该提交的 [MIT 许可](https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/LICENSE)。每份文件都有完整字节 SHA-256、上游路径、提交、URL 和获取时间；本地保留完整许可，MDX 不执行其中的 import 或代码。

校验会拒绝文件改动、引用不匹配、越界路径、绝对路径/符号链接、重复 ID、跨切分来源组、错误题数、错误许可哈希及伪装人工审查。bundle 最大 4 MiB，单来源最大 2 MiB；来源 URL 必须与固定提交和上游路径一致。哈希验证不是数字签名，不证明供应方身份或语义正确性。

审查状态是 **source_verified=30 / human_reviewed=0**。这是 Agent 对来源的核对，不是人工金标准。逐字引用验证也不自动证明事实蕴含；“证据不足”的片段描述文档范围，缺失判断仍需要人工复核。

当前冲突类别是范围限定型冲突，不覆盖多家独立来源真正互相矛盾的判定。MDX 有语言分支及外部 snippet 链接，未导入的 snippet/链接页不算本地证据。版本题以固定快照为准，不代表项目当前安装版本已经支持该功能。

## 2. 防止参考答案泄漏

`assets.py` 校验 scoring-side bundle，投影成现有 EvalQuestion/Corpus。检索仅收到原始文档及公开 ID/标题/URL；不把 gold、成功要求、审查信息或来源片段标签写入正文/tag。

gold 仍在评分 DTO 中，runner 只把用户问题交给应用路径。回归测试实际跑正常应用/基线：更换参考答案和评分参考 URL 后，回答、模型/工具轨迹与实际证据完全相同；哨兵内容不出现在 Agent 记录中。该测试检验已覆盖路径，不是对未来任意修改的无泄漏证明。

CLI 新增 `--benchmark` 和 `--split dev|test`（默认 dev），不能混用显式 `--dataset/--corpus`。数据预检在凭据读取、模型构建与实验目录创建之前完成；bundle 身份及 split 进入 manifest，改变切分不能原地续跑。质量导出保留原 v2 格式，新增评分侧数据审查数量/局限说明。

每个切分还导出与实际投影一致的数据集/语料哈希及 analysis card，供配对分析分组，避免把开发、测试、公开任务混合统计。源码身份现在包含 MDX，Windows Git 检出也通过限定路径的 `.gitattributes -text` 保留冻结文件字节。

## 3. 公开 DeepResearch Bench 子集

来源是 [官方 query.jsonl](https://github.com/Ayanami0730/deep_research_bench/blob/f2735b5c3636759c22f9e936c0232de8bf545b67/data/prompt_data/query.jsonl)，固定提交 `f2735b5c3636759c22f9e936c0232de8bf545b67`，保留该提交的 [Apache-2.0 许可](https://github.com/Ayanami0730/deep_research_bench/blob/f2735b5c3636759c22f9e936c0232de8bf545b67/LICENSE)。未读取或导入上游参考答案、模型测试输出与评分参考文件。

选择规则：[selection.json](../../backend/src/deeptrace/eval/data/public/drb-v1/selection.json)。先审查全部 Software / Software Development 候选，冻结工程系统/产品实现范围及逐题排除理由，再按原始 ID 升序取前五个符合者：**17、19、20、66、68**。这是目的性工程子集，不是随机抽样，不代表整个 DRB。

原始 ID、语言和题目文本逐字保留。20 题的“Anthropic 最新发布”来自原题，并不作为本项目核实后的事实；未来研究应核对前提及时间范围，不能把题目措辞当证据。

公开导入器验证原始 100 题文件、许可、候选覆盖与前五规则，输出原题和 audit。它**不执行研究**，也未连接冻结本地语料 runner；实时搜索/抓取适配器仍未实现。没有 reference 时事实正确性为 N/A，不补 0，也不反向根据 Agent 输出生成 gold。

这不是官方 RACE/FACT 评分或榜单结果，尚无这 5 题的 Agent 输出/质量分数。

## 4. 离线复现

从 `backend` 执行；输出目录必须为空/新建，以下命令不调用 Agent 或裁判：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval.assets --out ../tmp/research-assets-audit-new
.venv/Scripts/python.exe -m deeptrace.eval.public_assets --out ../tmp/drb-assets-audit-new
.venv/Scripts/python.exe -m pytest -q -m "not real"
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
```

研究入口接入的离线示例（脚本模型仅用于链路检查，不能作质量结论；本轮未执行 30 题矩阵）：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval --benchmark src/deeptrace/eval/data/benchmarks/research-v1/bundle.json --split dev --model scripted --modes workflow --include-baseline --response-max-chars 600 --out ../tmp/research-dev-plumbing-new
```

真实实验仍需新的题目/重复次数/模型与批次额度确认，旧 160 次研究与 24 次评分上限不自动成为本轮新增授权。尤其要先检查长 MDX 的检索覆盖、上下文预算和裁判输入限制，不能为提高分数按 gold 位置裁剪运行资料。

本轮审计：30 题与两个切分的 audit：`../../tmp/research-assets-audit-20261002/audit.json`（本地实验留样）、开发 analysis card：`../../tmp/research-assets-audit-20261002/analysis-dev.json`（本地实验留样）、测试 analysis card：`../../tmp/research-assets-audit-20261002/analysis-test.json`（本地实验留样）、公开导入 audit：`../../tmp/drb-assets-audit-20261002/audit.json`（本地实验留样）。

研究 bundle 规范内容身份：`e8dff03c5a52083bd73f3a0f7584130a641df850cc17db877eab11beea31b6de`。

bundle 文件字节 SHA-256：`1c6a16f39aeb5bfcbef8498a864a5aa2291df6d21e4ca1146b94e2bca97de3b5`。

公开 selection 规范内容身份：`d5c245867d5c8754d3ea35be09bfbc0d5bfcafa96a1bd1f92800a7aa2d1e7868`。

旧真实研究、旧评分和旧记忆记录哈希仍分别为 `7011c0bc…`、`ca483928…`、`d136e32b…`，原始失败记录未重写。新源码/资产会改变未来实验身份，不能拿新版本续跑旧研究；保留快照用于复现与只读分析。

## 5. 验收边界与面试表达

按 TDD 完成缺失入口、文件/引用损坏、gold-invariance 与 Git 字节保留回归；按 code-review-and-quality 检查正确性、简单性、架构、安全和有界处理。沿用既有 runner/评分环境，没有新增服务、生产依赖或改动生产数据库。数据治理、公开导入分成两个模块；公开任务不硬塞本地研究流程。

本轮新增付费 Provider 调用 **0**。已有真实小试和脚本记忆检查不替代完整基准。

最终验证：全项目 **702 passed / 2 real tests deselected**；独立评分环境 **28 passed**；本轮核心文件的 Ruff E/F/I/UP/B/SIM/C4（排除既存 C420）与测试 F/I 均通过，Git diff whitespace 检查通过。Ruff 使用已缓存的离线工具，不改变项目依赖。两份审计文件均已生成，旧正式结果的完整哈希与前轮一致。

可在简历加：“构建版本化研究评测数据集，覆盖六类能力的 30 道官方真实资料题、12/18 来源组切分与 47 处可定位引用；实现来源哈希、许可、评分参考隔离及公开 DRB 5 题子集治理。”

被问“有真实数据吗”时区分：资料是真实官方原文；问题/参考是 Agent 编写并核对、待人工审查；真实模型目前测了 1 道开发对照题。不能将数据集题数写成实测题数，或把离线工程测试数当成功率样本数。

仍待完成：CI、真实多题校准与最终冻结测试运行、公开任务 live-web 适配/执行、真实语义记忆收益、逐条引用语义指标和至少十对题的人工盲评。当前是已具备治理和复现能力的评测工程基础，不宣称完整成熟评测全部验收通过。
