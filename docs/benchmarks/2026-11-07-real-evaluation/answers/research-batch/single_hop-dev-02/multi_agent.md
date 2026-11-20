# single_hop-dev-02 / multi_agent

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered flag: True; response reason: None; model calls: 5; seconds: 32.158.

**结论：** 按冻结文档，用 `interrupt()` 暂停工作流需要三项：checkpointer、config 中的 thread ID、在目标位置调用 `interrupt()` 且 payload 可 JSON 序列化 [1]。编译图时需把 checkpointer 传给 `compile`，文档示例为 `workflow.compile({ checkpointer })` [2]。

**必需前置条件**

1. **checkpointer（持久化层）**：文档明确列出“A **checkpointer** to persist the graph state（生产环境用 durable checkpointer）” [1]。原因是 interrupt 触发时 LangGraph 通过持久化层保存图状态并等待恢复 [1]；checkpointer 也是 human-in-the-loop 工作流的前提，文档称“Compile a graph with a checkpointer to enable human-in-the-loop workflows” [2]。

2. **thread ID**：需在 config 的 `configurable` 中提供 `thread_id` [1]。文档称调用带 checkpointer 的图时**必须**指定 `thread_id` [2]；checkpointer 以 `thread_id` 为主键存取检查点，缺少它就无法保存状态或在 interrupt 后恢复执行 [2]。文档示例为 `{"configurable": {"thread_id": "1"}}` [2]。

3. **调用位置与 payload**：应在希望暂停的位置调用 `interrupt()`，且 payload 必须可 JSON 序列化 [1]。

**其他条件（按适用范围区分）**

- **版本要求**：仅“interrupt response schema”需要 `@langchain/langgraph` 1.4.16+ [1]；Python 侧同类说明为 `langgraph>=1.2.12` [1]。这不是所有 `interrupt()` 调用的通用门槛，文档未把基础暂停功能绑定到该版本。
- **恢复方式**：恢复时以 `Command(resume=...)` 作为 `invoke()`/`stream()` 的输入，文档称这是唯一用于该场景的 Command 模式 [1]。

**缺口说明**：本次可见材料未给出“不满足上述条件时”的逐项失败表现，也未列出其他环境或版本门槛；无法据此确认全部文档是否还有额外要求。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
