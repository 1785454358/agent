# HTTP 重试新题：三种策略真实对比

2026-11-18，在同一份现有项目代码上，分别指定 Workflow、Plan-and-Execute、Multi-Agent，回答同一个订单客户端 HTTP 重试设计问题。完整题目见 [question.txt](question.txt)。本轮只测试，未修改项目实现或用户的 `.env`。

## 条件

- 用户更换后的模型：`deepseek-v4.1-flash`，`thinking=disabled`。
- 每次上限：20 次模型调用、100000 输入 token、600 秒研究时间；规划/评估/成文单次超时为 60/120/180 秒。
- 使用实际独立策略执行图，手动指定模式；三次均创建新对话，运行目录、记忆库和缓存隔离，依次执行。
- GLM 配置探测遇到 thinking 参数错误、超时/断连，用户随后更换模型。那些探测记录不计入本表；小请求连通性探测也不计入应用运行用量。

## 测量结果

| 模式 | 引擎状态 | 耗时（秒） | 模型调用 | 输入 token | 总 token | 可引用来源 | 事实审查 |
|---|---|---:|---:|---:|---:|---:|---|
| Workflow | partial / insufficient_evidence | 84.75 | 10 | 46851 | 56219 | 1 | 完成 |
| Plan-and-Execute | partial / max_replans_reached | 85.16 | 11 | 50064 | 59824 | 1 | 完成 |
| Multi-Agent | partial / no_research_progress | 118.86 | 12 | 60611 | 75527 | 1 | 完成 |

三次的 `model.failed` 事件均为 0，用量统计完整；没有触及 20 次调用或 100000 输入 token 上限。事实审查完成是流程事件，不代表答案已正确或需求已完整覆盖。原始数值、运行 ID 和终止原因见 [measurements.json](measurements.json)。

## 共同阻断环节

三组最终可引用来源均只有 `https://www.rfc-editor.org/info/rfc6585`。抓取 RFC 9110 时，实际工具记录显示：

- `https://www.rfc-editor.org/info/rfc9110`：`response_too_large`，浏览器页面超过体积限制，HTTP 阶段另有重定向次数超限。
- Workflow、Plan-and-Execute 尝试 `https://www.rfc-editor.org/rfc/rfc9110.pdf`：`pdf_page_limit`。
- Workflow 获得了 RFCinfo 镜像，Plan-and-Execute 获得了第三方 503 解释页，但最终未作为题目所需规范依据引用。
- Multi-Agent 进行了补查，但仍未获得新的可用规范证据，因此以无研究进展结束。

这些结果把本题共同瓶颈定位到大文档获取与证据准入。不能根据本题的 partial 状态推断三种策略本身都无法完成研究。

## 人工检查

事先定义的检查项见 [criteria.json](criteria.json)，逐项结论见 [review.json](review.json)。这里检查的是返回答案和伪代码，未把伪代码描述为已执行的客户端程序。

- **Workflow**：六种方法/故障组合的风险说明较清楚，但 `send(request)` 没有受剩余时间约束；连接断开分支的退避等待也未检查剩余预算，不能保证端到端 30 秒。仅在循环开头检查时间不够。
- **Plan-and-Execute**：本题的流程约束最完整。伪代码使用单调时钟、单次请求剩余超时、统一等待预算检查、最多三次尝试，POST 需要额外安全条件。但规范证据仍缺失，并把两种 Retry-After 格式的句子标到了仅支持 429 的来源编号，引用支撑不完整。
- **Multi-Agent**：时间预算的伪代码较完整，但提出在收到有效 Retry-After、且业务接受重复创建风险时自动重试 POST。它明确承认重复风险，没有伪造去重承诺；不过这属于较激进的业务策略，并未解释与 RFC 默认非幂等重试建议的关系，不适合作为默认订单重试实现。
- 三者均未充分处理“自动重试本身再次失败”的规范边界；30 秒、三次尝试及退避参数是题目要求或设计建议，不能据此推导规范允许任何场景下连续自动重试。

人工检查的规范参照：非幂等自动重试和再次重试的条件见 [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)，等待值语法见 [§10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)，503 见 [§15.6.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.6.4)，429 见 [RFC 6585 §4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)。这些是本次人工复核额外读取的参照，不能算成研究引擎已经获取的证据。

## 回答正文

- [Workflow 回答](../../../output/HTTP重试三模式回答/workflow回答.md)
- [Plan-and-Execute 回答](../../../output/HTTP重试三模式回答/plan_execute回答.md)
- [Multi-Agent 回答](../../../output/HTTP重试三模式回答/multi_agent回答.md)

导出内容与各次 API 返回的 `answer` 完全相同，未修改、补写或追加评语。本题一次运行仅能说明这道题上的表现，不能据此做模式总体排名。
