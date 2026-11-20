# 论文深度研究：真实链路诊断与修复

测试日期：2026-11-17。结论：已修复全文获取、PDF读取、需求驱动阅读、来源状态继承和收尾预算等实际链路问题；已有报告输出不等于事实验收通过。本记录保留失败过程，不把 partial 改成 completed。

后续架构优化及真实结果见[研究记录交接、事实表格与执行恢复](qualified-records.md)，包含结构化实验字段、程序生成比较表、PDF失败隔离与收尾恢复的实施及未通过项。

## 问题与协议

固定问题：2024—2025年 test-time compute scaling 如何改善大模型数学推理；比较至少三项原始研究，说明采样/搜索、验证器及预算控制，列出模型、评测集、计算口径及结果，分析跨论文不可直接比较的原因并给出固定预算的工程建议。

生产装配、MULTI_AGENT、REPORT，真实模型/搜索/网页抓取；隔离 SQLite 与记忆。运行上限20次模型调用、100000输入Token、600秒研究时间，另有120秒收尾时间。原始模型输入输出、工具结果、事件、最终状态与来源正文保存在各运行目录，`protocol.json` 记录当时模型和源代码哈希。独立人工原论文复核没有作为预设答案输入研究Agent。

前四次完整运行采用 kimi-k3。用户恢复服务时改用 qwen3.8-27b，后续不再构成同模型严格对照。网络搜索结果、模型输出与网页版本也可能变化，以下为逐次观察，不是统计成功率或成本收益估计。

## 完整运行

| 运行目录（backend/runs/ 下） | 模型 | 输入Token | 模型尝试 | 秒 | 正文字符/引用 | 实际观察 |
|---|---|---:|---:|---:|---|---|
| deep-research-20261117-baseline-4998c0 | Kimi | 88731 | 16 | 516.14 | 4332/5 | 摘要不追全文、PDF失败；模型与成绩混淆 |
| deep-research-20261117-optimized-d9ba1e | Kimi | 64307 | 13 | 302.91 | 31/0 | 格式失败后丢失来源准入，空兜底；失败样本 |
| deep-research-20261117-optimized-v2-7f1104 | Kimi | 89013 | 15 | 609.27 | 10015/4 | 引用摘录退化，不能算正式报告成功 |
| deep-research-20261117-optimized-v3-b69127 | Kimi | 83765 | 10 | 456.98 | 9500/4 | 已有实质草稿；最终核查预算不足，明确警告 |
| deep-research-20261117-current-service-final-f184c7 | Qwen | 67390 | 10 | 237.77 | 4861/4 | 尝试合并写作与自检；仍混淆R1与Zero，方案已撤销 |
| deep-research-20261117-final-independent-review-6b3601 | Qwen | 至少80045 | 14 | 293.91 | 2005/5 | 独立核查完成，仍生成无依据的2k/10k预算分档，质量不通过 |

以上均为 partial / insufficient_evidence。耗时包括工具与收尾，字符数包括程序加入的警告，不代表质量评分。最后完整运行有一次模型连接失败且usage未知：80045仅为其余13次已测输入之和，不是完整运行总成本；另有5次网页browser_failed。该运行保留了全部错误轨迹。

最后完整运行又暴露核查窗口被开头的旧引用占满的问题，随后增加“核查旧引用最多500字符、余量独立检索”修复与回归；这项末端修复仅作冻结证据的真实重放，不宣称再次完成全链路对照。

## 从失败定位到架构修复

| 真实问题 | 所属边界 | 本次改动 | 验证与边界 |
|---|---|---|---|
| arXiv摘要页已有全文链接却停止 | 文献身份与内容表示 | 仅沿实际观察的同论文/版本HTML或PDF链接追全文，替换已解析的摘要候选 | 保留授权、URL去重与页数限制 |
| PDF被按HTML交给浏览器，最终browser_failed | 格式适配 | 有界pypdf文本提取，持久化实际media_type，单独错误分类 | 8MB文件、100页、1M正文字符等限制；不支持OCR；线程超时不是强制CPU进程隔离 |
| 只读开头和主题关键词，漏实验条件 | 需求与阅读衔接 | 使用需求级read_queries，同一需求允许多个互补查询；父层接收实际读过的片段 | 坐标/版本/哈希校验保留，片段交接受全局Token上限限制 |
| 三页抓取额度全被摘要占用 | 目标数量与资源规划 | 科研三篇目标提供六页获取空间 | 不提高运行级预算或任务模型调用上限 |
| 评估JSON失败后有效来源也消失 | 来源准入与结论验收 | 独立保留仍ACTIVE且版本/哈希匹配的来源准入 | 不继承旧coverage，不复活变化来源或已拒绝结论 |
| 时间标记在提取时丢失，年代校验误拒绝 | 提取保真与验证 | 保留HTML watermark和PDF旋转文字中的实际日期 | 不根据URL猜测论文日期 |
| 写完后核查上下文超限，实质草稿被擦除 | 写作/核查/运行预算 | 为两次输入及草稿复制留空间，预算紧张报告采用聚焦原文独立核查 | 仍由Gateway按实测用量准入；不可用时保留明确警告的草稿，格式坏稿不直接发布 |

