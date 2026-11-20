# 原文读取覆盖修复与重复验收

本轮继续处理[上一轮残留问题](../2026-11-09-root-cause-optimization/README.md)。修复的是共用原文选择器的确定性缺陷；没有增加模型阶段、扩大预算、修改 Writer/裁判提示词或降低门槛。

累计完成 **40 次真实 Runtime 执行，40 次均通过本项目的任务验收门禁**；来源范围与预算检查也均通过，无未处理运行异常。这里是 6 道既有问题的多次运行，不是新增 40 道题，也不表示通用准确率或原 30×3 全量矩阵已经重新通过。

## 根因

原失败 Trace 中存在同一个信息断点：

- Multi-Agent 的暂停前提题，读取查询为 `interrupt() prerequisites checkpointer thread_id compile workflow`。选择器命中 `thread_id` 后，优先并反复选取含这个标识符的段落，将没有该拼写的完整前提列表排除；Evaluator 和 Writer 都没看到 JSON-serializable 条件。
- Plan-and-Execute 的历史协调题，查询为 `trim_messages remove stale messages history pruning rules`。代码示例占满窗口，“删除后历史必须有效”的 Warning 及提供方配对规则没被读到。下游反复补查仍缺同一规则，因而持续判为无法协调。
- Warning/Note 等文档提示块内部有空行，旧分段器会把规则与其后条件列表拆开。单独读到引导句或例子，不能替代完整规则。

将原 Trace 查询原样送回选择器，在相同 3000 字符上限下，两项事实缺失都能确定性复现；对应测试先失败，再实施修复。[原查询读取回放](reading-replays.json)保存修复后的逐字原文，窗口分别为 2965 和 3000 字符。

## 修改与边界

修改集中于 `backend/src/deeptrace/tools/evidence_views.py`：

1. 每个 API 标识符仍保留基础命中；其余空间按问题词的相关性和区分度选段，普通参数名不再排除全页其他相关规则。
2. 明确限定 API 的查询仍优先其实际章节，并保留严格实体匹配；不把 `RunNodeSuffix` 当作 `RunNode`，不让其他 API 的泛泛描述挤掉目标章节。
3. Warning、Note、Tip、Info、Important、Caution 内部的空行不再把一个提示块拆散。先保留一个与至少两个问题词相关的完整提示块；限定 API 时仍受章节边界约束。
4. 过大的提示块整体省略，不截出半个条件组；实际已读范围、引用原坐标与现有字符预算仍约束选择，不能借提示块跨越授权范围。

新增 7 个回归测试，覆盖真实失败查询、重复标识符、完整条件组、过大块省略、实际读取范围与无关 API 提示块。开发中扩大召回一度破坏既有 API 章节测试，已恢复其边界保护，未删除或放宽原测试。

## 原生 LangSmith 实测

使用同一个 `deeptrace-grounded-v1` 数据版本 `2026-11-09T09:26:48.687291+00:00`。每题输入同一完整 14 份冻结文档，参考答案只供评分。模型、20 次调用/100000 输入 token 上限及 v4.1 裁判规则保持不变；正确性和证据支持均要求 ≥ 0.8。

| 阶段 | Workflow | Plan-and-Execute | Multi-Agent |
|---|---:|---:|---:|
| 主体修复：两道残留题各重复 3 次 | 6/6 | 6/6 | 6/6 |
| API 边界修正后：两题各重复 2 次 | 4/4 | 4/4 | 4/4 |
| 最终限定 API 提示块保护后：两题各复核 1 次 | 2/2 | 2/2 | 2/2 |

另有 Workflow 的对象定义、策略比较、版本边界、资料不足四道旁路问题，**4/4 通过**；资料不足题没有因扩大召回而编造数值。

原生实验：

- 主体修复：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/fb55968d-c9b0-4277-b740-78021af2f972)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/d50da45c-11eb-48ff-958a-970c2823da0b)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/05d1d0d5-f18c-4f83-9fee-178df8217040)。
- 重复回归：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/92cac0df-786e-415a-b260-7b58d462777f)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/aa80441f-9ab2-4f3d-84af-8929a124dce0)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/e3033076-4333-4334-92b5-f640bacb6e35)。
- 最终代码复核：[Workflow](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/a4869ccb-2f1f-4f4f-9f7d-fc238a4d22fb)、[Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/760e1774-05e1-4ad9-9723-5b878120d685)、[Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/afc4d619-9e5e-446f-b2ba-dab10d9281d4)。
- [四道旁路回归](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/36bc61bc-6104-4438-a838-472a36798e3c)。

两次裁判超时导致初始命令门禁非零；通过原生 `rescore` 补评同一份目标答案后通过，目标未重跑、原始超时反馈仍保留。最终 40 次都有明确验收判定。[逐运行快照](results.json)包含完整答案、来源、反馈、预算和模型尝试数，并保留上一轮用于比较的原始 12 次运行。

## 效率观察

以下仅比较同样两题、三种策略的固定题回归。Provider 尝试数包含重试；裁判调用不计入目标执行。

| 批次 | 样本数 | 尝试数中位数 | 协调题尝试数中位数 |
|---|---:|---:|---:|
| 上一轮规划优化后 | 12 | 7.5 | 12 |
| 本轮 API 边界修正后的重复回归 | 12 | 6 | 6 |
| 本轮最终代码复核 | 6 | 6.5 | 9 |

读取规则更完整后，已观察到协调题减少重复补查；最终复核仍有波动，因此分别列出各批次，不只展示最佳一批。样本少、不同批次并发不同，不把它解释为生产耗时或费用降低的因果证明，也不将缺少 provider usage 当作零消耗。

## 工程验证与范围

最终后端离线全量回归：**1486 passed，1 deselected，33 warnings**。原文仍逐字引用、坐标保持可校验；没有新增绕开 Gateway 的工具通路。本轮未修改前端或引入新模型阶段。

这些已参与调优的题只能用于回归，不能证明对全新问题稳定泛化。本轮没有再做完整 90 次矩阵、开放联网全测、部署或压力测试；历史失败矩阵保持原样。下一次扩大范围时，应锁定本轮代码和数据版本，再检验未参与调优的问题。
