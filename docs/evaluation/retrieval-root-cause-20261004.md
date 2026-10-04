# 取材链路根因复核（2026-10-04）

本文件记录诊断，不是已批准的实现规格。没有修改生产代码、模型、评分器、运行预算或旧评测结果；没有新一轮付费研究/评分。

## 已复现的结构问题

留样：`tmp/evidence-first-answer-20261004/records.json`，asyncio-live-01。主模式 F1 0.60、partial/iteration_limit，已有审计确认 16 次 read、5 次 find 未命中。旧结果仍保留。

1. `fetch_page` 只交付来源元数据，模型必须额外调用 `read_evidence` 才能看到正文。提示又要求条件遗漏时优先 find，导致模型猜测原文句子、跨语言/措辞未命中、重复定位。
2. `select_best_extraction` 无条件选最长文本。重新抓取实际使用的官方 3.11 页面后，BS4 正文前 20,000 字符与已保存正文完全一致。BS4 全文 20,743 字符，零个双换行段落边界；行内代码被拆成独立行。较长不代表正文结构或相关性更好。
3. 用实际分支查询和当前选择器重放，主模式 TaskGroup/gather 分支选出约 1,704 字符，主要是普通 Task、get_stack/get_name 等说明，未包含 TaskGroup/gather 的目标行为段落。引用坐标全部正确，但坐标正确不代表选材正确。
4. 仅替换为已有 Trafilatura 提取仍未解决相关性。相同页面的默认文本为 18,235 字符；Markdown 为 18,997 字符、45 个双换行。相同查询、2,000 字符选段预算下，Markdown 仍主要选普通 Task/uncancel，未选到目标 gather 段落。因此“改 Markdown”或“默认用 query”单独不能视为已经修复。
5. 现有选择器按问题中所有词的子串命中及稀有度累加排序；通用的“任务、异常、取消”等词容易压过目标 API，当前 ReadAdapter 未向选择器传入分支固定需求的 focus_queries。抓取丢失结构与检索排名共同导致错误取材。
6. 来源版本是另一条独立缺陷：规划输出中的 execution_constraints 经过校验但未被 parse_initial_requirements 返回、seal_initial_plan 持久化。完整原始问题仍固定在提示中，不能说版本要求完全丢失；但目前没有可靠的显式版本来源验收，其他模式仍接受新版来源。

## 复核边界

- 回放只使用实际分支问题和实际网页正文；未将金答案或评分参考链接注入检索。
- ExceptionGroup、gather 等字符串只用于观察选段输出，不作为回放的检索提示。
- 使用现有 select_evidence_passages/select_source_excerpt 和实际 2,000 字符读预算、4,000 字符预览上限。直接调用 _fit_preview 的输出不是完整研究流程或新的质量评分。
- 对已保存来源的现场复核进行了两次官方页面 HTTP 获取；沿用旧联网登记中的 allow_benchmark_dns_proxy=true，不改变应用配置或允许私网 URL。
- 未调用搜索供应商、模型或 Ragas。没有产生新的 F1、Faithfulness 或成本优化成功结论。
- 单页诊断不能证明所有站点行为；20,000 字符前缀截断对其他页面尾部内容的影响仍需单独测试，不将此页问题全部归因于截断。

## 外部实现对照

- [GPT Researcher ResearchConductor](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/skills/researcher.py)：搜索后抓取，再按查询取得相关正文；复用已取得的搜索结果并跟踪已访问 URL。研究循环不依赖模型逐句猜正文的精确字符串。
- [GPT Researcher ContextCompressor](https://github.com/assafelovic/gpt-researcher/blob/main/gpt_researcher/context/compression.py)：较小的文档集直接保留正文与来源，较大文档做分块及相关性筛选。其 embedding 管线不是本项目必须照搬的依赖或服务。
- [Trafilatura 官方输出说明](https://trafilatura.readthedocs.io/en/latest/usage-python.html)：支持结构化输出与 Markdown。现场使用本项目已有 2.2.0 验证 Markdown 可用，不升级依赖；输出格式改善不等于检索质量恢复。

这些实现提供设计参考，不证明本项目会达到相同质量或某个 F1。

## 待用户确认的优化顺序

推荐先局部替换“正文提取 + 问题选段”：以结构可用的正文为优先，保留段落/行内标识符；按分支答案要点检索，完整匹配目标实体，保留邻接条件与例外，按完整段落组适配预览。未命中须明确反馈，不默默把不相关选段当成已覆盖。

随后再将实际原文选段交付合并进抓取响应，减少模型导航轮次；必须沿用原文 hash/version/坐标、授权、checkpoint 和已读校验，不能将仅抓取或搜索摘要伪装成已读证据。

版本约束执行独立实施/验证，评分信号独立审计；不把多个因素同时修改后统一归因。本轮尚未批准上述新行为设计，待确认后另写具体规格。

验证继续使用相同模型、评分口径与轮数上限。首先恢复主模式 F1 至至少 0.80、任务完成且来源/关键行为验收通过，再比较时间、输入/输出/总 token、搜索 API 尝试；这是验收门槛，不是保证。
