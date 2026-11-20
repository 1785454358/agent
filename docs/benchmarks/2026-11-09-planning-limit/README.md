# planning_limit 定位与优化

## 根因

2026-11-09 回读 LangSmith 中原 Plan-and-Execute / Multi-Agent 的完整 Trace：两种策略都执行了 `insufficient_evidence-test-03`，要求仅凭冻结的 memory concept 文档推导召回精度与财务 ROI。参考答案明确说明没有相关标注评测和财务测量，不能推导。

原规划把指标定义、公式和测量参数拆为事实需求；核验持续返回 missing。补查又扩展到通用 precision/recall 教程和财务模板，不能满足用户的指定资料范围，最后分别达到 `max_replans_reached` / `max_follow_ups_reached`，统一映射为 planning_limit。不是 LangSmith 异常，也不是工具调用普遍失败。

评测入口只传问题，没有冻结原文，却使用实时搜索。它并没有重现旧冻结语料执行条件。原单题冒烟选取还依赖服务端返回顺序，刚好选到不可推导题。Workflow completed 的调度语义也不等同于证据充分，不能据此直接认定另外两种策略更差。

另有确定性的退出原因错误：空补查计划在尚未达到上限时，也被归为 planning_limit。新增失败测试已复现这一点。

## 已修改

1. 空补查计划保留 missing / 诊断，退出原因为 insufficient_evidence；真正达到规划上限仍报告 planning_limit。不增加预算、轮数，也不把缺失证据强制改为覆盖。
2. 共享补查 Prompt 明确遵守指定资料范围。当前只有范围外资料时先定位指定原始文档；已获取、核验指定材料但没有所需输入，且没有可继续读取的线索时，允许空计划停止。不得用财务模板或通用指标定义冒充指定文档答案。
3. LangSmith 样本按 case id 稳定排序，再应用样本数限制；新增 `--case-id`，在实验 metadata 中记录，避免随机抽取最新负例作为普通冒烟。

第一版过早停止候选使负例约 36 秒结束，但参考答案评分降至 0.2 / 0.1。这一判定条件没有保留；最终收紧为先取得并核验指定资料。没有把省调用本身当作质量通过。

## 真实复测

同题结果如下。模型调用与 Token 使用目标 Runtime 计数，裁判调用独立；耗时为目标 Trace 的 end_time - start_time。

| 原负例 | 原运行 | 最终候选复测 | 模型调用 | Token | 答案裁判 |
| --- | --- | --- | --- | --- | --- |
| Plan-and-Execute | partial / planning_limit，123.41 秒 | [partial / insufficient_evidence，82.16 秒](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/f912b629-1a1c-422f-87de-27c83c0d3ebb) | 17 → 10 | 76,897 → 35,684 | 0.9 → 0.9 |
| Multi-Agent | partial / planning_limit，110.63 秒 | [completed，51.40 秒](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/88295549-cae0-4c30-89a5-70de48917cfd) | 13 → 5 | 66,629 → 26,303 | 1.0 → 1.0 |

另用 `single_hop-dev-01`（检查点边界与 thread_id）验证可回答题：

| 策略 | 结果 | 模型调用 / Token | 答案裁判 |
| --- | --- | --- | --- |
| [Plan-and-Execute](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/fec12c92-6355-4436-9f37-766f428834f4) | completed | 6 / 25,610 | 1.0 |
| [Multi-Agent](https://smith.langchain.com/o/d90581d5-a6ea-478d-9c45-9407e1a70582/projects/p/d1b07c9c-b474-4a2c-9fa2-e343f8f82e00) | completed | 6 / 21,576 | 1.0 |

上述均为单次采样。初始规划、检索与来源会变，尤其 Multi-Agent 本轮的初始需求将“文档是否提供指标/输入”显式化，直接完成了有界说明；不能把全部差异归因于补查 Prompt，不能据此宣称普遍提速或整体质量提升。

这些运行依旧没有真正装载冻结文档。云端 completed / 评分 1.0 是当前 Runtime 与裁判的观察结果，不是已经验证对应历史快照的严格来源合规证明；概念文档的摘录也不能证明整个语料不存在某事实。若要形成严格冻结基准，需要向目标提供完整的指定快照，并约束实际取证范围；本次没有重建已退役的自建评测环境。

## 确定性验证与复现

新增回归分别覆盖空计划与真实耗尽上限，并覆盖显式选题、先排序后限量；整个后端确定性测试 **1448 passed，1 deselected**。保留 SDK 的弃用/Beta 提示与已有 SQLite 测试清理警告。Runtime 原有完成条件、覆盖核验和预算未放宽。

```powershell
cd backend
uv run python -m deeptrace.evaluation run --mode plan_execute --case-id insufficient_evidence-test-03 --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode multi_agent --case-id insufficient_evidence-test-03 --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode plan_execute --case-id single_hop-dev-01 --max-examples 1 --judge
uv run python -m deeptrace.evaluation run --mode multi_agent --case-id single_hop-dev-01 --max-examples 1 --judge
uv run pytest -m "not real"
```
