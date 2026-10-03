# 真实联网共享循环效率验证（2026-10-03）

## 结论

三模式真实联网研究与原评分器评分已各完成一次，全部结果保留。P&E/WF从iteration_limit变为程序运行completed，但严格来源/内容验收仍0/3通过；MA触及Gateway额度并partial。主模式F1从.80降为.44，WF升至.89，MA降至.57，本轮没有达到质量改善目标。输入token下降不代表正确答案更高效；搜索请求总数从8增至11，用户优先的外部检索调用目标也未整体改善。

## 口径与实现

目标：保持原评分口径，争取提高质量；不增加研究轮数，不更换模型、评分器或检索后端。主要模式为Plan-and-Execute，Workflow/Multi-agent同题对照。当前实现分支需求映射、宿主验证的finish_research、最近3组完整交换及8k软输入目标。全局评估、Writer、原文/引用/checkpoint不改。

非法初始映射回退为一个完整问题分支，保留合法requirements；supplement_targets优先于初始映射。finish只在最后一个本地工具位置、前置调用成功、已有todo全部完成、至少一条合法候选支持通过当前来源授权/ACTIVE/版本/hash/原文验证后成功。成功摘要进入outcome和checkpoint，不是全局coverage证明。固定问题、约束、当前来源身份与最新完整交换保持；软目标装不下时记录诊断，硬预算仍不可突破。

离线评测脚本模型适配了紧凑输入及新收尾协议，属于确定性管线测试，不作为真实质量成绩。旧无映射规划fixtures更新为显式映射；超限查询的映射仍包含已删除查询时按新契约降级，不弱化来源或约束断言。新增finish调用纳入本地计量，不混入Gateway和搜索调用。

本轮没有实现联网CLI多题推广或SDK直接计量，也未修复canonical版本路径与Writer结构化生成。这些是独立工作，不声称已完成全部规格。真实搜索尝试仍根据保留Gateway轨迹/重试推断，不冒充供应商账单或精确HTTP次数。

## 回归与审阅

TDD：finish测试12失败→12通过；初始目标契约15失败/2已通过→17通过（首个测试样例把非法r9当合法，已改为合法r4后再观察预期失败）；紧凑上下文4失败→4通过；finish本地计量1失败→2通过；manifest策略身份1失败后实现。当前全量1138 passed、2 deselected（116.01秒）；独立Ragas环境34 passed（6.56秒）。定向策略/上下文/计量223通过。Ruff核心变化和compileall通过。

五轴自审：正确性检查协议配对、同批前置效果、失败优先与分支/全局完成边界；可读性将支持验证独立为小模块；架构仍单一共享研究循环；安全保留原授权/来源校验与不可信数据标签；性能仅编码有界近期交换，候选支持完整DTO不反复发送。没有新增依赖。审阅是代理自审，不是独立模型或人工盲审；附加审阅检查文件不可用，不假称已读取。

## 付费前登记

保持旧联网题asyncio-live-01及金答案，1题×3模式，各一次；temperature=0、doubao-seed-2.0-lite、4096输出token、Answer最多2000字符、关闭记忆。每分支12轮；每运行40 logical/80 Provider/24 Gateway/360秒；研究批次120 logical/240 Provider；评分48 Provider。金答案仅在评分导出侧，不注入工具来源授权。

登记时间2026-10-03 22:19:13（Asia/Shanghai），研究身份`f81b6e0cfd76a0fcfaee2e63a76188318efdc9f8fbcd6e0688bc30450b048858`，源码身份`77331179686cfc315bb14a52fe5d509ef0e7184feb222dbd59f62b89c599b5ae`。配置、数据、源码、测试与评分器哈希留样于`tmp/live-efficiency-freeze-20261003/registration.json`及source_snapshot，不复制.env。实际运行manifest身份已与登记核对一致。

旧结果只作描述性参照：三模式F1均.80；P&E Faithfulness=.80/Goal=0，WF/MA均1/1；三次均partial/iteration_limit。耗时分别130.453/118.496/92.457秒，输入token210577/232579/196396，输出8053/11470/8657；搜索Gateway请求3/2/3，各无缓存/重放/重试。全部6个分支12轮截尾，不能当成正常完成所需轮数。

## 当前执行状态

三模式研究与评分已全部结束。研究CLI退出1是保留MA partial的结果，不重跑；评分退出0表示9项评分均正常返回，不表示产品验收通过。P&E/WF运行状态completed，MA partial/tool_error。新结果保存在`tmp/live-efficiency-answer-20261003`，评分目录固定为同名`-quality`。所有partial/failed保留，不重新执行择优，不重判低分。

