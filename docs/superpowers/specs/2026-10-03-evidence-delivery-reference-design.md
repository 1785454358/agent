# 第五轮：证据传递与宿主构造引用

## 已确认方向与边界

用户于上一轮设计答复后回复“可以”：保留现有 Harness、三种研究模式、记忆和 checkpoint，先改善“证据传递＋程序构造引用”。P&E 为主验收模式，Workflow、Multi-Agent 同测；不更换模型、提高预算、修改原评分或参考答案。

这是一个共享证据链路子项目，不整体替换研究框架。独立裁判校准、检索排序升级、未见测试集与生产实时联网验收不纳入此次实现。此文是待书面审阅的设计，不代表代码已实现或质量已提高。

## 根因与目标

上一批 structure-selection-real-answer-20261003 的只读审计确认：

- 单跳 P&E、MA 的实际 researcher 工具消息已经包含 thread_id 的主键、保存与恢复解释；evaluator 重新从正文选段后没有收到该解释。Workflow 的实际研究工具消息未找到这段解释，不能把三模式都描述为“已经读到”。
- 模型手工输出长 evidence_id/passage_id 和 quote，出现错 ID、删除反引号、换行改写、拼接省略号。多跳 P&E 的一条 quote 长513字符，超过500上限，使整个 assessment schema 失效。
- 回答阶段把“当前没有有效支持”转述成“文档没有说明”，把内部校验失败误当成资料不存在。

目标：研究阶段成功返回的原文范围能够受控地进入评估材料；模型只选择短编号，宿主生成原文支持；失败原因如实传给回答阶段。成功读取不等于事实被蕴含，合法引用不等于需求已完整覆盖。本轮不实现新的独立语义验证模型。

## 方案取舍与参考

- 采用：保留 Harness，改共享证据交接与引用解析。复用原文存储、预算、门禁、三模式调度；新增有界内部范围 DTO 和引用 draft，而非新服务。
- 仅调整提示词或换模型：成本较小，但无法消除“读到后丢失”和复制引文的结构性失败，本轮不采用。
- 整体替换研究框架：集成与兼容成本更高，不能证明在本项目约束下自动获得更好结果，本轮不采用。

参考 [Open Deep Research](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py) 的相关研究材料交接（该仓库已归档，仅作架构参考），以及 [STORM](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/article_generation.py) 的子问题取材与编号材料写作。这里只借鉴材料组织模式，不照搬其实现，也不宣称其编号引用具有本项目的原文校验保证。

## 数据流与责任

1. read_evidence 经既有权限和工具入口成功返回完整预览。
2. 共享 Agent 工具边界从实际返回、将交给 researcher 的预览提取原文范围，形成宿主 read anchors，随 Agent state/checkpoint 与 ResearchTopicOutcome 传递。
3. 共享 evaluator 验证 anchors 对应当前来源和正文；在原预算内优先组织已验收 supports、读过的 ranges，再用原 selector 补足材料。
4. 选中的原文范围拆为短引用单位；token 分配后只给真正可见的单位编号。
5. evaluator 输出 claim、短引用编号和 coverage。宿主映射编号，生成 EvidenceSupport 并沿用覆盖门禁。
6. writer 使用已验收 findings 与既有支持优先材料，区分“尚未建立有效支持”和“评估失败”；不会自动把读取记录当作已证明事实。

三模式仅使用共享入口与新 draft，不分别实现 anchors、引用解析或失败分类。正文仍仅在局部读取，不保存到新增 graph state；事件日志不是运行依赖，也不能作为权限或可见性证明。

## 1. 有界读取锚点

新增内部 ReadEvidenceAnchor，字段为 evidence_id、version、content_hash、start、end。start/end 使用 Python 字符坐标，严格整数，满足 0 <= start < end；不存正文、quote、模型结论或来源指令。该 DTO 仅由宿主构造，不进入模型工具参数，不允许模型上报范围作为读取证明。

捕获位置为 harness/agent_tools.py 的成功 READ_EVIDENCE observation：只解析实际 ToolMessage 对应的 preview，不从任意历史消息、AI 输出或整个 EvidenceStore 推测可见内容。若工具消息截断导致预览 JSON 不完整、结构/版本/哈希/坐标异常，拒绝建立 anchor 并记诊断，不扩大 preview 限额或伪造已读范围。原 tool 结果仍按既有契约返回。

