# 证据优先重构：联网恢复验证

## 预登记

用户已批准规格 `docs/superpowers/specs/2026-10-03-evidence-first-quality-design.md`。
本轮先做恢复验证，不以降低质量换取省时、省token；未过恢复门槛不扩大付费实验。

- 原诊断题：`tmp/grounded-handoff-live-assets-20261003/questions.jsonl`，asyncio-live-01，三模式各一次。
- 新运行前缀：evidence-first-answer-20261004，独立新目录，不覆盖旧失败/评分。
- 相同模型 doubao-seed-2.0-lite、temperature=0；Answer 2000字符、输出4096、记忆关闭。
- 每分支12轮、每运行40 logical / 80 Provider / 24 Gateway / 360秒；研究批次120 logical / 240 Provider。
- 相同Ragas 0.4.3评分器与金答案；评分独立环境、一次评分、48 Provider上限；费用/搜索credits未知。
- 复测前由 `tmp/evidence-first-preflight.py` 核对模型、数据、预算、评分器哈希，留存src/tests与配置身份，不复制.env。
- 只有共享证据处理策略与必要预算分类变化；未增加Agent、服务、依赖或评分宽松规则。Ruff通过uvx执行，不修改项目依赖。

恢复门槛：主模式F1至少0.80，gather取消行为和TaskGroup异常聚合正确，确实使用题目指定Python 3.11原文；程序completed不能单独表示通过。报告Faithfulness、Goal、所有partial/failed及来源/内容验收。不择优重跑、不变更金答案或评分器。

开销完整报告：时间、输入/输出/总token、search请求及供应商尝试、fetch/read、缺失usage；评分用量单列。历史旧臂没有合格成功时，成功成本配对为NA，不声称证明质量不降或效率成功。

## 实现与自审

共享链路已替换为：实际URL来源身份 → 完整阅读组及短引用 → 原文驱动评估 → 既有Writer。
候选记录仍留档兼容，不作为默认收尾前提或评估输入。实际已读anchor及当前授权、ACTIVE/version/hash/坐标仍校验；未完成todo、未来读取、批次错误、取消优先规则保留。

研究视图最多保留三份去重实际读取预览和最近三组完整协议交换；持久历史不裁剪。工具/评估按完整阅读组分配预算；超限明确省略，不将孤立短引用当成完整条件。无标点超长原文仍可能用既有有界窗口，语义完整性是启发式，不能以坐标正确代替语义证明。

来源/SSRF/权限、原文及引用、checkpoint兼容、预算计量、运行隔离均由回归覆盖。自审由本会话完成，无独立人工或第二评审者，不冒充独立审查。

## 验证与真实结果

完整离线回归：1162 passed、2 deselected；独立评分环境：34 passed。变化模块Ruff和compileall通过。每项行为修复均先复现失败再实施；未放宽旧权限/引用断言，只替换规格明确废止的候选优先/必须record断言。

封存身份：实验`4005539de9608f6f4c4884e600898d6fb19b4e761f9933feb590b7bc7bed1f95`；源码`b1424083b058530af590d4b593acaa80dccb49eb3fe0bfa8f3522b0ba47b5f1f`。运行前、后源码与留样哈希已核对；评分器及judge身份与旧臂相同。

三模式研究和评分已完成，研究命令退出码1（主模式partial）；评分退出码1（Multi-agent的Faithfulness供应商超时）。原文/引用审计：3条运行，17条最后评估归一化supports，Writer遗漏0，artifact错误0。此审计是字面出处/可见性核验，不是语义正确性或独立人工审查。

| 模式 | 本轮F1 | Faithfulness | Goal | 程序状态 | 指定3.11来源 | 秒 | 输入/输出token | 搜索尝试代理数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Plan-and-Execute（主） | 0.60 | 1.00 | 0 | partial / iteration_limit | 是 | 155.33 | 138,923 / 8,840 | 2 |
| Workflow | 0.83 | 1.00 | 0 | completed | 否，混用新版 | 75.97 | 60,734 / 6,311 | 2 |
| Multi-agent | 0.91 | N/A（评分超时） | 1 | completed | 否，新版/3.12 | 171.75 | 133,546 / 11,817 | 3 |

