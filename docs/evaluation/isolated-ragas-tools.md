# 独立 Ragas 工具评测

这一版评测“模型是否请求了正确的工具和参数”，不评判答案真假、完整任务目标或记忆收益。工程终态、模型请求、实际 ToolGateway 结果与工具指标分开记录。

## 环境与运行

从 `D:/Dev/Projects/agent_new/backend` 执行。生产环境没有安装 Ragas；其 OpenAI SDK 仍为 3.6.0。独立环境固定 Ragas 0.4.3、langchain-community 0.4.1，并在 requirements.lock 固定传递依赖。0.4.2 移除了 Ragas 导入所需的 VertexAI 模块，因此不能只固定 Ragas 而任由传递依赖漂移。

```powershell
uv venv .venv-ragas --python .venv/Scripts/python.exe
uv pip install --python .venv-ragas/Scripts/python.exe -r evaluation/requirements.lock
```

已有虚拟环境不必重新创建。独立评分脚本不导入 deeptrace，也不安装整个生产项目；不要在生产 `.venv` 里安装这些评测依赖。评分前强制关闭 Ragas analytics 和 LangSmith tracing。

先用生产环境生成一次离线研究记录，再用独立环境评分：

```powershell
.venv/Scripts/python.exe -m deeptrace.eval --model scripted --modes workflow --dataset evaluation/data/tool-contract.jsonl --out ../tmp/ragas-tool-contract-run
.venv-ragas/Scripts/python.exe evaluation/ragas_tools.py --input ../tmp/ragas-tool-contract-run/tool_eval.json --out ../tmp/ragas-tool-contract-score
```

这个单题数据仅用于工具契约联调：参考调用依据固定语料和脚本行为手工列出，不包含 gold answer。它不是人工审过的研究质量保留集。原来 smoke 的三题与语料不改；它们尚无人工参考调用，因此用默认题集导出并评分时应显示 N/A，而不是自动从 Agent 轨迹生成 gold。

## 输出与语义

生产命令保留原来的 report.md、records.json，新增 tool_eval.json。记录 status/reason/steps/gaps 来自 ApplicationRunResult，不再由研究 reason 推断整体完成；研究完成但回答失败仍为 partial。单个顶层运行异常保留 failed 记录、继续后续样本；取消继续传播。CLI 遇到非 completed 或 legacy judge 失败返回 1，输入/框架错误返回非零。

轨迹包含：

- model_turns：每次已返回模型响应的角色、可见研究查询分支和原始工具请求，包含未知工具与非法参数请求，不保存模型解释或回答正文。
- tool_executions：经过真实 ToolGateway 的 caller/request/call 身份、参数、成功/失败、拒绝分类、cache/replay；网关异常记录类型后原样传播。
- tool_observations：后续模型输入中实际收到的工具结果元数据，按查询分支与 tool_call_id 去重，包括 ToolGateway 前的本地拒绝，不复制 preview/body。它不是每个终止分支末轮的完整观察日志：未再送入模型的本地拒绝可能没有该观察记录，但原始请求仍保留。

模型接口没有 caller 身份，因此模型分支使用输入中的研究查询标签；真实 caller 身份仅来自 ToolGateway，不伪造模型请求与哈希执行 ID 的一一连接。记录发生在评测包装层，不改变生产 Agent 决策。

评分输出 tool_scores.json 和 tool_report.md。逐样本/逐指标使用 ok、not_applicable、error；value 在 0–1，未测/失败为 null，理由与错误类别另列。汇总同时显示测量覆盖率、错误数、未适用数以及系统未完成样本数；均值只使用已测值，不用 0 填充缺失。

`reference_tool_calls=null` 表示未标注；空数组表示人工明确“不应调用工具”，二者不同。Ragas 0.4.3 对预测和参考均为空时，Accuracy=1、F1=0；保留框架语义，不改造成一致的漂亮分数。

默认工具范围在请求与参考两侧都只排除内部 write_todos，并分别显式报告排除数量；未知工具仍计入。Accuracy 可检查顺序和参数，F1 是名称/参数的集合匹配，重复同一请求可能 F1=1，但请求次数增多或 Accuracy 下降。实际执行失败不会被过滤，也不能靠请求 F1 得分掩盖。

多分支默认忽略并发调度顺序；单分支任务可在题目中设置 strict_tool_order=true。跨分支严格顺序无法从目前的轨迹确定，因此 Accuracy 明确未测，F1 仍可计算；不按某次并发完成顺序编造 gold。

原五维 1–5 judge 保留，标识 legacy_custom，与 Ragas 0–1 指标分开；未请求评审或所有评审失败时为 null/N/A。评审错误只记录异常类型，不导出凭据或 provider 错误原文。没有用自定义 judge 冒充 Ragas。

导出包含题目/语料内容 SHA-256、Git revision/dirty、model_kind 与语料工具标识；评分另记录框架版本及输入哈希。当前不包含完整的真实模型配置、Token/费用统计，也未实现评分缓存；dirty=true 的实验不能声称只凭 commit 即完全可复现。

## 验证

```powershell
.venv/Scripts/python.exe -m pytest tests/eval -q
.venv-ragas/Scripts/python.exe -m pytest evaluation/tests -q
.venv/Scripts/python.exe -m pytest -q -m "not real" --tb=short
```

本轮没有调用真实 API、Ragas LLM judge、向量检索或生产 MySQL/Redis。尚未实现 AgentGoalAccuracy、Faithfulness、FactualCorrectness、简单基线、12 题冻结质量集及 6 组记忆对照。这些是后续质量评测切片，不是本次工具契约联调的结论。

接口依据：[Ragas Agent metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/agents/)。本地代码实际调用 collections 的 ToolCallAccuracy/ToolCallF1，而不是复制公式或仅检查 SDK 能导入。

## 本轮验收记录（2026-10-01）

- TDD：运行契约先 5 failed 后通过；未知值/失败报告先 5 failed 后通过；工具框架适配先 12 failed 后通过；观察记录补充先 2 failed 后通过；输入类型与范围一致性补充先 4 failed 后通过。
- 主项目评测专项：29 passed；主项目全量离线：585 passed, 2 deselected，49.68 秒。独立 Ragas：18 passed，4.20 秒；新进程中的禁止网络连接用例另单独验证。
- 独立环境 uv pip check：101 个包兼容；生产 OpenAI=3.6.0、langchain-core=1.6.1，均未变动。
- 实际两进程契约联调：单题 Workflow completed，7 次模型调用、2 次实际 ToolGateway 请求、6 个研究步骤；Accuracy/F1 均 1.0。报告保存在 `tmp/ragas-tool-contract-score/tool_report.md`。
- 原三题 Workflow 的未标注对照：工程运行均 completed；两个 Ragas 指标均 0/3 已测、覆盖率 0%、均值 N/A，未用 Agent 输出伪造 reference。报告保存在 `tmp/ragas-unannotated-score/tool_report.md`。
- 在生产环境误执行独立评分命令时显式失败，提示使用 .venv-ragas；没有回退自定义指标。
- Ruff 全规则（改动源文件）、测试 I/F、12 个文件格式检查通过。code-review-and-quality 自审覆盖状态权威、失败留样、取消传播、并发换序、请求/执行分离、未知值、内部工具两侧一致排除与网络隔离；未改变生产运行时、引用实现或用户其他未提交文件。

本轮代码保持在工作区，未把用户原有整套未提交评测资产加入提交；仅此切片完成，不把后续质量与记忆评测标为已完成。
