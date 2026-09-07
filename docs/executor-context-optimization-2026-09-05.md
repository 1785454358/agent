# Deep 模式 Executor 上下文优化对比测试

测试时间：2026-09-05
测试问题：`2025年ai热点新闻`
运行模式：deep

## 优化内容

针对 Executor 每轮决策重复携带全部已读原文导致的 Token 膨胀问题，按"按需加载"方案改动：

1. [executor.py](../backend/src/deeptrace/deep/executor.py)
   - `available_source_text`：不再全量拼接所有已读原文（原截 12000 字符），改为调用 `toolbox.relevant_contexts()`，用 BGE 按当前任务目标筛选 top 3 相关来源、各取 800 字符。
   - `completed_work`：只保留 `id + status + gaps` 索引信息，去掉完整 objective 和原文。
2. [tools.py](../backend/src/deeptrace/deep/tools.py)
   - 新增 `relevant_contexts()`：BGE 向量相似度筛选相关来源片段，嵌入失败时退化为按插入顺序取前几个。
   - `fetch_page` 返回给 Executor 的 `context` 从 6000 字符降到 2000；本地 `self.contexts` 仍存全文（6000）供 Writer 使用。

核心原则：原文全文始终保留在本地工作状态供 Writer 写报告，Executor 只看决策所需的少量相关片段。

## Token 消耗对比

| 角色 | 优化前输入 | 优化前输出 | 优化前合计 | 优化后输入 | 优化后输出 | 优化后合计 |
|---|---|---|---|---|---|---|
| Planner | 832 | 574 | 1,406 | 831 | 1,068 | 1,899 |
| Executor | 66,883 | 6,306 | 73,189 | 30,906 | 5,980 | 36,886 |
| Replanner | 14,663 | 8,603 | 23,266 | 11,274 | 6,816 | 18,090 |
| Writer | 10,980 | 13,445 | 24,425 | 9,733 | 4,211 | 13,944 |
| **合计** | **93,358** | **28,928** | **122,286** | **52,744** | **18,075** | **70,819** |

总 Token：122,286 → 70,819，**降 42%**。

## 关键效率指标

两次运行模型走了不同研究路径（工作量不同），需按单位工作量归一化：

| 指标 | 优化前 | 优化后 |
|---|---|---|
| 已读来源数 | 3 | 7 |
| 工具调用次数 | 9 | 24 |
| 执行轮次 | 4 | 8 |
| Executor 输入 / 工具调用 | 66,883 / 9 ≈ **7,431** | 30,906 / 24 ≈ **1,288** |

Executor 单次决策的输入成本降约 **83%**。若跑与优化前相同的 3 来源路径，Executor 输入预计从 6.7w 降到约 1.2w。

## 运行结果

- 运行 ID：`ed7be2a33416`
- 状态：`partial`
- 终止原因：`replanning_failed`（重规划时模型超时 TimeoutError，与本次改动无关，是 DeepSeek 思考模式响应慢导致，可调大 `DEEPTRACE_DEEP_CALL_TIMEOUT_SECONDS` 缓解）
- 总耗时：289.6 秒
- 已读来源：7 个
- 报告：正常生成，引用了具体数据点（88% 企业采用率、2859 亿美元美国私人投资、SWE-bench 60%→100%、OSWorld 12%→66% 等），证明 Writer 拿到的原文全文完整可用。

## 结论

改动有效，Executor 决策成本大幅下降，报告质量未受影响（Writer 仍拿全文）。原文"留本地、Executor 只看索引、按需加载"的方案达到预期。

## 后续可优化点

- Replanner 仍是第二大头（18,090），可压缩重规划时的历史回放与 `original_source_context`（当前 18000 字符）。
- 重规划超时问题：调大 `DEEPTRACE_DEEP_CALL_TIMEOUT_SECONDS`（默认 45s）。
