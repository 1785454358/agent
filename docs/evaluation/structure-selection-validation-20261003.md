# 结构边界与答案要点均衡选段：验证记录

## 实现范围

用户审阅书面规格并回复“可以”后实施。只修改 tools/evidence_views.py 与 strategies/evidence_evaluation.py：短段作为完整候选，长段优先句/行边界，无法拆开的超长单位保留有界重叠窗口回退；评估器分别传入封存 requirements.description，轮流尝试每项最佳 fit，再用原问题补剩余额度，事实选择后试放完整邻近标题。

无新服务、依赖、模型、状态或持久化 schema。每来源评估额度仍为 3000，最多 8 来源，既有完整 JSON/token 限额继续生效。已验收 supports 优先，显式 start 读取、授权、原文坐标/哈希、逐字 quote 与门禁均不改。工具与回答材料复用共享结构候选，未传 focus 时仍按原问题排序。没有新增通用停用词或修改原稀有度规则。

## 离线验证与限制

- 新 selector 回归 RED：12 failed / 6 passed；四项为实际句段边界断言失败，八项为批准的新 focus 参数尚未提供。没有导入或夹具异常。
- 真实入口竞争测试首版旧算法也能通过，未把它算作 RED；增加第二事实的同段背景后，四项均因完整 Beta 事实缺失而失败，覆盖实际三模式 evaluator 输入。
- GREEN 初轮 109 passed；补充已验收支持优先/伪造支持忽略及显式 start 不被 focus 覆盖的保护测试后，定向 328 passed。隔离 Ragas 34 passed，两个生产文件/两个新测试 Ruff check 与 format --check 通过。
- 简短本机性能观察：220,034 字符正文选段约 0.0089 秒；仅单次诊断，不是生产性能 benchmark。
- 依代码审查技能五轴自审：一个共享候选助手，无框架复制；所有内容为 body 原样切片；既有门禁/预算/权限保留；参数 backward compatible；遍历正文、最多六 focus 排序，不增加网络或模型。受测 manifest 对照仅两生产文件变化，大量既有 dirty 工作保持。

冻结完整后端回归 1011 passed / 2 deselected（58.97秒）；新测试共24项。不要把脚本模型结果当真实质量。

### 旧轨迹回放并未消除全部根因

按上一批单跳三模式相同 corpus、question、requirements 回放选段，完整 SourceExcerpt 分别为 P&E 2988 / Workflow 2976 / MA 2963 字符。新段落范围与旧窗口不同，但 thread_id 的关键主键解释仍未进入这些摘录。

原因已核对：原词项规则保留 that / using 等通用词与子串匹配；这些词在该问法下使介绍/后端说明等段落得分高于真正解释段。结构边界与均衡尝试不等于语义相关性判断，不能宣称 thread_id 缺口已经解决。此次不偷偷扩停用词表、不加主题特判或参考答案词项。离线结果也不能重用旧模型回答冒充新质量。

另外，模型把换行改为空格而失败的 494 字符 quote 仍属独立未修问题。省略提示不能防止所有错误缺口声明；抓取已丢失的尾部无法由 selector 找回。

## 付费前登记

本节在真实调用前登记，只跑唯一批次一次；离线全量回归通过后启动。

| 项目 | 固定值 |
| --- | --- |
| 批次 | structure-selection-real-answer-20261003 |
| 题目 | single_hop-dev-01 / multi_hop-dev-02 / version_boundary-dev-02 |
| 模式 | P&E / Workflow / MA，每题每模式一次，共 9 个 Answer |
| 模型 / 资料 | doubao-seed-2.0-lite，temperature=0，最多4096输出token；7篇冻结官方资料，本地search/fetch |
| 输出 / 记忆 | Answer最多2000字符，长时记忆关闭；Report仅离线回归，不合并质量统计 |
| 单运行上限 | 40逻辑 / 80 Provider / 24工具入口 / 12分支轮 / 360秒 |
| 整批上限 | 360逻辑 / 720 Provider |
| 评分 | 隔离Ragas 0.4.3同配置/scorer/输入限额，最多144 Provider，只评分一次 |
| 排除 | 不扩预算、重跑、改gold/裁判、临时裁剪评分正文；不新增baseline/test split |

