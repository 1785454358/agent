# 主要改动记录

## 2026-09-05 Deep 模式 Executor 上下文优化

针对 Deep 模式 Executor 重复携带全部已读原文导致的 Token 膨胀问题。

### 改动 1：Executor 按需加载相关片段

- [executor.py](../backend/src/deeptrace/deep/executor.py)：`available_source_text` 不再全量拼接所有已读原文（原截 12000 字符），改为调用 `toolbox.relevant_contexts()`，用 BGE 按当前任务目标筛选 top 3 相关来源、各取 800 字符；`completed_work` 只保留 `id + status + gaps` 索引信息。
- [tools.py](../backend/src/deeptrace/deep/tools.py)：新增 `relevant_contexts()`，BGE 向量相似度筛选，嵌入失败时退化为按插入顺序取前几个。

原则：原文全文始终保留在本地 `self.contexts` 供 Writer 写报告，Executor 只看决策所需的少量相关片段。

效果：Executor 单次决策输入降约 83%（7431 → 1288）。

### 改动 2：组合研究工具 research_topic

把"搜索 → 去重 → 候选筛选 → 批量抓取"这条确定性流水线打包成组合工具，模型一次决策完成，不再逐页单独决策。

- [models.py](../backend/src/deeptrace/deep/models.py)：新增 `ResearchTopicArgs`（query + max_pages 1-5）与 `research_topic` 工具 schema。
- [tools.py](../backend/src/deeptrace/deep/tools.py)：抽取 `_read` 的抓取+压缩逻辑为 `_ingest_document()` 共用；新增 `_research_topic()`，内部搜索后批量抓取，每次实际抓取通过 `self.quota` 回调计入工具配额（不绕过 `deep_max_tool_calls` 上限）。
- [agent.py](../backend/src/deeptrace/deep/agent.py)：每轮运行前注入 `self.tools.quota = runtime.claim_tool`。

分工：确定性步骤（搜索、去重、批量抓取）放进工具层；有判断价值的步骤（研究什么、资料是否足够、哪里补查）留给 ReAct。

效果（同一问题 `2025年ai热点新闻`）：Executor 输入从 66,883 降到 23,478，占比从 60% 降到 38%；决策轮次减少；读取来源从 3 个增至 14 个，研究覆盖面显著扩大，报告质量保持。
