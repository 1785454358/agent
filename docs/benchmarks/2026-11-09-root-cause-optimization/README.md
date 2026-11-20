# 失败定位与有界优化（2026-11-09）

本轮延续[全量验收](../2026-11-09-full-acceptance/README.md)，直接检查原生失败 Trace，复现后修改共享 Runtime 的规划、原文窗口、回答审查和搜索适配。验收阈值、模型、冻结资料版本与全局预算不变，未把参考答案加入运行输入。

后续针对本页残留漏答与过度拒答，已定位并修复读取器的信息丢失，见[读取覆盖修复](../2026-11-09-query-coverage/README.md)。本页保留该阶段的原始失败，不以补测结果覆盖历史记录。

累计完成 48 次生产 Runtime 任务执行和 6 次审查组件回放。48 次均有明确验收判定，无未处理运行异常，来源与预算检查均通过。[逐运行快照](results.json)和[同稿审查回放](review-replays.json)保留答案、反馈、运行 ID 与阶段；不同阶段的改动和失败均保留，不将迭代实验混合成一个准确率。

## 根因与对应修改

| 现象 | Trace 中确认的原因 | 修改 |
|---|---|---|
| Runtime 与 Context 混淆 | 原文区分容器与字段，草稿却把容器组件列成字段内容；旧审查沿用草稿的首句、表格框架 | 审查先核对原问题和原文，再列实际问题，最后生成修正正文；定义题的规划保持对象层级 |
| 暂停前提漏答 | 一份失败 Trace 已含 JSON-serializable 条件但 Writer 忽略；另一些运行的 Writer 原文完全没有这一条件。规划先猜出 checkpointer/thread_id 等示例，下游将示例误当完整清单 | 前提题保持开放的完整条件调查；Writer 不把规划当成完整事实清单；短引用周围优先保留预算内完整段落/列表，避免只截出条件组的第一项 |
| 协调问题过度拒答 | 规划自行要求专用算法、完整分类判据；答案把缺少实现细节解释为约束不能协调 | 规划限制新增验收条件；回答审查区分明确约束、有界推导和未知实现，不要求另有专用算法才允许综合已有约束 |
| 搜索到了错误版本 | 搜索适配把 `site:host/version/path` 变成 host-only include filter 和普通路径关键词；任意匹配版本的页面又会阻止另一个目标页面的补查；合并后的候选上限还可能提前丢掉正确版本 | 原样保留 host/path 的原生 include scope，同时做 host/path 边界校验；按具体路径判定是否需要补查；版本匹配排序前移到候选截断之前，最多两次搜索 |
| 有原文却只返回来源 | 一次审查输出达到 16000 token 上限；另一次只返回 issues、缺少 content/unanswered_points，被结构校验拒绝 | 对结构不完整增加一次有界协议修复，仍重新经过共享模型预算；持续非法输出继续失败关闭。输出长度错误没有通过提高上限或无界重试掩盖 |

Tavily 的 [include_domains 使用说明](https://help.tavily.com/articles/7879881576-optimizing-your-query-parameters)包含带路径的范围示例；本地真实 provider 探针也确认，保留 `docs.python.org/3.11/library/asyncio-task.html` 范围后返回 3.11 TaskGroup/gather 页面锚点。检索提示只是发现线索，来源资格仍由实际抓取原文核验。

实现位置：`strategies/planning.py`、`harness/batch_collection.py`、`tools/search/tavily.py`、`tools/evidence_views.py`、`responses/graph.py`、`responses/fact_review.py`。没有新建第二套 Agent Loop 或评测平台。

## 受控回放与重复执行

先保存三份失败草稿及其实际 Writer 原文，仅重放原有审查组件。旧组件在两个样本上仍失败；改为先审查再生成正文后，协调题从正确性 0.55 提升至 0.9，前提题仍未通过。这证明单靠审查提示不足，因此继续定位原文窗口和上游规划，而非把一次偶然通过当成修复完成。

随后对三道核心失败题（`single_hop-test-03`、`single_hop-dev-02`、`conflicting_evidence-test-03`）在三种策略下分别重复两次。固定数据版本 `2026-11-09T09:26:48.687291+00:00`，同一 14 份完整冻结文档，原生 v4.1 裁判，门槛保持正确性和证据支持均 ≥ 0.8。

| 策略 | 审查/列表修复后，同一三题各两次 | 加入规划范围修复后，同一三题各两次 |
|---|---:|---:|
| Workflow | 4/6 通过 | 6/6 通过 |
| Plan-and-Execute | 6/6 通过 | 5/6 通过 |
| Multi-Agent | 4/6 通过 | 5/6 通过 |

前一轮 Workflow 另测的两个比较题运行均通过，未混入这个配对表。后一轮细分：对象层级题 6/6，前提题 6/6，协调题 4/6；协调题在 Plan-and-Execute 和 Multi-Agent 各有一次仍过度拒答。前一轮协调题为 5/6，因此**不能声称所有类别都改善**。

最终增加的完整段落保护还单独复测了 Multi-Agent 的前提题与协调题：协调题通过，前提题再次漏掉必要条件。说明前提题虽在上一组重复中全过，仍存在不稳定性，不能宣布根治。

原生实验：

- 规划修复前：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/1a8b1ae1-6ae0-4a0e-a422-91e2efb107d9)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/b2e58a8d-d203-421d-ab02-e46b812a49cf)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/8a1467b7-d00a-4ace-b1e5-7d774b2c6da4)。
- 规划修复后：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/f075c91d-f3b5-4ccd-96b0-99d1c47ffc31)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/b1c1fa8b-4f0f-482d-9d76-9619ec153eb7)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/ff571608-e335-442c-8b3c-ab23b0efdd66)。
- 完整段落保护后的 [Multi-Agent 补测](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/d5a8dd98-202c-4fdb-92fe-871b800de617)。

## 旁路退化检查与联网

另用资料不足、版本边界、多跳三个旁路样本检查共享组件，Workflow [3/3 通过](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/0a701499-aa21-48f6-bf9d-582276b6d6de)，未因允许有界推导而编造精度/ROI。

真实联网题的版本召回已改善：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/faa03360-8b39-44c2-9aad-fe9661a5b578)与 [Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/95516bf1-68e0-45c6-a779-cb955a36180c)通过。Multi-Agent 一次取得正确版本但漏掉 TaskGroup 普通失败时取消同伴、清理后重抛等要点，另一次审查只返回 issues 导致安全退化；两次失败均保留，后者触发了本轮协议修复。

协议修复后的 [Multi-Agent 新增补测](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/441cc317-3c93-46d0-979d-d0a54110576e)通过。至此三种策略均有修复后的同题联网通过记录，但前述失败证明这不是稳定性或泛化能力保证。

## 工程验证与结论边界

后端最终全量离线回归为 **1479 passed，1 deselected，33 warnings**。新增测试先复现失败，再验证：路径参数不丢失、跨页面版本补查、截断前保留目标版本、条件组及段落完整性、其他已核实引用的预算优先级，以及审查结构修复的准确计费。回答模块单独回归 123 项通过。

本轮是原失败样本的有界修复和重复测试，没有重新跑一整轮 30×3，也没有把这些已参与调优的问题当成独立测试集。重复执行仍暴露过度拒答、漏答和模型协议不稳定；工程契约修复成立，语义质量目前仍不能宣布全部达标。后续应优先改进需求到证据的完整性核对和不必要缺口的判定，保留失败门禁，避免继续靠追加通用提示掩盖问题。
