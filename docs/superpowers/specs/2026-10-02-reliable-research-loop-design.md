# 可靠深度研究 Harness：三模式设计，以 Plan-and-Execute 为主

状态：用户于 2026-10-02 确认本设计，进入子项目 A 的实施计划编写。固定口径为“三种模式都测试、Plan-and-Execute 为主、Answer 主指标 / Report 独立验收”；尚未修改运行代码、未新增付费调用。

本版取代此前“先为 Workflow 新增外层补查”的草案。目标是公开网页研究的真实可用性，不是只提高单题裁判分数。调研、现状证据和本轮测试结果见 [调研与覆盖审计](../../evaluation/research-harness-design-review-20261002.md)。

## 1. 目标与范围

采用增量改造现有 LangGraph Harness：先打通正文读取、证据充分性检查和有界补查。第一版以个人/单用户、本地使用、公开网页为范围；不绕过登录、验证码或付费墙，不承诺多用户服务。现有 assembly 固定 local-user/local-workspace，正式多用户部署必须另补身份认证。

保留现有三种策略、API、Tool/Model Gateway、预算、缓存、Ledger、Checkpoint 和记忆。Plan-and-Execute 是主质量验收模式，公用正文视图与回答约束覆盖全部策略；不删除其他模式、不引入第四种策略，也不复制一个新研究框架。

| 模式 | 定位与保留的行为 | 本次增强 |
| --- | --- | --- |
| Plan-and-Execute | 顺序执行计划，已有有界 replan，默认最多 2 轮 | 正文评估、明确缺口输入、已有证据复用、补查进展与停止判定 |
| Multi-Agent | 监督者并行委派，已有 follow_up，默认最多 1 轮 | 同一证据标准、非重叠委派、缺口定向 follow_up、并行恢复验证 |
| Workflow | 固定规划 → 研究分支 → 评估 → 输出；分支 Agent 内仍可调整搜索 | 正文评估与诚实 partial，不强制新增外层补查 |

不自动改 API 默认模式，也不自动在模式之间切换。本阶段保留 Plan-and-Execute 每批最多 6 项、Multi-Agent 最多 5 个研究员的现有代码上限；研究方向尽量少而明确，不要求把上限全部用满。三模式共享外部资源上限，模式内部不同调度上限必须出现在实验配置中。

## 2. 已确认的缺口

- `tools/adapters.py` 的 fetch_page 保存正文，但 preview 仅含 URL、标题和时间；`harness/agent_tools.py` 只回填 preview 与 Evidence ID，研究员没有原文读取工具。
- 三种策略的充分性评估都只拼接 Evidence ID、标题、URL，没有读取正文。因此 schema 正确和 confidence=1 不能证明证据充分。
- Workflow 固定 evaluate → finalize，没有外层补查属于模式定位，不作为缺陷。Plan-and-Execute/Multi-Agent 已有有界重规划，但新任务提示没有明确带入 evaluator 的 reason、unresolved_gaps 和正文支持的发现，补查容易偏离真正缺口。
- Plan-and-Execute/Multi-Agent 的零证据分支目前直接进入 finalize；新设计允许在可恢复、仍有额度的情况下沿已有补查路径提出替代方向，不能将所有零证据都当作值得无限重试的错误。
- 当前 unresolved_gaps 使用累积 reducer；补查后完成也可能携带早期已解决缺口。新的当前覆盖状态必须与历史诊断分开。
- AsyncWebFetcher 默认只保留前 20000 字符；回答模型的选段器无法找回此前丢失的尾部。
- 回答验证只检查编号/来源合法性，不检查语义支持。旧真实校准三个分支重复抓取 Checkpoints，未抓取 Store，却写出 Store 结论。

已有能力不重复建设：EvidenceStore 正文/分块、URL 安全、Tool Ledger、传输重试、取消、模型输入 token 预算、按问题选段、独立 Ragas 评分与实验身份绑定。以上不等于所有部署路径都具有相同保证：本地工具账本仍为内存实现；本地重启会把运行中任务标为 interrupted，不自动恢复；生产 assembly 没有评测入口那样的全运行 Provider 尝试数封顶包装。恢复与预算部署差异在第五节独立验收。

## 3. 参考与路线选择

调查日期：2026-10-02。以下为官方文档/源码参考，不采信宣传性质量保证，也不复制榜单成绩。