Faithfulness有效评分2/3；F1、Goal有效评分各3/3。completed 2/3，严格指定版本来源1/3，程序完成且内容与来源全部合格0/3。高F1或Goal=1不能代替严格来源/内容验收。MA的评分错误不是0分，未重跑/重评分。

| 主模式参照 | F1 | 秒 | 输入/输出/总token | 搜索尝试代理数 |
| --- | --- | --- | --- | --- |
| grounded-handoff旧质量轮 | 0.80 | 130.45 | 210,577 / 8,053 / 218,630 | 3 |
| live-efficiency上轮 | 0.44 | 112.70 | 70,308 / 6,683 / 76,991 | 1 |
| evidence-first本轮 | 0.60 | 155.33 | 138,923 / 8,840 / 147,763 | 2 |

相对旧0.80参照，主模式总token少32.4%，搜索代理数3→2，但时间增加19.1%，F1仍低0.20；相对上一轮错误效率优化，质量回升但开销增加。两组历史参照均不构成合格成功配对；成功成本比较为NA，不能声称完成效率优化。

研究总计68次Provider尝试，输入333,203、输出26,968、总token 360,171，三模式时长合计403.05秒；Gateway请求44（search7、fetch7、read30），fetch有1次缓存，工具重试0。搜索供应商尝试代理数7来自无缓存/无重放且无工具重试的请求数，并非HTTP/发票或credits测量。

评分独立计量：24次Provider尝试（上限48），23次有usage，1次超时缺usage；已观测输入65,512、输出33,555，完整总token未知。研究和评分费用均未知。Judge/评分器哈希、配置及Ragas版本与旧轮完全一致。

产物：`tmp/evidence-first-freeze-20261004/registration.json`、`tmp/evidence-first-answer-20261004/records.json`、`tmp/evidence-first-answer-20261004-quality/quality_scores.json`、`tmp/evidence-first-summary-20261004.json`、`tmp/evidence-first-audit-20261004.json`；逐条判分在评分目录的`attempts.json`。

### 已确认的剩余问题

1. 主模式第一个分支用完12轮：多次猜测中文整句find，或沿泛化术语反复查找；第二分支10轮。主模式合计16次read、5次find未命中。模型并非缺少轮数配置，存在定位效率问题。真实答案已纠正gather取消行为并保留TaskGroup聚合，仍不能用正确的答案覆盖partial状态。Workflow分支6/5轮，MA为11/5/8轮；上限保持12，不凭本轮单样本调整。
2. Workflow的TaskGroup/gather依据来自默认新版路径，而CancelledError依据来自3.11页面；Multi-agent引用默认新版及3.12，没有3.11。实际URL独立保存已生效，但评估器仍把错误版本说成3.11并判covered：来源身份修复不等于来源约束执行已经可靠。
3. Multi-agent最后评估输入未包含ExceptionGroup，评估仍把“取消其他任务、异常传播给调用方”视为充分，最终漏掉异常聚合。Writer未删掉已接受支持，主要缺口在取材/语义覆盖，不能全部归咎Writer。
4. 主模式F1为0.60（上轮0.44、旧参照0.80）、Faithfulness为1.00、Goal为0。评分逐条日志表明：答案claims 4条，3条被金答案蕴含；“文档出处”被当作金答案未陈述的额外claim；金答案6条中3条被判未覆盖，涉及return_exceptions=True、timeout示例、uncancel例外。TP=3/FP=1/FN=3导致F1=0.60。真实漏答与claim分解/文档出处计分共同影响结果，F1不是“60%的句子错误”。保持这个原始得分，不删claim、不改金答案、不重评分。
5. Goal的第一步提取把end_state压成“已完成对比”等泛化描述，后一步认为没有呈现具体任务结果而判0；这是需要独立审计的评估信号，不能据此忽略真实partial和版本错误，也不能擅自改判为1。

本轮未达到主模式0.80恢复门槛，不启动扩大付费配对或择优重跑。下一步应针对现有阅读定位、版本约束执行和答案条件/例外完整性作局部替换，不新增Agent或大评测平台；评分信号另做独立审计，原始分数保留。

后续多题重复配对需另行封存至少3道新题加诊断题、旧/新源码、运行顺序及硬预算；通过本轮恢复门槛后才启动。
