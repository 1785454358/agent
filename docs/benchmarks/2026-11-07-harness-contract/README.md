# Harness 调研与聚合完成契约实验：未通过

调研参考 Deep Agents、Anthropic 长运行 harness、Open Deep Research 和 DeerFlow 的官方资料。[research.md](research.md) 区分上游机制与本项目的推断，[sources.json](sources.json) 记录固定 commit、日期及文件哈希，没有按星数或上游跑分作性能排名。

第一版保留检索分工，但用一个“完整回答原始问题和用户约束”的宿主需求作为完成标准，防止派生子问题扩大验收。真实结果表明它丢失了有用的原子检查，因此**未通过回归，已移除这一配置选项**；实现和测试保存在源码快照中。

## 同条件真实比较

重新执行 12 题 Workflow 基线和 12 题候选，每题一次，另有 6 次其他策略探针。两组模型、冻结资料、参考答案、预算、Ragas 和修正后的 claims-v3 相同。18 道 held-out test 题未用于调优。

| 指标 | 新基线 | 聚合候选 |
| --- | ---: | ---: |
| completed，执行指标 | 11/12 | 12/12 |
| answered，执行标记 | 9/12 | 11/12 |
| 模型调用 | 82 | 77 |
| 工具调用 | 194 | 142 |
| 目标达成评分 | 0.833（12题） | 0.833（12题） |
| 参考事实 F1 | 0.642（12题） | 0.539（12题） |
| Faithfulness | 0.925（8题） | 0.945（7题） |
| 引用分数 | 0.945（12题） | 0.927（12题） |

工具调用减少 26.8%，但 F1 配对差为 -0.1025，目标均值相同也掩盖单题退化。原门禁为 **fail，退出码 1**，没有改阈值。[完整门禁](gate/regression.md)、[逐题和实际契约](results.json)、[评分](scoring/) 均保留。

## 实际遗漏与决策

Agent 审查发现，候选 single_hop-dev-02 只列出 checkpointer 和 thread_id，漏掉 JSON 可序列化的 interrupt 载荷；multi_hop-dev-02 同时出现“从 interrupt 处继续”和“重跑所在节点”的不准确表述。检查变粗后，多余写作仍在，关键事实反而遗漏，不能凭完成率推广。[原始答案](answers/) 可核对。

其他策略探针没有独立质量评分，不能覆盖整轮退化。下一版保留原子需求，增加有界范围审查：[scope review 实验](../2026-11-08-harness-scope-review/README.md)。多个候选是 dev 迭代，不能解释为无偏选模或统计显著性证明。

## 复现

本阶段离线测试 1625 passed，2 deselected；定向测试 66 passed。资源、源码与裁判身份见 [verification.json](verification.json)。[reproduction-inputs.zip](reproduction-inputs.zip) 包含完整质量输入及轨迹、三个实验组的源码快照、评分、metadata、原策略和测试。

解压后使用现有 `python -m deeptrace.eval.regression_cli`：baseline/candidate 指向各自 quality_eval.json，两边各传入 ragas/quality_scores.json 和 claims/claims_scores.json；metadata.json、policy.json 位于解压根目录。两个 mode 都为 workflow，seed=7，out 使用新空目录。预期退出码 1，完全离线。

当前源码已移除聚合选项，重跑旧驱动需要使用其源码快照。一次 dev 运行、同模型自动裁判、评分覆盖不完整等限制保留，没有人工标签或绝对质量达标结论。
