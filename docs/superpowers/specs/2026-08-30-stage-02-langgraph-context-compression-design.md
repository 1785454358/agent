# DeepTrace 阶段 2 设计　LangGraph 编排、上下文压缩与可靠抓取

- 状态　已完成
- 日期　2026-08-31
- 实施位置　`backend/`
- 本地 Embedding 模型　`D:\Dev\Models\bge-m3`

## 1. 目标与边界

阶段 2 保留阶段 1 的单 Agent 形态。用户输入研究问题后，Agent 自主决定搜索、抓取、继续研究或回答。本阶段解决三个已经出现的工程问题，包括整页正文造成上下文膨胀、单一静态抓取路径不可靠，以及手写 Agent 循环不利于后续扩展。

本阶段引入 LangGraph、本地 BGE-M3 语义筛选、LLM 研究笔记压缩、分层抓取和逐轮 Token 统计。不拆分 Planner、Researcher、Writer，不实现 Evidence Store、Verifier、长期 Memory、API 或 Web UI，也不进行大规模评测。

设计参考 GPT Researcher 的两个经验，即网页内容先筛选再总结，以及抓取层支持多个后端。DeepTrace 独立实现自己的 State、双查询融合、运行时向量注册表、工具调用映射、降级策略和 Token 指标，不复制其源码、Prompt 或完整架构。