每分支最多64个唯一 anchors；去重键为来源、版本、哈希、start、end。合并保留宿主观察顺序，新重复项不改变位置；达到上限后不追加新项，记录 read_anchor_capacity。多工具同批按既有调用索引合并，不能因并发完成顺序改变结果。不将 anchor 计作新页面、网络请求、已验收 support 或需求 covered。

AgentExecutorState 和 ResearchTopicOutcome 增加 read_anchors，默认空列表；原 state、outcome、取消、失败和 unfinished todos 行为保留。成功读取但后续受控退出的 anchors 可供诊断或 partial 回答取材，不覆盖该退出原因。checkpoint 序列化显式允许新 DTO，旧无字段结果可加载。

## 2. 交接材料与限额

共享 evaluator 从当前 state 的 topic_outcomes / researcher_outcomes 收集 anchors，不额外读取所有历史 conversation。只处理本次 evidence_ids 内、既有顺序最多8份来源；不因 anchor 指向第9份来源而扩来源上限。

每次使用前按当前 workspace 重读记录和 body，验证 ACTIVE 状态、来源 ID、version、content_hash 和坐标。校验失败只拒绝该 anchor，不阻断其他合法来源；不得跨 workspace 使用、接受已过期/删除来源或旧版本坐标。无合法 anchor 的来源仍走现有 selector。

每来源额度仍3000字符，完整 metadata/JSON 和全局 token allocator 继续单独保护。顺序如下：

1. 原有已验收 supports 优先，保留其既有验证与取材规则。
2. 尚未包含的合法读取范围，按首次观察顺序加入，重叠原文只计算一次。能够完整容纳的范围原样保留；不能全部容纳时，在该范围的句/行边界提取可容纳部分，必要时才用有界原文窗口，记录 read_anchor_omitted。
3. 只有剩余额度才调用原 question/requirements selector 补足，不重新排序覆盖已保留的 anchors。不改词项、停用词、稀有度权重或加入主题特判。

因此“读过”并不保证无限保留；能够放入剩余额度的合法 ranges 不应无理由消失。超容量、来源上限、字额不足、token 掉落均有诊断。被丢弃的范围不得建立当前可见引用支持，也不得据此宣称完整资料无答案。

这不是相关性重排算法：首次读取本身可能不相关，也可能因限额仍漏关键事实。后续若真实轨迹显示 anchors 被无关阅读占满，应单独设计选择策略，而非在此轮偷偷调排序。

## 3. 短编号引用与宿主构造

### 原文单位

对选中范围按原始句/行边界打包成长度1至500字符的引用单位；无法在500内容纳的单句/单行允许按原始坐标连续拆分。已验收且长度合规的 support.quote 本身优先作为一个完整单位，不在其内部另行切分；其余范围排除重复覆盖后再打包。保留原始 Markdown、空白、Unicode 和换行，不能添加省略号或合并不相邻的正文作为单条 quote。

每调用最多128个引用单位。超过单位上限或 token 额度即掉落并诊断，不读取完整 body 的隐藏部分作为支持。完整 serialized JSON 与 pinned 指令参与 token 计算，单位只能整块保留/掉落；不能用计数前的单位表解析模型输出。

最终实际可见单位按稳定输入顺序编号 p1、p2 等；模型看到短 ref、来源短编号和原文 text。宿主局部映射同时保留 EvidencePassage 的来源、版本、哈希和 start/end。内部稳定 passage_id 算法保留用于审计，但不要求模型抄写它。相同正文在不同坐标处可分别选择，以编号定位，不用全正文子串唯一性猜位置。

### 输出与验证

新 ReferenceFindingDraft 只让模型填写 id、claim、confidence、supports；每个 support 只包含短 ref，每 finding 最多3个 supports。evidence_ids、quote、version、hash 和坐标由宿主推导，不接受模型在新 draft 中填入这些字段。claim/confidence 与 findings 数量沿用现有上限；covered 仍要求完整 coverage 与合法 finding_ids。

宿主只在本次 EvaluationView 的最终可见映射解析 ref，拒绝未知编号、旧调用编号与隐藏单位。注意短编号可能被不同调用重复使用：只按当前调用解释，不能凭相同 p1 自动关联历史内容。已验收 Finding 中只持久化现有 EvidenceSupport，不持久化短 ref 作为事实身份。