- [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)：参考大工具结果外置、按需读取和上下文管理。其记忆机制不直接替代本项目的版本化事实 Store。
- [Open Deep Research 的研究循环](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py)、[工具内容处理](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/utils.py)：参考研究 brief、正文内容/关键摘录、明确的迭代边界。仓库已于 2026-08-21 归档，只作架构参考，不新增为运行依赖。
- [GPT Researcher Deep Research](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/skills/deep_research.py)：参考已访问 URL 集合、发现/后续问题以及受控深度和并发。此处不采用递归研究树或整套引擎。

三种可选路线：

1. **增量改造现有 Harness（推荐）**：复用已完成的治理边界，先修主链路；缺点是仍需维护自身策略与评测。
2. **迁移 Deep Agents SDK**：可复用部分标准上下文能力，但要适配现有预算/安全/Ledger 和历史状态，不能靠替换框架自动获得正确检索。
3. **整体接入 GPT Researcher**：快速复用研究引擎，但会引入另一套模型、工具、缓存与费用治理，第一阶段难以清晰诊断收益。

推荐路线 1，以实际验收决定是否还有必要替换组件。这里没有一种可脱离模型、数据与成本约束的“最好架构”；取舍是让已有 Harness 更简单、证据路径可检查、调度可恢复、效果可对照。

调度取舍：第一阶段保留“当前批任务结束后评估”的 Plan-and-Execute，不为每个小任务增加一次 LLM replan。每任务重规划反馈更及时，但增加调用与状态分支；先验证缺口驱动的批次循环，再依据轨迹判断是否值得增加该能力。

## 4. 第一阶段：正文可见、缺口驱动的研究闭环

### 4.1 原文按需读取

工具保持 search_web → fetch_page，再增加一个只读 `read_evidence`：按已授权 Evidence ID 和问题相关范围返回有界原文，而非模型生成的摘要。返回 Evidence ID、版本/内容哈希、宿主生成的 passage_id、来源位置、选段策略和省略信息。首次可按问题选段，必要时按字符范围读取相邻内容，不新增 embedding、向量库或全文搜索服务。

模型参数限定为 evidence_id、query 或 start、limit：query 与 start 互斥，limit 默认 2000、最大 3000 字符；没有 query/start 时由研究分支填入当前查询。Evidence ID 不超过现有 128 字符上限、query 不超过 1000 字符、start 为非负整数。输入无效不静默转换；超出正文范围明确返回空范围，不声称已覆盖相关事实。最终 JSON preview 包含定位信息后不超过现有 4000 字符上限，必须完整可解析，不能依赖 Gateway 切断 JSON。

Agent 主动读取走现有 ToolGateway 的 EVIDENCE_READ 能力与执行账本，绑定当前运行的 workspace/允许证据集合；不允许模型传入任意文件路径、租户或未经授权的 ID。EVIDENCE_READ 枚举虽已存在，但研究员白名单尚未授权它，ToolName/registry 也没有 read_evidence；这些必须显式接入，不能声称“已经有可用读取工具”。读取计入工具次数，但不计网络抓取次数、不产生新 Evidence。第一阶段不新增读取结果共享缓存，CachePolicy.NONE；同一已提交调用仍由 Ledger 重放，避免先增加一套缓存失效机制。

Gateway 新增由宿主构造的 EvidenceAuthorization，包含已授权 ID 集合，不出现在模型工具 schema。允许集合来自该分支已抓取证据与宿主验证过的历史/父策略证据；不能以“同 workspace 中存在”代替“本次运行被授权”。权限校验在 Ledger 重放和缓存返回之前执行。适配器统一接收参数与可信调用上下文（tenant/run/caller/授权集合），不把 tenant 塞入模型参数，也不在通用 Gateway 中堆工具业务特例。

已删除/不可访问 Evidence 必须拒绝读取与重放；已过期/被替代材料只可按明确历史范围展示，不能自动作为当前有效事实。事件包含 ID、版本/哈希、范围、预算/省略状态，不默认把全文、密钥或未授权正文复制到审计日志。

复用唯一选段实现，将当前位置 `responses/excerpts.py` 提升为 `tools/evidence_views.py` 中的纯选段/定位逻辑，避免工具层反向依赖响应图或复制算法。Agent、evaluator、responder 同用原文选段规则，但可按阶段选用不同有界片段；“同一规则”不等于“每阶段看到了同一全文”。全文仍在 EvidenceStore，不进入持久化控制状态；有界 ToolMessage 可进入现有消息 checkpoint。