规范化 dataset SHA-256 为 `44da14cc98057d2aa763c0c2117147b71b13167ceeb63ee137aa12c4e0a69dec`，corpus 为 `ffd9e00644024250f508a0d27054c3b96b68e4065b5f0a1ab520ac9648104b8f`，已以 DTO 内容再次核对 analysis-card。三个登记目录启动前均不存在。凭据仅验证存在，未导出。Gold只进入评分侧。

HEAD冻结为 `f2b4f5dc49207b10b0a1e42ecf45018c31b8cd88`，包含设计文档，不代表全部工作树实现；以manifest哈希/source_snapshot留样。命令见 [实施计划](../superpowers/plans/2026-10-03-structure-aware-selection.md)。全量回归与真实研究/评分期间不改源或HEAD。

启动后研究身份为 `6c793c234a927e5994e2facc42e8f9b9d5220c6436e61312158e4aa3d96783f2`，185 个 manifest 文件已逐份复制/校验 SHA-256，不含凭据；新测试另存：selector测试 `be6954f52eaf65e884661a81e3f3c0a6bb5e9471d79d58c2af26facbce75876e`，入口测试 `0f1e5fc3bc3a5b845386b0015951751a0f13536da074f48011273fc922d1dcbe`。185份不是包含1011项测试的完整工作树快照。

与上批逐字段核对：模型、limits、context_allocator、数据哈希、tools/memory backend、模式、重复次数、输出参数和安装包版本完全相同。

## 真实结果与质量

研究、唯一原生评分与严格compare全部完成。三题已调试dev、每模式一次、同模型裁判、无独立人工盲评，不作因果/显著性/商业产品或生产可靠性结论。没有新baseline，严格配对n=0、delta/CI=null。真实模型加冻结本地资料，不是生产实时联网端到端通过。

### 运行结果

唯一9条研究运行全部留样，退出码1（存在partial，并非进程异常）。4 completed / 5 partial / 0 failed，9条非空答案，answered=4。共191逻辑调用=191 Provider尝试，87工具入口；input=754,331 / output=89,307，missing usage=0，Provider错误=0，来源artifact错误=0，费用null（未配置价格，不能说免费）。45个纯write_todos轮、22个实际researcher分支；不是把规划查询数或branches当完成数。

研究CLI的三模式citation_ok均1，只是宿主链接/编号有效性，非逐主张引用蕴含或答案质量满分；粗粒度gold URL覆盖均约0.833，也不是事实F1。每条最终选择1份完整source body（单跳50,902、多跳60,650、版本68,295个Python字符）供原生Faithfulness评分，不临时裁剪到writer摘录；含非BMP字符的.NET UTF-16长度与Python字符坐标不能混用。

| 题目 | 模式 | 状态 / 原因 | 逻辑 / 工具 | 纯待办 / 实际分支 | 秒 |
| --- | --- | --- | ---: | ---: | ---: |
| 单跳 | P&E | completed | 35 / 18 | 8 / 4 | 194.11 |
| 单跳 | Workflow | partial / insufficient_evidence | 10 / 5 | 1 / 1 | 75.27 |
| 单跳 | MA | partial / no_research_progress | 23 / 12 | 3 / 3 | 137.42 |
| 多跳 | P&E | partial / insufficient_evidence | 15 / 6 | 3 / 2 | 129.41 |
| 多跳 | Workflow | partial / insufficient_evidence | 17 / 8 | 3 / 2 | 118.83 |
| 多跳 | MA | completed | 35 / 14 | 11 / 4 | 190.85 |
| 版本 | P&E | completed | 20 / 8 | 6 / 2 | 129.34 |
| 版本 | Workflow | partial / insufficient_evidence | 16 / 7 | 4 / 2 | 97.03 |
| 版本 | MA | completed | 20 / 9 | 6 / 2 | 72.40 |