参考资料如下。

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph Use the graph API](https://docs.langchain.com/oss/python/langgraph/use-graph-api)
- [GPT Researcher context compression](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/context/compression.py)
- [GPT Researcher scraper selection](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/scraper/scraper.py)

## 2. 整体数据流

```text
START
  ↓
agent
  ├─ 无工具调用 → finalize → END
  └─ 有工具调用 → dispatch_tools
       ├─ search_web → tool_results → agent
       └─ fetch_webpage → pending_fetches
                            ↓
                       fetch_documents
                            ↓
                       prepare_chunks
                            ↓
                     compress_documents
                            ↓
                    build_tool_messages
                            ↓
                          agent
```

搜索结果较短，可以作为工具结果回填。网页正文不能直接进入主 Agent 对话，必须经过筛选和压缩。压缩失败时回填筛选后的原文片段，保证页面信息不丢失。

## 3. LangGraph State 与 reducer

State 只保存以下可序列化、适合 checkpoint 的数据。

- `user_query`，用户原始问题，运行期间不变。
- `active_query`，触发当前搜索或抓取的子问题。
- `messages`，给主 Agent 的有界消息窗口，采用覆盖语义。
- `documents`，`doc_id → RawDocument`，使用字典合并 reducer。
- `chunks`，`chunk_id → DocumentChunk`，使用字典合并 reducer。
- `notes`，`note_id → ResearchNote`，使用字典合并 reducer。
- `queries`，历史查询列表，使用保持顺序的去重追加 reducer。
- `pending_fetches`，本轮待处理请求，采用覆盖语义。
- `events`，运行事件，使用追加 reducer。
- `step_count`、`extension_granted`，预算状态，采用覆盖语义。
- `token_metrics`，逐轮 Token 指标，使用追加 reducer。

State 不使用 `set`，也不保存 numpy 向量。已访问 URL 从 `documents` 推导，避免维护两份可能不一致的数据。字典和唯一列表 reducer 是小型纯函数，需要单独测试。

## 4. 核心数据模型

### PendingFetch

包含 `tool_call_id`、原始 URL、`active_query` 和调用顺序 `order`，是并发任务与 ToolMessage 之间的稳定关联键。

### RawDocument

包含 `doc_id`、原始 URL、最终 URL、canonical URL、标题、正文、content hash、抓取时间、`scraper_used`、状态和错误。正文只在文档区保存，不进入主 Agent 消息。

### DocumentChunk

包含 `chunk_id`、`doc_id`、块序号、正文、token 数和字符区间。向量不放在该模型中。

### ResearchNote

包含 `note_id`、`doc_id`、`active_query`、标题、要点、证据摘录、来源 URL、相关性分数、压缩状态和错误说明。

笔记检索的代表文本固定为 `title + key_points + evidence_snippets`，兼顾主题和证据词汇。

### CompressionOutcome

包含 `tool_call_id`、`note`、`error` 和 `order`。并发完成后按 `order` 排序，再使用 `tool_call_id` 构造对应 ToolMessage。

## 5. CompressionRuntime

一次研究运行创建一个进程内 `CompressionRuntime`，负责加载 BGE-M3、批量 embedding、相似度计算，并保存 `chunk_id → vector` 和可选的查询向量缓存。

该对象通过图的运行依赖传入节点，不进入 State。运行结束后释放。Note 初期只有几十条，每轮可以批量重算 note embedding，不急于增加持久缓存。

## 6. 分块、召回与压缩

### 6.1 分块

- 使用 BGE-M3 tokenizer 估算长度。
- 目标块大小 800 token，重叠 100 token。
- 保留块序号和字符区间，支持相邻块扩展和后续 Evidence 定位。
- 多个新文档的块合并为 batch 计算 embedding，默认 batch size 为 8。

### 6.2 双查询融合

每个 chunk 分别与用户原始问题和当前子问题计算余弦相似度。

```python
fused_score = max(
    cosine_similarity(user_query_vector, chunk_vector),
    cosine_similarity(active_query_vector, chunk_vector),
)
```

max 是有意的宽召回策略。块只要与总体任务或当前方向之一相关，就能进入压缩层。初始选择融合分数最高的约 6 个块，再补充相邻块、去重并恢复网页顺序。

### 6.3 整页无关短路

若融合后的 top-1 分数低于 `0.45`，页面标记为“已抓取但不相关”，跳过 LLM 压缩。日志同时记录 top-1 的用户问题分数、当前子问题分数、融合分数和阈值。

`0.45` 是初始值。真实运行后观察融合分数分布，预期可能上调到 `0.45–0.50`，但本阶段不为调参运行大规模评测。

### 6.4 结构化压缩与降级

入选块交给 LLM 生成 ResearchNote，输出先通过 Pydantic 校验。失败时按以下顺序处理。

1. JSON repair 后再次校验。
2. 仍失败时使用相同输入重试一次。
3. 超时或再次失败时生成抽取式笔记，直接保留筛选后的原文、标题和 URL。

无论压缩模型是否成功，主 Agent 都能收到与该工具调用对应的信息。

### 6.5 笔记召回

主 Agent 每轮只接收当前最相关的有限笔记。ResearchNote 代表文本也同时计算用户问题和当前子问题相似度并取 max，避免后期新方向被早期笔记长期压制。

## 7. 抓取降级链

抓取顺序如下。

1. HTTPX 获取 HTML，Trafilatura 提取正文。
2. 若过短，BeautifulSoup 对同一 HTML 提取可见文本。
3. 若仍过短，Playwright 渲染页面，再依次尝试 Trafilatura 和 BeautifulSoup。

正文同时满足至少 500 字符和 200 token 才视为正常成功。进入下一级后，如果新结果没有更好，保留此前质量最高的提取结果。

`scraper_used` 使用枚举记录最终采用的提取方式。Playwright 设置明确超时、DOM 等待、常规 viewport、locale 和 User-Agent，并阻断图片、字体、视频等重资源。本阶段不处理登录态、Cookie 复用、下载、验证码绕过或反爬对抗。

## 8. URL 规范化与页面复用

抓取前保守规范化包括 host 小写、删除 fragment 和默认端口、规范化路径点段和尾部斜杠、删除常见追踪参数、对其余 query 参数稳定排序。此时不盲目合并 HTTP/HTTPS，也不直接合并 `m.` 或 `mobile.` 子域。

抓取后结合最终响应 URL、安全可信的 canonical 标签和 content hash 判定页面身份。只有 canonical 明确一致或正文 hash 一致时，才合并协议与移动子域别名。

同一页面出现在新的 `active_query` 下时，不重新抓取、分块或计算 chunk embedding。系统使用新子问题重新筛选已有块，并按需生成新 ResearchNote。笔记键由 `doc_id + active_query_hash` 构成，避免复用错误角度的摘要。

## 9. 并发与 tool_call_id 映射

一轮可能同时出现多个抓取调用，实现采用以下 fan-out/fan-in 流程。

1. 每个 PendingFetch 保留 `tool_call_id` 和 `order`。
2. 抓取和压缩可以并发，压缩 semaphore 初始并发度为 3。
3. 使用 `asyncio.gather(..., return_exceptions=True)`，单页失败不取消其他页面。
4. 每项任务返回 CompressionOutcome。
5. 汇合后按 `order` 排序，将结果回填到同一 `tool_call_id` 的 ToolMessage。

禁止依赖异步任务完成顺序，否则 Agent 可能把 A 页笔记误认为 B 页结果。

## 10. 轮次预算与重复查询

迁移初期保留阶段 1 的硬上限 8，先验证图稳定。随后在同一阶段启用软上限 8、硬上限 12、最多延长一次。

只有近期产生新笔记、仍有明确研究缺口、没有重复查询且从未批准延长时，才能超过软上限。新 search query 与历史 queries 使用 BGE-M3 计算相似度，最大值超过 `0.85` 时视为重复循环并拒绝延长。

## 11. Token 节省统计

### 11.1 统计目标

本阶段回答“压缩后每轮大约节省多少 Token”。这是单次运行的工程观测，不是质量评测。对照对象是阶段 1 把历史网页正文持续留在消息中的策略。

### 11.2 两条口径

估算口径默认使用 `cl100k_base`。

- `estimated_baseline_context_tokens`，使用同轮系统 Prompt、用户消息、Agent 消息和工具元数据，再加入截至当前轮全部原始网页工具载荷，重建阶段 1 的反事实上下文后估算。
- `estimated_actual_context_tokens`，对当前真正构造给主 Agent 的有界消息和笔记估算。

Provider 口径读取模型响应中的 `prompt_tokens`、`completion_tokens` 和 `total_tokens`。Provider 可能使用不同 tokenizer，所以单独展示，不能混入反事实估算。

### 11.3 每轮公式

```text
gross_saved = baseline_context - actual_context
gross_ratio = gross_saved / max(baseline_context, 1)

compression_tokens = compression_input + compression_output
net_saved = gross_saved - compression_tokens
net_ratio = net_saved / max(baseline_context, 1)
```

每个网页另记 `raw_tool_payload_tokens`、`note_tool_payload_tokens` 和压缩率。压缩 usage 优先读取 Provider；缺失时用同一 estimator 估算并标记来源。

基线必须包含此前各轮累积的原始网页正文。否则只能说明一页缩短多少，不能反映第 N 轮避免了多少上下文膨胀。

BGE-M3 输入量可记为 `local_embedding_tokens`，但明确属于本地计算，不计入 API Token 成本，也不从主 Agent 节省量中扣除。

### 11.4 CLI 输出

每轮输出一行。

```text
[Round 4] baseline≈32,180 | actual≈8,420 | gross saved≈23,760 (73.8%) | compression=2,140 | net saved≈21,620 (67.2%)
```

结束后输出累计主 Agent usage、累计压缩 usage、累计毛节省与净节省。所有估算值带 `≈` 或 `estimated` 标识。

## 12. 配置

```dotenv
DEEPTRACE_EMBEDDING_MODEL_PATH=D:\Dev\Models\bge-m3
DEEPTRACE_MIN_RELEVANCE_SCORE=0.45
DEEPTRACE_EMBEDDING_BATCH_SIZE=8
DEEPTRACE_COMPRESSION_CONCURRENCY=3
DEEPTRACE_MIN_EXTRACTED_CHARS=500
DEEPTRACE_MIN_EXTRACTED_TOKENS=200
DEEPTRACE_SOFT_MAX_STEPS=8
DEEPTRACE_HARD_MAX_STEPS=12
DEEPTRACE_QUERY_LOOP_THRESHOLD=0.85
DEEPTRACE_TOKEN_ENCODING=cl100k_base
```

已有 LLM 与 Tavily 配置继续复用。模型路径、浏览器和阈值需要在启动时清晰校验，失败时给出可操作的错误。

## 13. 计划代码文件

| 文件 | 职责 |
|---|---|
| `models.py` | RawDocument、DocumentChunk、ResearchNote、PendingFetch 等模型 |
| `state.py` | LangGraph State、reducer 和状态辅助函数 |
| `graph.py` | 图构建、条件路由和节点连接 |
| `nodes.py` | Agent、抓取、压缩和 ToolMessage 回填节点 |
| `embedding.py` | BGE-M3、batch embedding、相似度和向量注册表 |
| `compression.py` | chunk 筛选、笔记生成、JSON 修复和抽取式降级 |
| `fetching.py` | 抓取降级链、正文质量判断和 scraper_used |
| `urls.py` | 抓取前规范化和抓取后页面身份 |
| `token_metrics.py` | 反事实基线、实际上下文、压缩成本和 CLI 汇总 |

现有 `config.py`、`tools.py`、`agent.py` 和 `cli.py` 按职责调整。实施计划可微调文件名，但不能改变架构边界。

## 14. 必要测试

- reducer 的字典合并、列表去重和覆盖语义。
- chunk 与 note 层双查询 max 融合，包含后期新方向笔记召回。
- top-1 低于阈值时跳过压缩。
- LLM JSON 异常和超时降级为筛选原文。
- 多页并发失败互不影响，完成乱序时 `tool_call_id` 仍正确。
- 同一 URL 不重复抓取，新 active query 重新筛选已有 chunks。
- URL 追踪参数、尾部斜杠、canonical 和相同 content hash。
- 提取过短时进入下一级并正确记录 `scraper_used`。
- 查询相似度超过 `0.85` 时拒绝延长。
- Token 指标公式、累计基线和压缩成本扣除正确。
- 使用真实 API Key 跑一次完整冒烟问题，观察逐轮与最终 Token 统计。

阶段 2 不建立评测数据集，也不运行 Open Deep Research 或 GPT Researcher 对比。

## 15. 完成标准

用户可以继续通过 CLI 提问真实研究问题。Agent 使用 LangGraph 完成闭环，整页正文被隔离在文档区，主对话只接收相关笔记；静态抓取失败时能安全降级；并发结果不会错配；每轮能看到相对阶段 1 上下文策略的估算毛节省、压缩成本和净节省。
