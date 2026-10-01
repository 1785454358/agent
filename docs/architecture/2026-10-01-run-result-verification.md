# 统一运行结果：实施与验收

日期：2026-10-01。

## 已实施

应用服务返回 ApplicationRunResult，包含权威 Harness 终态、原始研究/回答结果、停止原因、研究执行步数、未解决问题和引用来源。fresh、continuation、resume 使用同一提取边界。

Local 和 Worker 直接映射结果，不再通过 response.partial_reason 猜测整体成功，不再重复查询来源。研究受限但回答可用时仍保留 partial；Worker.steps 不再固定为 1；CLI 改为“执行步数”。

来源读取保持 workspace 隔离和引用顺序；只读 metadata，有引用查询一次，无引用不查询。研究未完成的原因优先于回答原因；研究 completed 后的回答失败仍保留整体 partial。复制 gaps，避免应用摘要与原研究列表相互污染。

异常、取消、身份校验、checkpoint 恢复和已有控制响应语义不变。未增加 schema、运行服务或依赖；用户原有配置、引用和评测修改未覆盖。

## 离线验证

- TDD 首先观察状态丢失回归失败，再实现返回契约；随后观察 Local/Worker 旧适配失败，再迁移两端。
- 应用/Local 专项最初 34 passed；应用/Local/Harness/集成专项 60 passed。
- 全仓首次发现 API 夹具仍返回旧 ResponseOutcome，显式迁移夹具后通过；没有把 failed 的预期改成“通过”。
- 最终 `.venv/Scripts/python.exe -m pytest -q -m "not real" --tb=short`：**562 passed, 2 deselected，49.49 秒**。其中包括工作区现有未提交评测代码，仅验证其兼容性，不将这些文件纳入本次提交。
- 修改的生产文件 Ruff 全规则、测试 I/F、14 个文件格式检查通过；git diff --check 通过。
- 审查了状态权威、原因优先级、来源租户边界、单次元数据查询、恢复不重复研究和适配器生命周期；原有 broad exception 保留在观察者隔离/公开运行失败边界，注明理由，不扩展吞异常行为。

## 真实 API 首轮：3 轮预算，端到端未通过

执行命令：`.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -s -m real --tb=short --show-capture=no`。

单题：“LangGraph 的 checkpoint 机制是什么？”；独立 run/thread、临时 SQLite、lexical 记忆、每分支最多 3 轮、输出最多 1024 token、180 秒超时、最多 12 次逻辑模型/工具调用。没有使用生产 MySQL/Redis、历史运行数据或向量目录。finally 已关闭资源。

**结果：1 failed，26.70 秒；partial / no_sources，11 个研究执行步骤，0 个引用来源。**

失败发生在带引用答案断言；此前 ApplicationRunResult 与真实 Harness snapshot 的 status、研究/回答结果、身份、steps、gaps、reason 一致性断言均通过。不能将这次结果表述为“真实端到端已通过”。

对已保存 checkpoint 的只读调查发现：规划器分出 3 个研究分支，各分支 iteration=3、errors=[]，工具消息依次为 write_todos、search_web、write_todos；搜索返回 ok=true，但尚未调用 fetch_page。最终保留 agent_exit:iteration_limit 与 no_evidence_collected。诊断支持“测试轮次预算在抓取之前耗尽”，不支持“模型/Tavily 服务不可用”或“引用来源读取故障”。

没有为了获得通过结果提高限额、重跑真实流程或跑全题集。下一轮建议审阅预算与轨迹效率：规划辅助动作占用有限迭代，最低可执行路径需要先校准；扩大每分支上限也必须保留全局模型/工具上限。

逻辑调用数不等于网络重试数；本次失败前打印摘要尚在末尾，因此不能事后声称已得到完整计费统计。测试已将摘要打印移动到引用断言之前，方便后续失败诊断，此诊断改动尚未再次调用真实 API。执行步数不解释为 LLM 次数，Token 和费用仍未知。

## 新增 Agent 评测范围

