# 三家成熟产品与本项目的同题实测

测试日期：2026-10-24，Asia/Shanghai。**本题中，ChatGPT 的匿名回答最完整、最有助于落地；本项目在关键问题覆盖上明显落后。差距主要出现在找齐关键材料和解释具体边界，并非只有排版。** 这是单题、单次观察，不是产品总体排名。

这次实际打开产品、发送问题并保存首个回答，没有用模型 API 模拟竞品。按用户选择，完成三家当前可用的匿名模式对比；Kimi 深度研究提交后被登录页阻挡，未参与输出排名。没有购买订阅或把匿名回答标成深度研究。

## 同一问题与实际模式

所有请求均使用[同一份提示原文](prompt.txt)，新会话、无附加材料、每个模式一次。具体方法与事先确定的六项核对标准见[方法记录](methodology.md)。

> 对比 LangGraph 的 checkpoint 与 Store 的用途、线程边界与恢复能力。依据当前官方文档，用中文回答：先给结论，再用表格比较；分别说明进程重启、interrupt 恢复、跨线程共享时的行为与前提，并给出适用场景和带链接的来源。明确区分事实、推断和无法确认的事项。

| 产品 | 实际可用模式 | 结果记录 |
|---|---|---|
| 本项目 DeepResearch | Workflow，当前配置的 DeepSeek，默认预算，新线程 | 有正文，但 `partial_reason=insufficient_evidence`；不是完整回答 |
| ChatGPT | 匿名 Chat，Default；页面未披露底层模型 | 回答完成；非 Deep research |
| Perplexity | 匿名 Search，默认模型；页面未披露底层模型 | 回答完成，来源面板显示 10 个来源；非收费研究模式 |
| Gemini | 匿名 3.5 Flash-Lite；高级工具不可用 | 回答完成；非 Deep Research |
| Kimi | 深度研究入口 | 发送后要求登录；没有获得报告，排除比较 |

这些结果不能代表三家的付费、高级推理或深度研究上限。本轮不改变项目配置去匹配某一家，也不进行同题调参后替换原结果。

## 逐项比较

| 观察项 | 本项目 | ChatGPT | Perplexity | Gemini |
|---|---|---|---|---|
| 职责区别、结论在前、对比表 | 做到了；一个主表 | 做到了；另有场景表、选型表、事实分类表 | 做到了；结构紧凑 | 做到了；分场景条理清楚 |
| 进程重启的前提 | 写明材料不足，没回答内存实现重启丢失这一关键点 | 区分内存与持久化后端，也说明应用仍需发起恢复 | 明确内存 checkpoint 重启丢失；Store 后端说明偏保守 | 区分内存和持久后端，但后续恢复描述偏笼统 |
| interrupt 怎么恢复 | 同 thread、checkpointer 等基本条件；没有具体恢复调用 | 提到 `Command({ resume: ... })` 与同线程配置 | 提到同 `thread_id`、可用检查点；没有具体恢复调用 | 泛称再次调用 `invoke`；没有说明 `Command(resume=...)` |
| 节点重执行、副作用风险 | 没有解释 | 提到节点可能从开头重执行、外部副作用不保证恰好一次，并给幂等性建议；“可能”仍弱于文档的确定表述 | 没有解释；转而讲了故障恢复的 pending writes | 没有解释；“从挂起点继续后续节点”易被理解为从调用行继续 |
| 跨线程的边界 | 解释 namespace，但又留下“能否跨 thread 读状态”的缺口 | 用 A/B 会话举例，说明逻辑索引、共享数据与权限不能混为一谈 | 有 namespace 建议；将一些文档已有的组织规则列为未确认 | 有用户偏好跨会话例子；“线程 A 无法直接读取 B”措辞过强 |
| 帮助用户做决定 | 有简短选型清单，缺具体操作例子 | 有业务需求→方案→原因的表、审批与偏好示例、原生架构示意 | 简洁场景清单，易扫读，操作细节较少 | 场景覆盖较完整，但关键恢复细节仍缺 |
| 证据表现与实测问题 | 3 个官方引用来源；核心 Persistence、Interrupts 页面没有进入实际模型材料 | 来源与段落解释较好；一条长期记忆链接实测 404，一条检查点链接为旧跳转页 | 文末明确列出 4 个官方文档/仓库链接；10 个检索来源中也有第三方，不能把 10 当作 10 条正文证据 | 文末列 3 个官方链接，但多处正文引用气泡指向第三方博客，与“依据官方文档”的呈现不一致 |

这里没有按篇幅或来源数量直接打分，也没有用项目自己的模型给自己和竞品评分。以上是对保存回答的逐项观察，关键事实另按官方原文核对。

## 三个可直接复核的差异