Evaluator/responder 的固定读取属于宿主控制的材料装配，可以直接通过 EvidenceStore 构造授权视图，不伪造模型工具调用；单独记录 evidence.read/view 事件。Evaluator 每次最多装配 8 份来源、每份最多 3000 字符，再通过现有 token 预算；未装配/被丢弃的来源显式记录，不能当成读过。正文位置单位沿用 Python 字符索引（0-based、end-exclusive），行号 1-based，不混用 UTF-8 字节或 UTF-16 偏移。

支持校验以最终实际模型输入为准，不只检查选段器裁剪前的结果。原文范围作为可定位单元装配；需要缩短时重新计算实际范围，不能保留旧坐标。无法确认裁剪后可见范围的引用不获支持资格。

研究 system instruction 明确：搜索摘要只用于发现来源；抓取完成不等于已阅读；关键结论需读取原文支持。页面内容是证据数据，不能覆盖原任务、工具权限和预算。

### 4.2 充分性检查

规划在原有 planner 请求内生成最多 6 项用户问题要求，不能读取 gold、评分引用、期望 URL。固定 ID 为 r1…r6，每项描述不超过 500 字符；原问题和用户约束始终保留。要求在首次规划后固定，replan/follow_up 不能删掉难回答的项或降低标准。规划格式无效时保留当前查询兜底，并将原问题作为整体要求；这是降级分解，不得伪称细粒度需求已完整提取。

三模式使用共享 CoverageAssessment：每项 requirement_id 对应 covered / missing / conflicting、reason，以及支持的 Finding ID。所有要求必须出现且仅出现一次；额外或缺失 ID 均无效。评估器看到有界真实正文，不能把背景记忆、标题、搜索摘要、todo completed 或 confidence 当作正文支持。

模型输出的 Finding draft 增加 supports 请求：每项仅填 evidence_id、passage_id、quote。模型只复制当前材料的片段标签与原文，不要求它数几千个字符计算绝对位置。宿主在指定的实际可见片段中定位 quote，唯一匹配后生成规范化支持项（evidence_id、版本/哈希、start、end、quote），存入现有 Finding 的有界 supports。重复匹配不猜位置，需扩展 quote 或保留 missing。每个 Finding 最多 3 段、每段 quote 最多 500 字符；继续使用现有 findings 条数上限。当前覆盖状态每轮替换，证据 ID 集合继续合并；不持久化全文副本。

代码检查 ID 是否授权、passage_id 是否属于本次实际可见材料、定位后 body[start:end] 是否逐字等于 quote、字段与长度是否有效，以及 coverage 的 Finding ID 是否指向通过检查的发现。定位只在对应正文片段中进行，不能匹配来源标题、URL、模型背景或省略标记。任何 covered 项没有有效 supports 都降为 missing；模型 action=complete/sufficient=true 不能覆盖这一检查。这只证明出处存在与可见，语义蕴含仍由 evaluator 判断，不承诺纯代码解决幻觉。

本版本产生的未支持 Finding 不进入事实型长期记忆；既有偏好、事实、Evidence、Episode 的类型与 TTL/删除机制不重建。历史事实仍须回到来源核验才能计入本次覆盖，不能因为存在 source_evidence_ids 就当作语义真值。已有记录不批量清理。

已截断/不可读来源不作为不存在某项信息的证明。读取失败、评估失败或预算被裁剪均保留具体缺口，不猜测 sufficient=true。

### 4.3 有界补查

Plan-and-Execute：plan → 顺序执行当前批任务 → 正文评估 → 足够则 finalize，不足且可继续则沿已有 replan → 执行新批 → 再评估。保留最多 2 轮 replan；新增加 max_replan_tasks=2 的独立补查批次上限，不把初始最多 6 项的额度每轮再用满。

Multi-Agent：supervisor_plan → 并行研究 → aggregate → 同一正文评估 → 足够则 finalize，不足则沿已有 follow_up。保留最多 1 轮 follow_up；补充分配最多 2 个方向，其余初始研究员上限不变。来源重复或单分支失败不抹掉其他分支已提交证据。

Workflow：保留 evaluate → finalize，证据不足时返回具体缺口与 partial。测试要接受这一有意差异，不要求它具有另外两种模式的外层重规划行为。