EvidenceSupport 的 quote 严格等于 body[start:end]，长度上限仍500；版本、哈希、坐标和正文复核不放宽。语义是否支持 claim、需求是否完整和来源冲突仍由现有 evaluator/coverage 逻辑判断。无需新增一个模型或自动多轮引用修复。

格式不合法仍按现有 repair_attempts、重试与调用计量处理，不新增尝试。schema 合法但未知引用的 support 不被验收；一个 finding 无合法 support 则拒绝，有合法 support 时沿用既有 normalize_findings 的有效支持保留规则，不额外收紧为整条 finding 失败。重复 finding ID、不合法需求 ID、covered 引用未验收 finding 等继续按当前严格规则拒绝。尤其不把“有一个合法 ref”自动视为需求 covered，不把一项无效 finding 从 coverage 中删除后偷偷判完成。

## 4. 契约版本与恢复

新研究使用 evidence_contract_version=3，ResearchTopicInput/ResearchOutcome 接受该版本；require_evidence_contract 只允许 v3 继续派发、评估和补查。v1/v2 已完成记录与旧 DTO 保持可反序列化、查询和历史展示；旧中途状态若恢复并尝试新研究动作，显式 incompatible_evidence_contract，不解释为引用失败或允许绕过门禁。

保留旧 SupportDraft、FindingDraft 与旧模式评估 DTO 供 checkpoint 解码；新短引用 draft 与模式评估 schema 使用独立类型。新三模式共享一个引用解析入口，策略的 action/sufficient/routing 字段与意义不变。实现计划明确列出各类型及 serializer 注册，不能只改类型上限而漏掉生产创建点或 writer 的 grounded 判断。

writer 可处理历史 v2 和新 v3 已验收 EvidenceSupport；支持验证与可见材料规则继续生效。历史结果的覆盖验证与“允许派发新研究”的版本门禁分开，不能让 v3-only 的派发检查误拒绝历史 v2 已完成结果，也不能因 writer 能读取 v2 就放开旧中途状态。新读取 anchors 是默认空的向后兼容字段，不回填旧记录，不把旧日志恢复成已读凭据。受控退出、待办、no_progress 与 runtime 恢复门禁不放宽。

## 5. 如实表达缺口

通过现有 coverage reason、diagnostic_gaps 和 writer 的 pinned 研究上下文传递原因，不新增一套全局状态机或公共错误服务：

- evaluation_unavailable / schema 校验失败：无法完成有效评估，不是原文没有答案。
- invalid_support_reference / unsupported_requirement_coverage：未建立有效原文支持，不是文档缺失说明。
- unread_evidence / read_anchor_capacity / read_anchor_omitted / token 掉落：材料未读全或未送达，不能做整个语料的不存在断言。
- missing / conflicting：表述当前可见证据未覆盖某要点或存在冲突，不扩大为“所有资料都没有”。

writer 仍须明确未满足的要点，不能隐瞒 partial 或借常识补全。可报告已验收、在本次 writer 输入中可见的事实；不能因为局部读到了但未通过评估就把该 requirement 强行标记完成。本轮修改是失败原因组织与提示约束，不宣称已经实现逐主张语义校验或能彻底阻止所有错误措辞。

补查目标、次数、去重和强退出优先级不变。不额外增加自动 fetch、重评、Agent 或预算来掩盖上述失败。

## 组件落点与排除

预期涉及 domain 的锚点/结果/版本 DTO，harness 的工具观察、Agent state/finalize/checkpoint，tools 的原文单位与有界材料组织，strategies 的共享 evaluator 与三模式新 draft/版本入口，以及 responses 的 grounded/失败原因上下文。每个助手保持单一职责，禁止三模式复制同一段引用逻辑。具体文件与签名在书面审阅后进入实施计划。

不改 EvidenceStore 持久化正文/哈希算法、URL 授权、租户边界、历史证据读取权限、抓取上限、记忆准入、模型、预算、重试、原始评分、gold、待办策略、三模式调度或公共响应格式。无新网络服务、向量数据库、第三方依赖或压缩模型。不引入人工制作的标准答案、目标事实词项、测试题 URL 作为运行提示。

## 验收与实验