**1. 本项目把可查明的关键点留成了缺口。** 项目原答写“本次可见材料未直接说明‘进程重启后数据是否保留’”，也写“材料未提及 Command(resume=...) 的具体用法”。但是当前官方 [Persistence 文档](https://docs.langchain.com/oss/python/langgraph/persistence)明确解释了内存 checkpointer 的重启丢失问题；[Interrupts 文档](https://docs.langchain.com/oss/python/langgraph/interrupts#resuming-interrupts)给出了恢复输入、同线程及节点重执行的规则。因此“诚实表示当前材料不足”没有错，产品仍未完成用户需要的研究。

项目本次最终引用的来源是 CompiledStateGraph API、Subgraphs、Memory overview，且研究过程出现了 LangMem 材料。保存的 researcher、evaluator、responder 消息里没有核心 `/langgraph/persistence` 或 `/langgraph/interrupts` 页面。可以确认关键资料没有到达模型的工作材料；不能仅凭这份记录判定搜索服务从未返回过这些候选页面。

**2. 完整答案也需要核查。** ChatGPT 提供了更完整的恢复和架构解释，但文末的 `.../langgraph/long-term-memory` 在本次 HTTP 检查中返回 404。旧 `langchain-ai.github.io/langgraph/reference/checkpoints/` 返回 200，但内容是跳转页，不能直接当成已拿到文档正文。完整结果见[链接检查记录](source-link-checks.json)。这不推翻其全部回答，但说明不能把更成熟的表达自动等同于来源全部有效。

**3. 文末官方链接不等于正文由官方材料支持。** Gemini 在进程重启后的恢复行为上引用的是 ActiveWizards 博客，其他多处气泡为 Vilix AI；原始[展开引用记录](raw/gemini-source-detail.json)保留了可见链接。该回答没有解释 interrupt 节点重跑规则。[官方 Interrupts 规则](https://docs.langchain.com/oss/python/langgraph/interrupts#rules-of-interrupts)明确区分节点重新执行与从中断调用行继续；[Checkpointers 的 super-step 说明](https://docs.langchain.com/oss/python/langgraph/checkpointers#super-steps)也区分完整快照与节点级 writes，不能简单等同于每个节点后都生成完整 checkpoint。

Perplexity 对 checkpoint 的重启前提答得比项目明确，阅读也更紧凑；但没有解释节点重跑与幂等性，且把需要同线程恢复归成“推断”，而该条件在官方文档中已有直接说明。它本题也不是无遗漏的标准答案。

## 对本项目下一步优化的含义

本次结果支持先处理以下问题，优先级高于继续增加最终审查提示词或单纯扩写答案。这是基于本题的工程判断，不是已经完成的修改：

1. **让关键子问题取得对应原文。** 重启行为应落到持久化/后端文档，interrupt 恢复应落到其规范页；不能用宽泛记忆概念或子图介绍代替。验收应检查取得的材料能否回答每个关键问题，不绑定某个题目的硬编码 URL。
2. **让缺口驱动有效补查和材料保留。** 本次产物有 `synthesis_window_omitted:5`，部分覆盖在证据校验后变成 missing。应分别定位搜索、抓取、窗口淘汰及支撑校验损失，补查真正缺失的要点，再判断是否结束研究。不能直接把所有 missing 改成 covered。
3. **增加操作层解释。** 在有证据的前提下，为概念结论补上触发条件、恢复操作和容易踩坑的例子；把“用于恢复”解释成用户知道下一步怎么做。ChatGPT 本次的场景表与架构示意可作为交付参考。
4. **引用交付同时检查可达性和逐句支持。** 保留现有审查，但也需要识别旧跳转页、404 和正文/文末来源不一致；引用数量不能作为主要质量目标。

项目本次共 8 次模型调用、40 次工具调用（6 search、10 fetch、24 read），累计输入 43,321 tokens、输出 8,144 tokens，生产调用与导出阶段合计记录约 51.1 秒。其中 2 次 fetch 返回 `response_too_large`，未在此直接认定它们就是缺口根因。详细数据见[项目原始运行结果](project-run.json)。竞品没有同等可靠的起止计时和用量数据，不制作速度或成本排名。

`run.status=completed` 只是 Workflow 结束；研究和回答都记录了 `insufficient_evidence`，不能将其描述成“完整研究成功”。本轮的失败结果保留，没有重跑挑选更好答案。

## 原始输出、截图和复核入口

| 产品 | 完整正文 | 原始页面记录 | 截图 |
|---|---|---|---|
| 本项目 | [原始 Markdown](outputs/project.md) | [运行 JSON](project-run.json) | 本轮通过生产 service 执行，未截图前端 |
| ChatGPT | [可见正文原文](outputs/chatgpt.txt) | [原始捕获](raw/chatgpt.json) | [页面截图](raw/chatgpt.jpg)、[架构示意视窗](raw/chatgpt-diagram.jpg) |
| Perplexity | [可见正文原文](outputs/perplexity.txt) | [原始捕获](raw/perplexity.json)、[10 个来源展开记录](raw/perplexity-sources.json) | [页面截图](raw/perplexity.jpg) |
| Gemini | [可见正文原文](outputs/gemini.txt) | [原始捕获](raw/gemini.json)、[第三方引用展开记录](raw/gemini-source-detail.json) | [页面截图](raw/gemini.jpg) |
| Kimi（未比较） | 无报告 | [登录阻挡记录](raw/kimi-login.txt) | [登录页截图](raw/kimi-login.jpg) |

竞品正文直接提取自渲染后的可见文本，保留原文、换行和来源气泡文字，未由我改写；三个正文均验证为首次原始捕获文本的完整连续子串。原生图表与表格布局以截图为准。浏览器的 fullPage 截图不保证覆盖内部滚动容器全部内容，**完整文本记录优先于截图**。HTML 导出也可能漏掉原生组件中的文字，故不将其作为完整正文的唯一存档。

会话地址保存在各自原始 JSON 中，可能需要当前浏览器会话才能访问；没有点击公开分享。更可靠的复核入口是本地原文、截图、[记录清单与哈希](manifest.json)。原始模型消息和抓取运行日志保存在本地 `.local-notes/product-comparison-2026-10-24/`，没有修改生产提示词来适配本题。

项目运行完成后，可选的来源元数据导出脚本因字段名使用错误发生异常；完整 outcome 在异常前已保存，正文从该 outcome 原样恢复，未再次调用模型。此导出问题与产品的 `insufficient_evidence` 是不同问题。原错误、恢复说明见[capture-notes.json](capture-notes.json)。