初始规划各保留2个固定需求；除Workflow单跳1个查询外，其余2个初始查询。P&E三个样例的角色逻辑调用分别为 planner1/researcher30/evaluator2/replanner1/responder1、planner1/researcher12/evaluator1/responder1、planner1/researcher16/evaluator1/responder2；仅实际发生的调用计数，不把宿主阻止的尝试记成模型输入。

### 与上一批的描述性对照

| 模式 | completed（旧→新） | 非空答案（旧→新） | 逻辑调用 | 纯待办 | 实际分支 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E | 1→2 / 3 | 3→3 / 3 | 67→70 | 19→17 | 7→8 |
| Workflow | 1→0 / 3 | 3→3 / 3 | 57→43 | 18→8 | 6→5 |
| MA | 2→2 / 3 | 3→3 / 3 | 59→78 | 13→20 | 7→9 |

总completed仍4/9，failed仍0；模型调用183→191（增加8，4.4%），工具81→87；纯待办50→45，比例27.3%→23.6%。P&E单跳/版本partial变completed，但多跳completed变partial；Workflow版本completed变partial；MA三题状态不变。不得只展示P&E两题改善，也不能宣称整体更省或更可靠。所有配置和资产相同，但模型输出与规划本身也有变化，不能把一次差异严格归因于selector。

### 原生质量评分

隔离Ragas 0.4.3评分退出码0，只运行一次；72/144 Provider尝试全部status=ok，input=232,635 / output=76,902，missing usage=0、费用null。研究加评分共263次Provider尝试，input=986,966 / output=166,209。27/27指标槽位ok，0 N/A、0 error，没有裁剪正文、补零或重评。

裁判配置逐字段与上一批相同；scorer SHA-256为 `69144d3c8faeb2f2c77bd68c5139e435baa94f2b19ddbcea2064246c80c17688`，评分输入SHA-256为 `7dcdec53d154f288404927a37b0f1809e375a39b3d4f56c7bf1398b08d452525`。strict compare退出码0，精确输入、研究manifest、评分身份、数据/资料与analysis-card核验通过；没有baseline，所有严格配对n=0、delta/CI=null。

| 模式 | completed | partial / failed | 事实F1（有效/全部） | Faithfulness（有效/全部） | Goal（有效/全部） |
| --- | ---: | ---: | ---: | ---: | ---: |
| P&E（主模式） | 2/3 | 1 / 0 | 0.287（3/3） | 1.000（3/3） | 0.667（3/3） |
| Workflow | 0/3 | 3 / 0 | 0.223（3/3） | 0.690（3/3） | 0.333（3/3） |
| MA | 2/3 | 1 / 0 | 0.390（3/3） | 0.808（3/3） | 0.667（3/3） |

| 题目 | 模式 | F1 | Faithfulness | Goal |
| --- | --- | ---: | ---: | ---: |
| 单跳 | P&E | 0 | 1 | 1 |
| 单跳 | Workflow | 0 | 0.5714 | 0 |
| 单跳 | MA | 0 | 0.6667 | 0 |
| 多跳 | P&E | 0 | 1 | 0 |
| 多跳 | Workflow | 0 | 0.5 | 0 |
| 多跳 | MA | 0.5 | 0.9 | 1 |
| 版本 | P&E | 0.86 | 1 | 1 |
| 版本 | Workflow | 0.67 | 1 | 1 |
| 版本 | MA | 0.67 | 0.8571 | 1 |

这是available-case均值与覆盖，不是用户问题正确率。与上一批：P&E F1 0.377→0.287（均3/3）、Faithfulness 0.783→1、Goal 0→0.667；Workflow F1 0.307→0.223、Goal 0→0.333（均3/3），Faithfulness 0.833（2/3）→0.690（3/3），有效覆盖不同不能直接宣称升降；MA F1 0.370→0.390、Faithfulness 0.833→0.808、Goal 0.333→0.667（均3/3）。不能把Goal或Faithfulness单项改善包装成整体质量提高；裁判风险见下文。

### 实际输入与原文支持审计