设计提案见 `docs/superpowers/specs/2026-10-01-agent-evaluation-design.md`。推荐 Ragas 单主框架、pytest 工程回归、冻结题集、简单基线和记忆对照。尚未安装/接入 Ragas，也尚未执行框架真实 judge 或更大规模的 Agent 质量评测；待用户确认书面选型后实施。

## 用户要求加额后的真实复验（2026-10-01）

用户明确要求提高预算、争取端到端通过。检查实际 Settings.from_env 发现项目配置为 agent_max_iterations=8、openai_max_tokens=16000、max_tool_calls=30；原 3 轮 / 1024 token 是 smoke 的保守测试覆盖，不是生产配置。这一轮只调整测试，不修改 .env 或生产默认值。

### 6 轮 / 1024 输出 token

限额：最多 32 次逻辑模型调用、24 次工具调用，240 秒。

结果：**1 failed，68.11 秒**；partial/insufficient_evidence，20 个研究执行步骤，4 个引用来源，21 次逻辑模型调用，7 次逻辑工具调用。

三个分支均 iteration_limit，任务清单分别完成 3/4、1/3、3/4；无工具错误。Workflow gaps 包括 evaluation_unavailable，所以不能把这个退出原因直接解释为评估器判定真实资料不足。一次复用已抓取资料的 evaluator-only 诊断遇到连接错误，未取得可用于判断输出截断的响应；未重跑搜索/抓取。

### 8 轮 / 2048 输出 token

限额仍为 32 次逻辑模型 / 24 次工具调用，240 秒；增加评估器 finish_reason/schema error 和工具成功摘要。

结果：**1 failed，98.02 秒**；partial/incomplete_plan，23 个研究执行步骤，3 个引用来源，26 次逻辑模型调用，9 次逻辑工具调用；3 次搜索、6 次抓取均成功。

评估器 finish_reason=stop、schema validation 无错误、sufficient=true。两个分支计划已完成；第三分支在 8 轮时完成 3/4 项，仅“总结形成完整回答”仍为 in_progress。不能绕过计划完成检查而改称 completed。此结果支持继续校准少量收尾预算，而不是把充分证据的 partial 当作完整成功。

离线复验：**562 passed, 2 deselected，53.25 秒**。真实 smoke 的静态 I/F 与格式检查通过；未修改任何生产实现或用户原有未提交评测/引用工作。

最后一次校准采用 12 轮、2048 输出 token、40 次模型 / 24 次工具逻辑调用和 240 秒；保留全量 Harness snapshot 一致性检查，并要求实际成功 fetch_page、有引用回答、status=completed、termination_reason=completed、response.partial_reason=None。结果在下节记录。

### 12 轮 / 2048 输出 token：轮次阻塞消除，另有评估契约问题

结果：**1 failed，91.72 秒**；partial/insufficient_evidence，22 个研究执行步骤，3 个引用来源，26 次逻辑模型调用、7 次逻辑工具调用。3 次搜索和 4 次网页抓取均成功。

只读 checkpoint 核实：三个研究分支分别在 7、8、8 轮结束，均为 completed，任务清单完成 3/3、4/4、3/3，无工具错误，已不再是 iteration_limit。整体 gaps 仅 evaluation_unavailable。

评估器 finish_reason=stop，但 WorkflowEvaluation 校验出现 **string_type**，这证明另有结构化输出契约问题，不能解释为 token 截断或继续加迭代额度便能解决。失败发生在整体 completed 断言，没有改状态或放宽验收标准。

没有执行第四次完整测试。测试诊断现进一步记录校验错误 loc 和 input_type（不输出原始输入），尚未再次调用 API。后续需修正评估输出契约/有限纠正；未在本轮暗中宽松转换字段、移除校验或将证据充足直接升级为 completed。

本轮 code-review-and-quality 自审：只有测试预算、诊断和验收标准改变，生产实现/配置未改；诊断不打印凭据、响应正文或出错字段原值；共享计数在 await 前增长，三分支仍共用总限额；测试的来源、真实 fetch 成功、状态和 snapshot 断言均保留。预算修订完成，端到端完成目标尚未达成，不能宣称通过。

