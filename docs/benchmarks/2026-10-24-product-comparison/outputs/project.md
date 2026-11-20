## 结论

Checkpoint 是**线程内的图状态快照机制**：编译图时提供 checkpointer 后，每个 superstep 保存一次图状态；不提供则无法保存或恢复状态 [1]。它支撑同一 thread 的续跑、状态查询/更新与 interrupt 暂停恢复 [1][2]。Store 是**跨线程的长期记忆存储**：官方定义为“可选的长期记忆存储，允许跨线程持久化与检索数据” [1]，长期记忆按自定义 namespace 组织、可在任意线程召回 [3]。

取舍：需要“接着上次继续跑/人工审批后恢复”用 checkpoint；需要“不同会话共享用户偏好、提示词、事实”用 Store。二者可同时配置，但职责不同。

## 对比表

| 维度 | Checkpoint（checkpointer） | Store |
|---|---|---|
| 官方定位 | 持久化图状态；每个 superstep 存检查点；未配置则不能保存/恢复 [1] | 可选长期记忆存储，跨线程持久化与检索 [1] |
| 存什么 | 图状态快照、状态历史；getState/getStateHistory/updateState 均依赖它 [1] | JSON 文档，按 namespace（类似文件夹）+ key（类似文件名）组织 [3] |
| 线程边界 | 线程作用域：短期记忆由 checkpointer 持久化，使该 thread 可随时恢复 [3]；子图用 checkpoint namespace 区分多次调用 [2] | 作用域是自定义 namespace，而非单一 thread ID；跨会话、跨线程共享 [3] |
| 恢复能力 | 支持从暂停处恢复；无检查点时子图无法暂停/恢复，也无持久执行 [2] | 提供记忆的保存与召回，不是执行断点恢复机制（据定义推断）[1][3] |
| 检索方式 | 按 thread 配置取状态/历史 [1] | 支持语义搜索与按内容过滤；可跨 namespace 用内容过滤搜索 [3] |

## 分场景说明

**进程重启**
- 事实：checkpointer 把状态持久化到数据库，使线程可随时恢复 [3]；未配置 checkpointer 则图无法保存或恢复状态 [1]。
- 无法确认：本次可见材料未直接说明“进程重启后数据是否保留”及具体依赖哪种后端（仅提到数据库持久化与内存版示例）。因此“用持久化后端即可跨重启恢复”属合理推断，需按所选后端核查。
- Store 同理：材料只说跨线程持久化 [1]，未直接给出重启语义。

**interrupt 恢复**
- 事实：checkpointer 支持 interrupt() 暂停并等待用户输入，再从暂停处恢复；无检查点时子图无法暂停/恢复 [2]。有状态子图继承父图 checkpointer，从而支持 interrupt、持久化与状态检查 [2]。
- 前提（据材料）：配置 checkpointer、同一 thread、存在对应检查点。
- 无法确认：材料未提及 Command(resume=...) 的具体用法，也未说明 Store 在 interrupt 恢复中的角色；按定义推断 Store 不承担断点恢复。

**跨线程共享**
- 事实：长期记忆跨对话线程共享，可在任意时间、任意线程召回，作用域为自定义 namespace [3]；Store 支持语义搜索与内容过滤 [3]。
- 前提：写入时用一致的 namespace/key 约定（常含用户或组织 ID）[3]。
- 无法确认：材料未说明 checkpoint 能否跨 thread 读取另一线程状态；按“线程作用域”表述推断不能直接跨线程复用。

## 适用场景

- 用 checkpoint：多轮对话续跑、human-in-the-loop 审批、状态检查与回放、子图持久化 [1][2]。
- 用 Store：跨会话用户画像/偏好、可复用提示词、需语义检索的事实库 [3]。
- 组合：执行状态放 checkpoint，跨线程知识放 Store（推断，依据二者定位互补 [1][3]）。

## 缺口说明

本次可见材料未覆盖：Store 的完整 API 定义细节、checkpoint 与 Store 作用域差异的原文对比、进程重启行为的直接表述、Command(resume=...) 用法。以上缺口仅表示当前材料不足，不代表官方文档无答案。

## 来源

- [1] CompiledStateGraph API：https://langchain-ai.github.io/langgraphjs/reference/classes/langgraph.CompiledStateGraph.html
- [3] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [2] Subgraphs：https://docs.langchain.com/oss/python/langgraph/use-subgraphs