只读诊断 `tmp/structure-selection-diagnostics.py` 逐次解析记录中的实际 evaluator `EVIDENCE_VIEW_JSON`，对照当前调用的可见 passages，而不是把全体历史 visibility 的并集当当前输入。它没有调用模型、改变评分或写回状态。

三模式单跳的实际评估输入均没有送达原文的 primary key 解释，验证了旧轨迹回放限制，不声称结构优化已解决该事实漏选。

| 单跳模式 | 实际支持问题与状态 |
| --- | --- |
| P&E | 第一轮 super-step quote 的 passage ID 写错一位，宿主拒绝；补查后两个需求各有可解析逐字支持，runtime completed。但 thread_id 答案主要解释为 O(1) 查找与交互记忆，而非完整原文的主键与读取/恢复原因。completed 不等于质量通过。 |
| Workflow | super-step quote 有效；thread_id quote 删除原文反引号而拒绝，r2 缺口，partial / insufficient_evidence。答案把“当前无有效支持”表述成“封存文档缺失说明”，完整原文实际含说明。 |
| MA | 第一轮 thread quote 长446，未超500，但把换行变空格而拒绝；补查后 super-step quote 长420，含拼接省略号，非原文子串，r1/r2缺口，partial / no_research_progress。答案也出现过度的文档缺失声明。 |

运行期间核对185份源与快照哈希差异0，HEAD不变。上述问题未通过放宽门禁、重跑或临时改词表规避。

多跳 P&E 返回的一个 SupportDraft.quote 长513（上限500），使整个 assessment schema 校验失败，状态 partial / insufficient_evidence，缺口含 evaluation_unavailable。同一响应内另一段268字符的逐字 quote 虽在可见段内，也不能算整个无效评估已验收。两条研究需求和足额预算均仍在；不能归因于预算或官方资料缺失。

Workflow 多跳的两段恢复支持172/268字符均为当前可见原文子串；重复副作用的两段450/156字符均非当前原文子串，r2宿主校验失败。回答没有完整恢复输入 Command(resume=...)，并继续把原文支持失败转述成资料缺口。这两种失败没有在本轮混修。

MA 多跳第一次评估四条 quote 均未逐字匹配；补查后实际输入保留相同五个范围，三条逐字 quote 有效、一条仍无效，但每项需求至少有有效支持，runtime completed。回答提供相同thread ID、Command(resume=...)、节点重启与幂等方案，不过仍把移动副作用到中断后描述成保证只运行一次，不能视作外部服务通用 exactly-once 保障。该样例35逻辑调用，上一批同题16次；不掩盖开销增长。

P&E 版本题两项均有有效原文支持（129/209字符的回调说明、112字符的writer限制），另一185字符引用仍非当前原文子串；没有把全部quote计为有效。回答先出现JSON解析失败，使用既有一次合并纠正后 completed，共20逻辑调用、2次responder。不能仅凭本题成功声明引用复制问题已根治。

Workflow 版本题209字符回调支持、112字符writer支持有效；290字符的原因说明quote空白被改写而拒绝。r1的coverage同时引用有效finding-1与无效finding-2，既有严格覆盖校验拒绝该项，partial / insufficient_evidence。最终答案保留两个核心结论，不因partial而把答案评分补零，也不因文字答对而冒充运行门禁完成。

MA版本题三个quote（129/209/112字符）均是实际输入的唯一原文子串，两个需求有效，completed。核心答案与P&E版本题接近；固定裁判评分另列，不凭运行状态推算质量分。

### 裁判风险（保留原始分数）

P&E单跳原生评分为Faithfulness=1、Goal=1、F1=0。已核对实际F1精度侧NLI输入：context确实包含“Full StateSnapshot checkpoints ... super-step boundaries”与thread_id主键说明，但裁判理由却说context没有checkpoint、super-step信息，理由与实际输入不符。两条回答claims又是较长的复合主张，加入了短reference未列出的调度/O(1)/交互细节，严格精度可能受参考粒度影响；不把全部差异都归因于语言或裁判，也不把F1=0视为所有内容均错误。