每模式仅一次、已知诊断题、网页可能变化、同模型裁判、无新增baseline和独立人工复核。无匹配的任务/版本约束合格成功样本时，成功效率对照为NA；允许展示全部运行的逐项原始成本，但不把更早失败包装成节省。供应商credits/价格未知保留null，fetch/read不计入搜索API请求。

## 实际研究用量与轮次

| 模式 | 程序运行状态 | 秒数：旧→新 | 输入token：旧→新 | 输出token：旧→新 | 搜索请求：旧→新 | 新Provider/Gateway |
| --- | --- | --- | --- | --- | --- | --- |
| plan_execute | completed | 130.453→112.700 | 210577→70308 | 8053→6683 | 3→1 | 16 / 7 |
| workflow | completed | 118.496→104.709 | 232579→103904 | 11470→7838 | 2→4 | 22 / 14 |
| multi_agent | partial/tool_error | 92.457→114.611 | 196396→160172 | 8657→10816 | 3→6 | 35 / 24 |

三次研究73 logical/73 Provider、输入334384/输出25337，全73次usage有效，费用null。搜索请求合计8→11，各次新search无缓存/重放，工具重试均0，故推断供应商SDK搜索尝试与search请求数一致；没有直接HTTP/账单观测。WF/MA缓存仅为fetch_page（1/3次），不能据此宣称搜索缓存命中。旧/新总耗时分别341.406/332.019秒，为三次逐运行时间之和，不是并发分支时间之和。

本地record/todo/finish分别P&E 2/2/2、WF 2/1/2、MA 2/1/2；全部执行计量13/19/29（Gateway另为7/14/24）。MA还有两次研究工具请求因评测Gateway上限在实际执行前拒绝，不计供应商调用；Agent所有请求与成功执行不是同一分母。

| 模式 | 分支责任 | 实际研究轮次/上限 | 退出观察 |
| --- | --- | --- | --- |
| plan_execute | TaskGroup/gather对比 | 9/12 | finish成功 |
| plan_execute | CancelledError处理 | 4/12 | finish成功 |
| workflow | TaskGroup/gather对比 | 7/12 | finish成功 |
| workflow | CancelledError处理 | 12/12 | 最后一轮finish成功，不是iteration_limit截尾 |
| multi_agent | TaskGroup行为 | 11/12 | 工具错误导致分支停止 |
| multi_agent | gather行为 | 11/12 | 工具错误导致分支停止 |
| multi_agent | CancelledError处理 | 9/12 | 两次finish_no_valid_findings，随后工具错误停止 |

研究模型轮次为13/19/31；其他角色为3/3/4（MA最后回答含一次JSON纠正）。没有设置24轮，没有任何新分支因iteration_limit停止。MA分成三个责任分支，预算分配仍受整次24 Gateway约束，不能把分支平均轮次下降解释成全模式优化成功。无匹配的严格约束合格成功样本，成功效率对照仍NA，不报告节省百分比。

## 来源与内容复核：仍未通过产品验收

P&E最终引用3.14.8而非题目指定3.11，且明确把gather默认普通异常后的行为写为“取消其他任务”。该错误来自研究候选，不是Writer首次捏造：候选对gather引用的n单元停在`If return_exceptions`，未包含下文的关键否定条件；评估器照搬该候选并将coverage判covered。完整抓取正文实际明确写着其他awaitables不会取消。TaskGroup的一条候选还引用了代码示例而非所主张取消行为的支持句。字面出处合法不等于主张受到原文蕴含。

WF找到了3.11繁体页面，却最终主要引用3.14任务/异常文档，并把TaskGroup异常传播说成“直接传播”，未交代题目需要的异常组聚合边界。运行completed不等于版本条件和答案义务通过。

MA收集3.14英文、3.11中文与3.14中文三份正文，均落在同一canonical URL，产生共享来源版本互相作废。`tmp/live-efficiency-source-replay.py`用本批实际正文、URL和时间在独立内存仓库重放，无网络/模型调用，重建全部来源ID一致：英文3.14→superseded，中文3.11→superseded，中文3.14→active；重复缓存/再次摄取英文正文仍返回superseded。读取边界只接受ACTIVE或显式历史授权，研究分支没有历史授权，因此不可把此现象修成放宽来源门禁。实际MA出现5次evidence_not_authorized，WF出现2次；MA既有发现随后失效，finish拒绝后继续补读，24 Gateway额度耗尽。主因链路已定位为抓取canonical身份→仓库版本替换→读取/记录有效性→额外检索；不是简单“12轮太少”。

