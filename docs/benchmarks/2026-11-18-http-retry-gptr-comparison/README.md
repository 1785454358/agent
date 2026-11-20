# 同题对比：GPT-Researcher 与 agent_new 三种模式

2026-11-18，使用本地 `D:/Dev/Projects/github/GPT‑Researcher` 检出版本运行与上一轮完全相同的订单客户端 HTTP 重试题。GPT-Researcher 使用标准 `research_report`，不是 `deep` 或多智能体扩展。

## 对照条件与口径

- 四组模型均为 `deepseek-v4.1-flash`，thinking 关闭；同一个模型接口及 Tavily 检索服务。**参数记录修正：** agent_new 的实际调用温度为 0；GPT-Researcher 虽将全局配置设为 0，原生角色选择、查询生成、报告写作分别使用源码中的 0.15、默认 0.4、0.35。不能称完全同参数实验；实际 token 统计与计时不变。
- GPT-Researcher 的 FAST、SMART、STRATEGIC 三个角色均指定同一模型，输出中文；不提供额外来源链接或预先整理的资料。
- 保留 GPT-Researcher 的本地 MiniLM 嵌入、bs 抓取、3 次原生研究迭代配置及各角色输出上限。它没有套用 agent_new 的 20 调用/100000 输入 token 预算限制。本次实际仅调用 3 次，输入也低于该上限。
- GPT-Researcher 的 token 逐次取自本地 `GenericLLMProvider.last_usage_metadata`，包括流式报告调用；3/3 调用均取得真实 usage，无字符估算或缺失项。
- 只增加独立运行与计量脚本，未修改任一项目的实现和 `.env`。本地 GPT-Researcher 修订为 `6f998577d547b1e54ec662dac63583aa11e3b84b`，沿用现有检出配置。

## 耗时与用量

| 项目/模式 | 运行结果 | 阶段耗时（秒） | 模型调用 | 输入 token | 输出 token | 总 token |
|---|---|---:|---:|---:|---:|---:|
| agent_new Workflow | partial | 84.75 | 10 | 46851 | 9368 | 56219 |
| agent_new Plan-and-Execute | partial | 85.16 | 11 | 50064 | 9760 | 59824 |
| agent_new Multi-Agent | partial | 118.86 | 12 | 60611 | 14916 | 75527 |
| GPT-Researcher research_report | 已生成报告，人工检查未通过 | 68.39 | 3 | 17433 | 7030 | 24463 |

**计时差异：** agent_new 是 API 已启动后的新请求到结束；GPT-Researcher 的 68.39 秒包含实例初始化 10.69 秒、研究 32.63 秒、写作 25.08 秒。从 Python 进程启动计时为 **113.41 秒**，其中首次模块导入约 45.02 秒。因此不能把 68.39 秒解释为完整冷启动比三组 API 都更快。

GPT-Researcher 的输入 token 约为 Plan-and-Execute 的 34.8%，总 token 约为 40.9%。这里只比较真实 token 数，不使用其内置美元成本估算推断实际账单。

## 获取资料与使用资料的区别

GPT-Researcher 访问 17 个 URL，保存 13 份成功抓取的来源，其中 RFC 9110 正文约 **447606 字符**。抽查可找到 §9.2.2 的非幂等重试条件及 Retry-After 语法。因此它在这次运行中成功跨过了 agent_new 的大文档抓取限制。

但是，保存的最终研究上下文没有带入官方 RFC 9110 URL 对应的来源段，报告也没有直接引用 RFC 9110 原文链接。最终报告引用 7 个不同 URL，只有一个是规范正文（HTTPWG 托管的 RFC 6585）；其余来自博客、LinkedIn、Microsoft Learn 等。它没有满足题目的“仅依据 RFC 9110 与 RFC 6585”要求。

这说明：抓到原文不等于相关条款已进入写作上下文，更不等于报告中的规范性结论已正确引用原文。上一轮 agent_new 则明确报告了证据不足；两个项目的“生成完成”和“覆盖验收通过”状态不能直接等同。

2026-11-18 后续源码核对还发现，`SearchAPIRetriever` 默认对每篇 `raw_content` 先截取前 50000 字符，再进入分块与嵌入筛选；本地环境未覆盖这个默认值。本次 RFC 9110 的非幂等重试条款、Retry-After 语法分别出现在提取正文的约 161053、204673 字符处，均超出该前缀。这一步已在语义筛选前排除了关键正文，因此不能把资料使用缺失全部归因于嵌入排序或写作模型。

## 回答质量复核

沿用上一轮事先定义的 [10 项检查标准](criteria.json)，未因本次答案改变标准。细项见 [review.json](review.json)，没有把伪代码当作已执行的 HTTP 客户端。

1. **POST + 429 的重试条件错误。** 报告宣称 429 意味着请求未处理，进而在伪代码中对所有方法直接返回 `TRUE`。RFC 6585 §4 定义限流状态，没有给出订单未执行的保证；结合 RFC 9110 §9.2.2，不能仅凭 429 就认定非幂等 POST 可安全重发。这是基于规范范围和重试条件的推断。[RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)、[RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)
2. **等待预算与题目直接冲突。** 代码执行 `wait = min(hint, BACKOFF_CAP_MS)`，上限 10 秒。若服务器提示 120 秒、剩余预算约 30 秒，代码把等待裁成 10 秒后继续发送；按题目要求应停止。报告后文反而声称不截断等待，文字与代码矛盾。
3. **总时限处理不完整。** 虽给单次请求设置 `remaining(start)`，循环入口没有明确检查剩余时间是否为正，也没有明确使用单调时钟。
4. **规则被提及但未落实。** 报告提到了自动重试再次失败的规范建议，但代码仍统一允许三次尝试，没有解释适用边界。引用更多、篇幅更长不能替代代码与规则一致。

本题的人工结论：GPT-Researcher 在抓取能力和 token 用量上有明显优势，但答案有实质策略错误；agent_new 的 Plan-and-Execute 伪代码更稳妥，却仍缺 RFC 9110 证据。Workflow 的总时限遗漏、Multi-Agent 的激进 POST 重试建议也未因这次对照而消失。四份答案都不应原样作为订单系统的最终实现。

以上只是同一题各一次运行，不是总体能力排名，也不是严格等预算实验。标准 research_report 的结果不能代表 GPT-Researcher 的全部模式。

## 原始产物

- [GPT-Researcher 回答正文](../../../output/HTTP重试三模式回答/GPT-Researcher回答.md)
- [上一轮三种模式的对比及回答](../2026-11-18-http-retry-three-modes/README.md)
- [同题用量与计时明细](measurements.json)

回答正文与原生 `write_report()` 返回值逐字相同，未补写或修正。本地完整日志、逐次 usage、抓取资料和上下文保存在 `.local-artifacts/http-retry-gpt-researcher-20261118/`，不将人工额外读取的规范冒充项目已使用的证据。