## 评估契约修复后：真实端到端通过（2026-10-01）

用户确认“修复”后，按照已批准的 [评估契约设计](../superpowers/specs/2026-10-01-workflow-evaluation-contract-design.md) 实施。生产改动只在 Workflow 的 evaluate_node：替换原来不合法的 JSON 示意，增加明确字段类型、合法示例和完整 WorkflowEvaluation schema。保留原模型校验、来源过滤和完成标准。

只在 JSON/schema 校验失败时，通过既有 ModelGateway 纠正一次；不重新规划或调用搜索/抓取。纠正携带同一任务、约束和证据 ID，原始响应限制为 4000 字符、仅携带最多 10 条 type/loc 错误，每个字符串路径片段限制 200 字符，不携带错误输入值或异常文本。纠正数据以 JSON 编码，系统指令明确不得执行其中的指令。正确但 sufficient=false 的响应不重试，第二次格式仍错误则保持 evaluation_unavailable/partial。网关传输、上下文错误或取消不被当作格式问题吞掉。未新增依赖、框架、全局解析器或 Provider 专用能力，未修改用户评测模块、.env 或生产限额。

### 离线与静态验证

- TDD：先确认新增行为 RED（6 failed / 10 passed），再实现修复。
- 节点、研究图、响应退出门与 Harness slice 专项：**46 passed**。包含错误字段与非法 JSON 恢复、第二次失败降级、有来源但 sufficient=false 不重试、未知来源过滤、无来源不调用、原始输出有界、网关错误与取消传播。
- 全量离线：**573 passed, 2 deselected，51.84 秒**。工作区原有评测代码兼容，未纳入本任务改动。
- 生产文件 Ruff 全规则、测试 I/F、两文件格式与限定文件 diff 检查通过。
- code-review-and-quality 自审：没有把严格校验变为宽松转换，没有把充分性改为固定 true；有限循环最多两次模型调用，两个请求都保留系统指令/原始任务/当前约束；证据存储只查询一次，不增加工具或网络重试层。额外纠正算模型调用，不增加研究阶段 executed_steps（该阶段仍为 1）。

### 真实单题结果

执行命令与前轮相同：`.venv/Scripts/python.exe -m pytest tests/real/test_real_smoke.py -q -s -m real --tb=short --show-capture=no`。

预算保持 **每分支 12 轮 / 输出 2048 token / 总 40 次逻辑模型调用 / 总 24 次逻辑工具调用 / 240 秒**；独立 run/thread、临时 SQLite、lexical 记忆，未连接生产 MySQL/Redis。

**结果：1 passed，114.53 秒；status=completed，termination_reason=completed；5 个引用来源，23 个研究执行步骤，28 次逻辑模型调用，9 次逻辑工具调用。** 3 次 search_web、6 次 fetch_page 均成功，unresolved_gaps=[]。

本次评估器首次 finish_reason=length，校验错误为 json_invalid；一次纠正后 finish_reason=stop、validation_errors=[]，最终完整成功。这里的截断证据仅解释本次首次响应，不能倒推上一轮 string_type 的具体字段或原因。

验收保留并通过：ApplicationRunResult 与 Harness snapshot 的 status、research_outcome、response_outcome、身份、steps、gaps、reason 一致；实际成功抓取网页；有引用来源与 cited_evidence_ids；非空回答含 [1] 引用；整体 completed、termination_reason=completed、response.partial_reason=None。没有提高本轮预算、修改成功标准或人工覆盖结果。finally 已关闭资源。

局限：这是一次 Workflow 真实单题工程 smoke，不代表多题质量评测、其他模式、生产向量记忆或 MySQL/Redis 集成全部通过；尚未接入 Ragas judge。逻辑模型调用数不等于底层 HTTP 重试次数；Token 实际消耗与费用未统计。模型仍可能产生格式错误，本改动将恢复限制为一次，无法恢复时继续诚实返回 partial。