关键代码：`tools/scraper/{fetcher,pdf,research_links,metadata}.py`、`harness/{batch_collection,source_selection}.py`、`strategies/{evaluation_materials,publication_dates}.py`、`research/{adapters,quality}.py`、`responses/{graph,fact_review}.py`，均位于 `backend/src/deeptrace/`。

## 冻结证据的真实回答重放

来源固定为 v3 运行的原文、研究结果、来源ID/版本/哈希。仅重放生产回答图，无搜索；输入预算28043、调用额度11，等于该次运行进入写作前实际剩余额度。来源清单哈希记录于协议。

| 目录（backend/runs/ 下） | 结果 |
|---|---|
| scholarly-response-replay-20261117-b2ad85 | Kimi额度耗尽，403；无成功回答，失败用量不作零Token统计 |
| scholarly-response-replay-20261117-fad896 | Qwen连接中断，两次尝试后失败，补充有界传输退化处理 |
| scholarly-response-replay-20261117-02440a | 合并写作与自检：6019字、4引用，1次调用、10342输入Token、85.78秒；错误地把Snell模型写成Llama，质量不通过，已撤销合并方案 |
| scholarly-response-replay-20261117-79100e | 独立写作与聚焦核查：2943字、4引用，2次调用、18659输入Token、74.67秒；核查完成、修正部分引用与过强结论，仍为partial，完整质量未通过 |
| scholarly-response-replay-20261117-597008 | 限制旧引用占用后：3327字、4引用，2次调用、19527输入Token、124.88秒；PaLM-2-S*与14倍比较条件更明确，仍遗漏重要协议字段，完整质量未通过 |

最后一次事件 `response.fact_review.completed` 的模式为 `draft_then_focused_review`，返回4项修改原因和3项未决点。正文能区分R1的79.8/97.3，但仍遗漏最大生成长度配置；把部分条件化结果写得过强，模型与评测集描述也不够具体。不得将“核查调用成功”解释为逐句事实正确。

原始重放报告：[answer.md](../../../backend/runs/scholarly-response-replay-20261117-79100e/answer.md)；原始事件：[events.json](../../../backend/runs/scholarly-response-replay-20261117-79100e/events.json)。

最新重放报告：[answer.md](../../../backend/runs/scholarly-response-replay-20261117-597008/answer.md)。其核查自报4项修正、无未答问题，但人工复核仍发现：将Pass@1/Cons@64这样的指标混在预算栏；R1最大生成长度与实际平均消耗未分清；SC的总计算优势被推导成移动端/实时延迟建议，而没有对应并行度或延迟证据。Snell和Singhi的测试子集、验证次数与开销条件仍未完整保留。故不接受模型自报的“无未答问题”作为完成判定。

独立核对Singhi v2原文，MATH Hard约30%的相对改善确有依据，但对应Llama-3.1-8B-Instruct GenRM-FT、32次验证等具体设置；正文还应保留这些条件，及计算匹配时的显著额外开销。新增核查空间只解决旧摘要引用垄断窗口，不保证关键词检索取齐每个必要字段。

## 独立事实核对与验收限制

- [Snell原始论文](https://arxiv.org/html/2408.03314v1)：使用PaLM 2-S*（Codey）；MATH采用12k训练/500测试设置。关于4倍效率及14倍大模型的结论带有具体实验条件，不能直接推广。
- [DeepSeek-R1原始技术报告](https://arxiv.org/html/2501.12948v1)：R1的AIME2024为79.8、MATH500为97.3；不能套用R1-Zero的71.0/95.9。评估协议包含最大生成32768 Token；最大长度与平均实际开销是不同字段。
- [s1版本化论文](https://arxiv.org/html/2501.19393v1)：budget forcing、基座和评估数字必须按版本对应。Agent没有稳定选择该论文，本次不要求把独立复核选择强加给其研究方案。
- [Singhi版本化论文](https://arxiv.org/html/2504.01005v2)：关于生成与验证开销的比较只适用于对应实验设置，不能泛化为所有任务的工程最优方案。

仍需处理：规划自行扩大硬性需求、未读/未找到/未披露共用missing状态、大JSON评估失效范围过大，以及缺少模型—数据集—预算—结果的结构化实验记录。字面引用支持校验不能替代语义蕴含验证；当前系统不能保证每个深度研究任务都正确完成。

## 回归与复现

最终生产代码非联网回归：**1705 passed、1 deselected、33 warnings**（120.30秒）；最后新增窗口回归及事实核查子集15 passed。警告主要来自现有LangSmith SDK。本次涉及的受跟踪代码文件 `git diff --check` 通过；工作区整体检查另发现已有 `tests/observability/test_progress_details.py` 末尾空行，未修改无关文件。

从 backend 目录执行：

```powershell
.venv/Scripts/python.exe -X utf8 scripts/validate_deep_research.py --label scholarly-retest
.venv/Scripts/python.exe -X utf8 scripts/analyze_deep_research.py runs/<运行目录>
.venv/Scripts/python.exe -X utf8 scripts/replay_scholarly_response.py runs/deep-research-20261117-optimized-v3-b69127
.venv/Scripts/python.exe -m pytest -m "not real" -q
```

真实运行会使用本地配置服务并消耗额度；协议与原始轨迹用于审计，不能承诺远端输出逐字复现。原始run目录在工作区保留，不向文档复制凭据或数据库。
