# 回答交付边界与引用恢复实验

本轮保留的生产改动只有**一次受共享预算约束的引用协议恢复**。写作策略候选没有通过事先规定的条件，已经撤回；没有把组件回放包装成完整 Agent 质量提升，也没有修改参考答案、评分器或门禁阈值。

## 实际保留的修复

最终审查生成不存在的引用编号、或完全没有数字引用时，以同一问题、草稿、规划清单和可见原文重试一次，明确列出允许的来源编号。所有调用仍经过原来的计量和预算网关，第二次仍错误就失败。不会自动把错误编号替换成某个合法编号，也不会清空未答项。JSON、长度、网络和预算错误不在这里重试。

正常第一次调用的消息逐字保持原样。12 份真实历史轨迹回放验证了：输入不变、有效审查结果不变、没有额外 Provider 请求。

另外复用了一个真实历史错误输出（仅有来源 `[1]`，却输出 `[4]`），注入首次响应，再发出 **1 次真实 Provider 纠正请求**，修复为正确编号。首次错误响应属于历史重放；这不是一次全新的两调用 Agent 运行。完整输入、原始错误、实际纠正响应、用量和哈希见 [recovery-verification](recovery-verification/live-repair.json)。

生产差异见 [production-changes.patch](production-changes.patch)，新增测试为 `backend/tests/responses/test_review_recovery.py`。

## 真实实验结果

使用相同 `deepseek-v4.1-flash`、冻结文档、原问题、原始可见段落和原字符上限。12 个 dev 问题各运行 5 个组件版本，共 **60 次真实组件生成调用**，没有重新检索，也没有向生成模型提供参考答案。两个有完整输出的候选使用原 Ragas 与 claims-v3 独立评分；其余失败版本保留原始结果，不补单题、不虚构分数。

| 项目 | 历史基线 | 独立作答＋编号提示 | 请求绑定＋协议恢复候选 |
|---|---:|---:|---:|
| 任务达成 | 10/12 | 11/12 | 11/12 |
| 参考事实 F1 | 0.6417 | 0.5658 | 0.6400 |
| 引用准确率 | 0.9451 | 0.8931 | 1.0000 |
| Faithfulness | 0.9254 | 0.9911 | 0.9282 |
| Claim groundedness | 0.9688 | 1.0000 | 1.0000 |

F1、任务达成、引用准确率各覆盖 12 题；后两项只在相同的 **8 题**上可测，其余保留 N/A。沿用的 Faithfulness / groundedness 评分上下文是已选来源全文，不等同于回答模型实际看到的摘录，不能据此声称所有生成上下文都充分。

这些是固定材料的回答组件实验，基线复用较早生成的历史审查输出；不能比较组件调用量与完整 Agent 总成本，也不能推断端到端 Agent 已改善。原严格完整运行门禁正确拒绝了这种执行配置混用：[component-gate-rejection.json](component-gate-rejection.json)。

候选未满足“F1 至少提升 0.05、单题下降不超过 0.20”等预先规定的条件。最终候选比较题 F1 从 0.97 降至 0.61，整体 F1 没有提升，因此**没有进入新一轮完整 12 题 Agent 测试，也没有启用其写作策略**。任务达成与引用分数的改善不代表整体质量过关。

逐题分数与来源身份验证见 [最终组件比较](component-replay-request-bound-repair.json)、[较早候选比较](component-replay-source-first-numeric.json)，所有版本输出见 [answers](answers/)，实际费用未知，用量见 [results.json](results.json)。受控用量小计另行排除了较早一次混合 pytest 执行的两个真实冒烟测试，后者未完整采集 Provider 用量。

## 已确认但尚未修复的上游遗漏

恢复与外部副作用题的完整原文明确要求恢复时使用同一个 thread ID，但传给最终回答的 Interrupts 摘录没有包含该段。原文坐标、文本、来源哈希和可见性核查见 [source-handoff-incident.json](source-handoff-incident.json)。仅改写作提示无法可靠补回未交付的关键条件；这项摘录选择问题仍未解决。

同时，直接依据原问题作答曾减少未问细节产生的假缺口，但引入了其他单题退步，因此保留为失败实验，不能把它描述成已解决的生产能力。

## 验证与复现

最终生产版本：离线测试 **1632 passed, 2 deselected**，121 项回答与证据边界专项测试通过。Ruff 检查生产改动与新增测试通过。更早的混合测试曾出现一条 aiosqlite 后台线程关闭警告；它不属于最终离线通过记录，未将其隐去或算作无告警验证。

[reproduction-inputs.zip](reproduction-inputs.zip) 包含历史基线、5 版候选的输入导出与源码快照、原始请求/响应、评分输出和评分身份、最终生产修复与测试。实验生成脚本必须配合对应源码快照使用，当前生产代码已经撤回候选接口。离线比较脚本可在当前环境运行，不产生 Provider 请求：

```powershell
cd backend
./.venv/Scripts/python.exe -X utf8 ../docs/benchmarks/2026-11-08-answer-review-boundary/compare_component.py --variant replay-request-bound-repair
```

该命令读取原始私有实验目录。完整可迁移材料在 ZIP 内；来源文件校验、归档哈希、凭据扫描及离线报告重算记录见 [verification.json](verification.json) 和 [final-checks.json](final-checks.json)。分析、生成、评分、代码修复的计数分别保留，不把历史轨迹回放计为新增真实模型调用。

简历可以描述：建立冻结材料组件回放、严格来源身份校验、独立评分、逐题退步检查与失败候选保留机制，并实现受共享预算约束的引用恢复。**不能写成本轮事实准确率已经提升，或达成 100% Agent 成功率。**
