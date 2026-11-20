## 结论

Checkpoint 是**线程内**的图状态持久化机制：以 `thread_id`（必需）和可选 `checkpoint_id` 为键，保存每一步的精确图状态，用于恢复、时间点重放、human-in-the-loop 与容错 [1][2]。Store 是**跨线程**的长期记忆载体：以自定义 namespace + key 组织 JSON 文档，不绑定单个 thread，可在任意线程召回 [3]。

取舍：需要“接着上次的会话/中断继续跑”用 checkpoint；需要“跨会话记住用户或应用级数据”用 Store。二者互补，不是替代关系。

## 对比表

| 维度 | Checkpoint（checkpointer） | Store（BaseStore） |
|---|---|---|
| 用途 | 保存图状态，支持恢复、HITL、持久执行、交互间记忆 [2] | 保存跨会话的用户/应用级长期记忆 [3] |
| 键/组织 | `thread_id` 必需，`checkpoint_id` 可选；thread 是一系列 checkpoint 的唯一 ID [2] | 自定义 namespace（类似文件夹）+ 独立 key（类似文件名），支持层级与跨 namespace 过滤搜索 [3] |
| 线程边界 | 线程范围，线程间隔离 [3] | 不限于单个 thread ID，跨线程共享 [3] |
| 写入时机 | 每个 superstep 保存；节点失败时保留同 superstep 已完成节点的 pending writes [2] | 由节点代码显式 `put`/`get`/`search` [3] |
| 恢复粒度 | 线程内任意 checkpoint 点 [2] | 无“恢复图”概念，仅数据读写 |

## 分场景行为与前提

**进程重启**
- 事实：生产环境应使用持久化 checkpointer（如数据库后端），以便执行后可恢复 [1]。
- 推断：内存型 checkpointer 重启后状态丢失；持久化后端可恢复，前提是同一 `thread_id` 与同一后端。
- 无法确认：文档未明确说明 Store 在进程重启后的数据保留条件 [1]；需按所选 store 后端核查。

**interrupt 恢复**
- 事实：`interrupt()` 暂停执行并保存当前图状态；前提是配置 checkpointer（生产用持久化）且 config 中有 thread ID；恢复用 `Command(resume=...)`，其值成为 `interrupt()` 返回值 [1]。
- 事实：复用同一 `thread_id` 恢复同一 checkpoint，新值则开新线程空状态 [1]。
- 无法确认：Store 在 interrupt 恢复中的直接角色文档未说明；其作用是保存跨步骤/跨会话数据（如提示词）[3]。

**跨线程共享**
- 事实：短期记忆线程隔离，不同线程间保持分离 [3]。
- 事实：长期记忆作用域为自定义 namespace，可在任意线程召回 [3]。
- 前提：Store 需在节点中注入并显式读写；namespace 常含用户/组织 ID 以便组织 [3]。

## 适用场景

- Checkpoint：多轮对话续接、审批中断恢复、失败重跑不重复已完成节点、多租户隔离会话 [1][2]。
- Store：跨会话用户偏好、应用级配置/提示词、跨线程共享知识 [3]。

## 来源

- [1] Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
- [3] Memory overview：https://docs.langchain.com/oss/python/concepts/memory
- [2] langgraph.checkpoint 参考：https://reference.langchain.com/python/langgraph.checkpoint

## 缺口说明

本次可见材料未覆盖：Store 各后端在进程重启下的保留语义、Store 与 interrupt 的官方组合用法。以上标为“无法确认”，不代表全部文档无答案，建议核查 Persistence 指南与所选 store 后端文档。