补查输入包含固定 requirements、当前 missing/conflicting、评估原因、已支持发现、已执行方向、来源 URL/内容哈希摘要与剩余限制。每个新方向声明 target_requirement_ids，必须指向当前缺口；再将该缺口与相关已授权证据传给研究分支。不重跑全部任务、不把 bare Evidence ID 当研究摘要、不向模型灌入 gold。

代码继续做确定性查询去重，不新增语义向量去重。URL/内容重复不是硬禁令：补读同一页面的新范围也可能解决缺口。进展定义为新增来源内容、有效的新原文支持范围或覆盖状态改善；一次完整补查与再评估后仍无进展则 partial。首次评估不足不因为“尚无新增”而跳过第一次补查。最多轮数仍是最后硬边界。

当前需求缺口来自最新 CoverageAssessment，解决后可移除；历史工具错误/早期缺口留在 topic outcomes 与诊断事件中，不继续全部冒充 unresolved。取消、致命错误、未完成 todo 等现有强终止条件仍保留；不因最终找到另一来源而自动把所有历史逻辑失败改为成功。

零证据时不用空材料请求模型假装评估：构造 missing 状态。若是可恢复来源失败且仍有补查额度，可沿已有 replan/follow_up 找替代方向；预算不足、取消、致命故障直接退出。补查仍无来源则 no_sources，不猜测事实。

补查不创建新的预算作用域，不重置 Provider/工具/时间限额；取消立即传播。新增控制状态进入 Checkpoint，重放从已提交账本读取结果。对新增状态字段的旧快照采用明确缺省值；不能保证恢复的历史快照用旧版本完成，不清理用户数据。

旧 Finding 的 supports 可反序列化为缺省空列表，但不能因此通过新契约的 completed/事实记忆准入。旧运行若没有可重建的 requirements/可见材料状态，必须用原版本完成或明确提示恢复不兼容，不能静默跳过支持检查。

上段的限额继承针对已配置、已计量的限制；不暗示当前本地生产入口已经具备全运行 Provider 计量。子项目 A 的真实开发实验仍用已封顶评测入口，子项目 B 完成后才验收生产入口的统一限额。

不叠加独立的第二套预算或 LLM 裁判循环。第一阶段直接复用现有模式解析规则：Workflow 最多一次格式修复、Plan-and-Execute/Multi-Agent 当前解析失败降级；后者如需统一格式修复，另做有界且计费的单独改动。

### 4.4 回答与降级

Responder 使用原问题、固定 requirements、最新覆盖状态、通过支持检查的 Findings 与实际可见原文。已验证 supports 对应的片段优先进入回答输入，避免普通关键词选段把支持结论的关键原文挤掉。每项用户要求要么有证据回答，要么明确缺口/矛盾；不能用常识补写缺失来源，也不能仅为忠实度分数删掉必答项。

不新增无界“生成—裁判—重写”循环。保留既有一次合并格式/长度纠错，先在同一生成请求中要求来源约束和逐项覆盖。原文引用校验不是答案语义正确性的硬保证，真实语义评分继续隔离在评测环境。

完成状态与证据充分性一致：当前必答项 missing/conflicting、支持检查失败或已有强终止条件未解除时不能 completed；partial 不被来源清单伪装为已完成研究。回答仍保留已有 content 与引用契约，不在第一阶段增加庞大的 claim extraction 在线服务。引用编号有效不等于全文语义正确；逐条引用语义支持留给独立评测和人工抽查，并在第五节规定分母。

## 5. 三模式测试与主指标

### 5.1 分层测试，不混淆结果含义

| 层级 | 三模式要求 | 可证明的内容 |
| --- | --- | --- |
| 功能/故障回归 | 三模式逐项参数化；包含 Answer 与 Report 响应链路 | 契约、路由、边界与受控场景行为，不是模型真实质量 |
| 持久化恢复 | 三模式逐项新建 gateway、graph、DB session 后恢复；本地入口也要验证 | 已提交副作用重放、状态/额度延续，不是任意外部调用 exactly-once |
| 冻结真实资料 + 真实模型 | 同题同材料同资源，三模式与固定 Baseline | 可复查的模型/检索编排质量，不是实时联网研究 |
| 真实公开网页 + 真实模型 | 三模式都做端到端冒烟；Plan-and-Execute 是主要质量样本 | 生产抓取、来源覆盖与可用性；实时网页变化须单独标注 |