同样的主键/恢复reference在反向NLI中前两项被判支持，Goal二值判定也认为两个核心目标达到，而Faithfulness使用完整selected source body、并非每条writer引用或当前摘录的语义核验。不同指标范围本来不同，但出现明显NLI理由异常说明本批仍缺独立人工校准。保持scorer、gold与单次原始结果，不重评挑分；报告须同时呈现运行门禁、指标值及局限。

P&E多跳Faithfulness=1，但答案只是拒答并称没有具体恢复/重复副作用处理方法。裁判把全部五条缺口声明判支持，理由将原文的恢复与幂等建议解读为仅原则性指导。已核对本次NLI请求确实包含Command(resume...)、same thread ID和idempotent相关正文。因此即使该指标为1，也不证明答案完整或不存在错误缺口；不能用Faithfulness作为唯一产品验收。

MA多跳Faithfulness=0.9（10条statement有9条支持）。唯一0的statement是“共有两种推荐处理方式”，理由原文列出三种；但最终原答案说“有两种推荐处理方式”，拆分时增加了排他性的“共有”。这涉及主张生成改变数量限定的风险。也不能用这个0.9证明“移动到interrupt后保证只运行一次”的边界可靠；裁判在本批未因此扣分。后续独立校准应检查语义拆分是否保留量词、限定与否定，不回写本次结果。

MA版本Faithfulness的唯一0为生成statement “Python 3.10 refers to any Python version less than 3.11.”，NLI指出3.10并非所有低于3.11的版本。原答案是“在Python 3.10（即Python < 3.11）中”，其中“即”也不够严谨，更准确应说“属于<3.11范围”；但拆分新增了any，不能直接当原答案明确声称所有版本等同。保持该扣分，人工校准需同时检查原答案措辞、拆分忠实性及NLI，而不简单归因到单一环节。

## 留样与后续优先级

研究与评分全部结束后再核对：当前source_identity完整枚举185文件与manifest一致，manifest自身内容哈希正确，185份source_snapshot哈希全部相同；HEAD及两个另存测试哈希不变，judge与旧批相同，scorer哈希不变。保留全部9条、partial、失败引文、Provider计量和原始裁判结果，没有整体Git提交。

- 研究manifest：`../../tmp/structure-selection-real-answer-20261003/manifest.json`（本地实验留样）、9条完整研究记录：`../../tmp/structure-selection-real-answer-20261003/records.json`（本地实验留样）、源文件留样：`../../tmp/structure-selection-real-answer-20261003/source_snapshot/`（本地实验留样）。
- 27项原生评分：`../../tmp/structure-selection-real-answer-quality-20261003/quality_scores.json`（本地实验留样）、72次评分尝试与裁判理由：`../../tmp/structure-selection-real-answer-quality-20261003/attempts.json`（本地实验留样）。
- 严格身份与统计结果：`../../tmp/structure-selection-real-answer-comparison-20261003/comparison.json`（本地实验留样）。
- 只读实际输入审计：`../../tmp/structure-selection-diagnostics.py`（本地实验留样）。

本轮交付的是批准的结构选段与固定要点取材，不是可靠产品验收完成。通用离线测试保护了完整结构、均衡、原文坐标和旧契约，但单跳关键解释仍漏选，真实F1没有全面提高，Workflow运行完成率降为0/3。简历可如实描述可追溯评测与失效定位，不应写成总体质量显著提升或生产端到端全部通过。

下一步先独立设计可靠引用构造：模型选择可引用短片段编号，由宿主从原文生成quote，避免错ID、空白改写、跨段拼接和超500；不取消可见性、原文坐标、语义与覆盖门禁。然后独立调整通用词项排序/标识符相关性，修正“当前无有效支持”被写成“官方资料没有”的错误缺口。评测侧需要冻结rubric、独立人工校准拆分/NLI/Goal，并登记未见测试集与重复实验；不回改本批gold或裁判。以上本轮未实施，新的行为修改需另行规格确认。

Report真实质量、生产实时联网端到端、多次重复、未见test split、不同裁判与独立人工盲评仍待验证，不先以扩大预算代替这些验收。