评测RequestLimitReached在工具边界被通用异常映射为tool_internal_error/最终tool_error；保留原始异常，不把它误报为联网供应商故障。MA回答首次JSON无法解析，经一次纠正仍保留tool_error降级状态。

逐帧字面审计通过：当前源码及完整留样一致，3次研究12条候选，最后归一化21条支持，Writer丢失支持0，artifact_errors0，引用ID均有来源。它不是蕴含或版本正确性的证明；重放评估引用对重复文字使用首个位置，不声称等于原在线坐标。

下一步应独立修来源身份（保留实际版本/语言URL，canonical仅作元数据），再收紧既有评估器的主张—支持句/条件核验，维持现有评分器与资源上限；不能继续把quote存在就称supported。这些下一步方案尚未在本轮冻源实现，不以扩大轮数掩盖。

## 原评分器最终结果

| 模式 | Factual F1：旧→新 | Faithfulness：旧→新 | Goal：旧→新 | 指标有效分母 | 完整产品验收 |
| --- | --- | --- | --- | --- | --- |
| plan_execute（主模式） | .80→.44 | .80→.875 | 0→0 | 每项1/1 | 未通过 |
| workflow | .80→.89 | 1→.833333 | 1→0 | 每项1/1 | 未通过 |
| multi_agent | .80→.57 | 1→.875 | 1→0 | 每项1/1 | 未通过 |

9/9 metrics ok，NA=0/error=0；每模式一道已知题一次，不是稳定泛化分数，不计算显著性/P95。评分器、Ragas0.4.3、模型与原裁判配置不变，不为低分重新评分。Goal仍是问题+最终答案视图，不验证网页版本或完整运行状态，不能代替上述来源/义务验收。

评分24 Provider/上限48，输入80382/输出36770，全部usage有效，费用null。研究与评分合计97 Provider，输入414766/输出62107；不混入运行token/时间的逐模式表中。没有新增baseline，严格配对因果效果或成功成本节省均不可得。

## 原始产物与复现

- [运行records](../../tmp/live-efficiency-answer-20261003/records.json)、[实验manifest](../../tmp/live-efficiency-answer-20261003/manifest.json)、[评分输入](../../tmp/live-efficiency-answer-20261003/quality_eval.json)。
- [原始quality_scores](../../tmp/live-efficiency-answer-20261003-quality/quality_scores.json)，同目录identity.json和attempts.json完整保留；progress.json是最后进度留档，不代表仍在运行。
- [预登记与源码留样](../../tmp/live-efficiency-freeze-20261003/registration.json)，[预检脚本](../../tmp/live-efficiency-preflight.py)。原运行HEAD为06cdde6加dirty源码身份；后续文档提交不改变冻源内容，不把现HEAD当原运行源码。
- [字面审计](../../tmp/live-efficiency-audit-20261003.json)、[审计脚本](../../tmp/live-efficiency-audit.py)、[无API来源重放](../../tmp/live-efficiency-source-replay.py)。

本批冻源后未修改生产、评测实现、测试、数据或评分器。原始report.md仍含旧“offline corpus”标签，实际manifest为live_web/corpus_sha256=null，轨迹为真实Tavily搜索与网页抓取；本报告明确纠正该展示，不以错误标题冒充冻结资料实验。

已执行一次的命令（不要为查看结果再次运行，目录与登记必须保留）：

```powershell
# 工作目录 backend
.venv/Scripts/python.exe -X utf8 ../tmp/live-efficiency-preflight.py
.venv/Scripts/python.exe -X utf8 -m deeptrace.eval.live --dataset ../tmp/grounded-handoff-live-assets-20261003/questions.jsonl --run-prefix live-efficiency-answer-20261003 --out ../tmp/live-efficiency-answer-20261003
.venv-ragas/Scripts/python.exe -X utf8 evaluation/ragas_quality.py --input ../tmp/live-efficiency-answer-20261003/quality_eval.json --out ../tmp/live-efficiency-answer-20261003-quality --max-provider-attempts 48 --env-file .env
```

只读审计和本地重放不发API；上述研究/评分命令不是自动重试建议。本轮提交仅自有计划/报告文档，已有dirty源码全部保留供用户审核，不整体打包提交。