### 5.2 共同功能矩阵与有意差异

- 真实生产循环中的研究员和三种策略 evaluator 能看到受控原文，而非只有 metadata；正文尾部相关事实在存储范围内可被读取。
- Checkpoints-only 场景不能声称 Store 已覆盖。候选来源可用时，Plan-and-Execute/Multi-Agent 的补查必须针对 Store 并读取原文；Workflow 固定流程不足时如实 partial。无可用来源三模式都保留缺口。
- requirements 固定且完整；无有效引用的 covered 无效；已补齐缺口可以关闭，历史诊断仍可追踪。背景事实或 memory 不能替代本轮正文支持。
- 只读新范围能形成进展；重复抓取/缓存命中不能冒充新研究；零证据仅允许有界替代，不无限重试。
- 同一 URL/内容重复、预算耗尽、无新信息、正文失败、格式失败和取消不会导致无限循环或错误 completed。
- 原文位置正确、正文/哈希保持、跨 workspace/未授权 Evidence ID 拒绝；网页注入不能改变任务/预算/权限。
- 新旧 Checkpoint 边界、工具结果配对、Ledger 重放、已完成证据复用及记忆准入不退化。
- 改变 gold 和参考 URL 不改变检索/正文读取/模型输入；各模式的可见证据与预算事件可留样复查。
- 本地测试先 RED 后 GREEN；独立 Ragas 回归保持通过。开发题用于诊断，不伪装为未知测试题。

### 5.3 恢复矩阵与部署边界

每种模式至少覆盖：研究模型返回待执行调用后中断、工具 Ledger 已提交但图节点尚未提交、研究子图已完成但父图未合并、回答阶段中断、事实记忆已写入后的恢复。Plan-and-Execute 增加 replan 之后/新任务执行前；Multi-Agent 增加同一 fan-out 内一个分支成功、另一个中断，以及 follow_up 跨轮恢复。不能仅参数化模式名却始终运行 Workflow。

测试必须重建依赖而不是只复用内存对象；断言任务位置、轮数、原问题/约束、当前缺口、引用、预算和已提交工具调用次数。增加子进程停止/重启测试，才能在报告中使用“进程崩溃恢复”措辞；普通异常/CancelledError 测试只称受控故障注入。

用户可用的本地恢复作为独立子项目：本地复用已有 SqlAlchemyToolExecutionStore，补齐 SQLite tool_executions 表；增加同身份 resume 入口，首版显式续跑，不在启动时自动触发付费任务。仅允许 interrupted/recoverable 状态恢复，取消/已完成状态不能自动复活；并发 thread/run 使用已有租约原则防重复执行。预算恢复失败应拒绝新的付费/网络执行，而不是用清零计数继续。这个子项目完成之前不能承诺本地重启不重复抓取。

模型全运行逻辑调用/Provider 尝试限制与剩余额度用于最终回答的预留，归入同一“运行限额”子项目；迁移评测侧计量的公共部分到运行层而非生产代码反向导入 eval。预留不是额外额度，重试仍消耗尝试数。副作用发生后、Ledger 提交前的崩溃窗口仍可能重试，不能宣称外部网络请求严格 exactly-once。

### 5.4 主指标与诊断指标

主报表首先展示 Plan-and-Execute + Answer，随后用相同指标完整展示 Workflow、Multi-Agent、Baseline；不把它们混成一个“总体正确率”。Report 是独立实验身份与报告。