### TDD 与离线边界

- 工具成功预览建立 anchors；失败、伪造模型消息、截断 JSON、非法坐标、跨租户、旧哈希/版本不能建立当前支持。并发顺序确定、重复去重、64个上限和 checkpoint 重放不重复追加。
- 通用问题样例：关键原文被研究工具读到，但 broad question selector 不选它；通过真实三模式 evaluator 入口断言该合法范围在额度内进入最终模型输入。另测无读取记录的正常回退、多个来源/范围竞争、重叠范围、超过8来源、已验收 supports 优先。
- 包含反引号、换行、中文/英文否定、代码、非BMP字符和超长句；选择短 ref 后支持等于原文切片，长度<=500，无模型抄写 ID/quote。引用单位切分不能将未显示文本带入支持。
- 未知/隐藏 ref、不合法 finding、重复 ID、无效 coverage 不完成；合法编号但语义不支持的脚本 evaluator 判 missing，不能被宿主自动转成 covered。
- token 掉落、pinned 溢出、anchors 超限、来源不可读隔离；完整 JSON 额度保护。事件不可用不影响运行；取消和受控退出不被覆盖。
- v3 三模式通过，旧已完成记录可解码与展示，旧中途状态拒绝新研究动作；新增 DTO checkpoint roundtrip；真实存储中的旧 supports 仍按原文验证。
- writer prompt/input 验证失败分类和“不作全语料缺失断言”约束；脚本回答不能代替真实回答质量。Answer 为主，Report 独立回归，不合并质量。
- 完整后端 not-real、隔离 Ragas 回归，相关文件 Ruff 与五轴代码自审；只提交本次设计，不整体提交原有 dirty 工作树。测试必须观察正确 RED 后再实施。

### 唯一真实复测

书面规格确认、实施与离线回归完成后，登记并只跑一次：single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02，7篇冻结官方资料，本地 search/fetch、真实 LLM，三模式每题一次，共9条 Answer。不是生产实时联网端到端验收。

沿用 doubao-seed-2.0-lite、temperature=0、max output4096、Answer最多2000字符、长时记忆关闭。每运行40逻辑调用 / 80 Provider尝试 / 24工具入口 / 12分支轮 / 360秒；整批360逻辑 / 720 Provider。隔离 Ragas0.4.3、原裁判/scorer/输入限额，只评分一次，最多144 Provider。资产哈希、模型、context allocator 和评分配置逐字段与上一批核对；gold 仅用于评分或诊断断言。

唯一目录：tmp/evidence-delivery-real-answer-20261003、tmp/evidence-delivery-real-answer-quality-20261003、tmp/evidence-delivery-real-answer-comparison-20261003。付费前检查不存在，冻结源码/HEAD/source_identity 并留样。不得换目录整体重跑、扩预算、改gold或挑选评分。若登记配置无法沿用，先报告原因，不能默默替换。

报告全部9条 completed/partial/failed、非空答案、事实F1/Faithfulness/Goal及有效覆盖、调用/token、实际 anchors/单位可见性与丢弃原因、引用失败和回答错误。对照上一批只作已调试dev描述性诊断：无新baseline，严格配对n=0、delta/CI=null，不做因果或显著性声明。

离线支持完整性和交接通过是实现验收；真实目标是答案要点更完整、错误缺口减少，同时没有放宽门禁。若 F1 未提高或调用明显增加，应如实报告并继续定位，不包装成总体成功。三题一次、同模型裁判不能证明生产可靠性；后续需独立人工校准裁判、未见测试集和重复运行。

## 自审与流程

- [x] 已查实际读取/评估输入、共享工具边界、DTO、三模式 schema、checkpoint 和 writer。
- [x] 文字接口/契约足以讨论，不需视觉伴侣；三方案与推荐已经呈现，用户批准方向。
- [x] 自审：读过不等于蕴含；来源、字额、单位和 token 上限分别保护；短编号仅属于当前调用；版本变化显式处理；失败分类不放宽 coverage；评测不改旧分数。
- [x] 用户审阅本书面规格后回复“开始”，进入 writing-plans，再按 TDD 实施。用户同时授权必要时大幅重构；本轮允许按职责拆分共享模块，不改变已确认的行为契约。超出该数据流的整体架构调整仍需独立设计。