| 指标 | 口径与分母 | 用途 |
| --- | --- | --- |
| FactualCorrectness F1 | 原生 Ragas 0.4.3；最终回答对冻结参考答案；逐项 ok/error/N/A | 主事实质量指标，兼顾正确性和完整性 |
| Faithfulness | 原生 Ragas；回答对实际选入 outcome 的证据，不补 gold | 主来源支持指标；不能替代真实性或逐条引用正确性 |
| 应用完成率 | completed / 全部预注册运行；partial、failed、cancelled、未执行分开列 | 主工程可用性指标，completed 仍不是语义正确的同义词 |
| AgentGoalAccuracy | 原生 Ragas，原问题 + 最终回答的 outcome-only 视图与 reference | 辅助指标，不虚构多分支工具会话，不单独称正确率 |
| 引用 ID 有效性 | 引用是否指向授权已加载来源；无引用按任务引用要求处理 | 确定性格式/权限检查，不是 citation entailment |
| 引用支持 / 事实引用覆盖 | 离线逐条核对事实与其实际所引来源；报告支持引用数/全部被评引用数，以及获有效出处事实数/需出处事实数 | 自定义 rubric + 人工校准；未实现/未标注时 N/A，不冒充原生 Ragas |
| 错误完成率 | completed 但独立复核发现必答事实缺失或无支持的运行数 / 全部 completed | 防止机械完成掩盖证据不足；无 completed 时 N/A |
| 恢复成功率 | 验收恢复不变量的通过场景 / 全部注入场景，按模式与故障点拆分 | 受控可靠性，不计作真实回答质量 |
| p50/p95、Provider、工具、抓取、Token | 实际轨迹/usage；缺失数单列；p95 小样本仅描述 | 资源权衡；无价格时 cost=null |

补充报告缺口关闭率、无新增信息停止、来源/读取范围重复、最终 writer 实际可见证据。这些是行为诊断，不能用 online evaluator 自评分冒充独立正确率。参考 URL 命中只作诊断，不强制唯一 URL/多个域名。现有 source_quality 的 canonical URL 启发式也不能当权威性评分。

所有预注册任务都出现在执行结果中；未评分不补 0，也不悄悄删除。质量均值附 scored/attempted 与 error/N/A/missing 分母，同时报告全部运行完成率和失败文本。主配对质量视图要求同题、同 repeat index、双方都有实测评分，不只筛 completed；completed-only 仅辅助。重复先在题内汇总，再按题配对；小样本、共享上游事实、来源家族相关性明确披露，不宣称统计显著性或商业榜单优势。

功能与安全不变量是硬放行条件，出现越权读取、已取消任务复活、无限补查或元数据冒充支持则不放行。质量数值门槛在新的 Plan-and-Execute/Answer 开发基线和人工校准后预注册，再冻结测试配置；不能借用旧 Workflow/Report 分数设提升目标，也不能在看到 test 结果后下调门槛。子项目 A 至少须在同条件开发对照中验证事实 F1 的改进且不以丢必答项换 Faithfulness，完成率/用量一起报告；没有新增真实评分时只称行为修复已验收。

### 5.5 真实实验批次与公平性

下列规模是待批准的采样设计，不是新增调用授权；每批研究/Tavily/抓取/评分上限在运行前另行确认。

1. 开发冒烟：固定 single_hop-dev-01、multi_hop-dev-02、version_boundary-dev-02，共 3 道已用于开发的题 × 三模式/Baseline × 1 次 = 12 个 Answer 运行；只用于校准与诊断。
2. 开发验收：现有 12 道 dev × 四系统 × 1 次 = 48 个 Answer 运行，按类别报告；预先选 6 道 dev 对四系统各重复 3 次作为独立稳定性批次，共 72 个运行，不挑最好的一次。
3. 固定配置验收：18 道现有 test × 四系统 × 1 次 = 72 个 Answer 运行；开发与测试来源按已有 source_group 隔离，但不是完全语义独立、人工金标的通用 holdout。测试失败后继续调参，该版本题集即转为开发数据，不能继续称未见测试。
4. 真实网页冒烟：先固定 3 道适合公开网页核验的问题 × 三模式 × 1 次 = 9 个运行；保留搜索结果、实际网页正文/时间/哈希、失败/截断信息，明确标为 live-web。再依据新额度扩大 Plan-and-Execute 样本，不能与冻结语料成绩混合。
5. Report 验收：3 道开发题 × 三模式 × 1 次 = 9 个独立长报告运行，检查需求覆盖、章节完整性、引用支持、输出截断与最终状态；输出预算与长度配置单独冻结，三模式一致。

同批模型、温度、工具后端、资料、长期记忆关闭、Answer 输出/token 配置、run 资源上限一致；裁判身份与原生指标配置固定。基线使用相同证据视图和回答器，只保留固定检索/抓取，不偷偷增加自适应补查。采用预注册随机顺序或轮换顺序，记录顺序，避免整批总额度总是优先供给某个模式；不能按观察到的好坏分数追加重跑。

主实现复用现有 eval/runner、manifest、原始 records、隔离 Ragas、compare_cli；对 before/after 的同模式配对展示属于分析侧扩展，不新造平台。老真实校准只有 Workflow/Baseline + Report 单题，原记录不改，不当作 Plan-and-Execute/Answer 基线。本轮尚无新的真实质量分数。

第一阶段完成不宣称全面生产就绪，更不承诺某个分数。验收依据是行为和完整轨迹，不是单题 Goal=1。

## 6. 后续独立子项目与真实验收

交付顺序：A 共享正文/支持契约 + 缺口驱动的已有循环；B 三模式持久化恢复验收 + 本地显式续跑/运行限额；C 抓取可靠性与真实网页端到端验收。A、B、C 各自拆为可独立审阅的实施计划；当前先确认 A 的设计，不把所有子项目挤成一个大改动。

抓取可靠性：采集/存储上限与模型读取预算分离；在现有响应字节安全上限内尽量保存正文，超过保存上限则显式记录截断和长度/哈希口径。补齐 HTML/纯文本/Markdown 支持、动态页面提取与回退；不默认下载大文件，不绕过站点访问限制。截断内容不能用于武断否定。A 只能读取已经存入 EvidenceStore 的内容，不能找回 fetcher 丢掉的尾部。

可用性和交付：优先完成单用户公开网页的运行、取消、超时和显式恢复体验；将来源、当前缺口、截断、实际 usage 展示给用户。多用户认证、PDF/登录资料、独立云部署分别评估，不混在当前循环改造里。

真实验收采用新实验身份保留旧低分样本，先跑小规模公开网页检索和冻结真实资料开发题，再冻结配置跑未见题。相同模型/资料/预算下对照 Baseline/Harness，报告事实 F1、Faithfulness、完成率、缺口、延迟、实际 usage 和人工抽查，不只报告最好结果。

新增付费研究、Tavily 和裁判调用必须先确定新的批次上限。之前单题校准的额度不自动复用为新批次授权；无新额度时先完成离线真实应用链路验证。远程 CI/Docker/多用户生产上线未验证时如实保留边界。

## 7. 代码落点与设计自审

| 所有者 | 主要代码落点与职责 |
| --- | --- |
| 领域契约 | domain/evidence.py 的有界 supports；domain/research.py 的 requirements/coverage；不把评分 gold 放进运行 DTO |
| 证据视图 | 新 tools/evidence_views.py 复用原 excerpts 纯算法；range/哈希/可见性；固定装配不伪造工具调用 |
| 模型工具 | domain/tools.py、tools/contracts.py、adapters.py、policy.py、gateway.py、harness/agent_tools.py；读工具 schema、宿主身份、授权与 Ledger |
| 覆盖评估 | 新 strategies/evidence_evaluation.py 负责共同材料装配、coverage/support 校验；三模式 nodes/state/models 只保留自身路由与 schema 适配 |
| 回答与记忆 | responses/graph.py 传入当前覆盖与支持片段，保留 citation validator；harness 的记忆 consolidation 只接纳新契约支持的事实 |
| 序列化 | harness/checkpoint.py 为新增有界类型注册；旧快照契约用明确默认值或旧版本完成，不删除历史数据 |
| 恢复与限额 | application/assembly.py、runtime/local.py、persistence/execution_ledger.py 与既有预算/调用边界，独立子项目 B |
| 评测 | eval/runner.py、experiment.py、comparison.py、evaluation/ragas_quality.py；新语义引用分析留在评测侧 |

重构选段模块与行为增强分开提交，兼容导入只在有实际调用者时保留并说明迁移；不创建不承担职责的抽象。三模式共用的是证据标准，不是新的通用调度器。新增支持模型必须真的参与覆核、回答装配与记忆准入，而非只作为展示字段。

自审结论：无新运行依赖，不复制编排层；不把 Workflow 无外层循环列为缺陷；replan/follow_up 上限与补查批次上限清晰区分；当前缺口可关闭而诊断不可丢；可见引用校验不冒充语义真值；本地部署恢复差异、人工核验不足、模型费用授权与抓取截断明确分开。

设计已确认：先用 writing-plans 写子项目 A 的逐任务计划，再按 TDD 实施；三模式完整测试与 Plan-and-Execute 主指标是所有后续阶段的固定要求。恢复/统一运行限额、抓取可靠性分别使用独立计划。设计确认不表示运行代码已经改变，也不表示真实质量分数已有提升。
