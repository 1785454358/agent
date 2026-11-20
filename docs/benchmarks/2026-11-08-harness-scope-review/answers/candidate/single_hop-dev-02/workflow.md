# single_hop-dev-02 / workflow

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: partial; answered: False; reason: answer_review_incomplete; model calls: 7; tools: 25; seconds: 34.779.

结论：按冻结文档，用 `interrupt()` 暂停工作流需同时满足三项前置条件：编译图时配置 **checkpointer**（生产用持久化 checkpointer）、运行时 config 提供 **thread ID**、在**节点内**调用 `interrupt()` 且 payload 可 JSON 序列化 [1]。版本要求仅针对“中断响应模式（response schemas）”，不是调用 `interrupt()` 本身的前置条件 [1]。

**1. checkpointer（持久化）**

`interrupt()` 触发时，LangGraph 用持久化层保存图状态并等待恢复 [1]。文档明确列出使用 `interrupt()` 需要“一个 checkpointer 来持久化图状态（生产环境使用 durable checkpointer）” [1]。checkpointer 也是 human-in-the-loop 工作流所需，因为人要能查看任意时刻的状态、并在更新后恢复执行 [2]。

取舍：`MemorySaver`/`InMemorySaver` 存在 RAM，进程重启即丢失，文档建议生产改用持久化 checkpointer（如 `PostgresSaver`、`SqliteSaver`）[3]。

**2. config 中的 thread ID**

运行时 config 必须提供 `thread_id`，让运行时知道从哪个状态恢复 [1]。checkpointer 以 `thread_id` 为主键存取 checkpoint；没有它，checkpointer 无法保存状态，也无法在中断后恢复执行 [2]。同一 `thread_id` 复用即回到同一 checkpoint，新值则开启空状态的新线程 [1]。

**3. 调用位置与 payload**

`interrupt()` 应在图节点内调用，payload 必须可 JSON 序列化 [1]。恢复时用 `Command` 重新调用图，其值成为节点内 `interrupt()` 调用的返回值 [1]。

```python
from langgraph.types import interrupt

def approval_node(state):
    approved = interrupt("Do you approve this action?")
    return {"approved": approved}
```

**4. 版本要求（仅限 response schemas）**

若使用中断响应模式，Python 需 `langgraph>=1.2.12`，JS 需 `@langchain/langgraph` 1.4.16 或更高 [1]。这是该可选特性的门槛，文档未把它列为 `interrupt()` 的通用前置条件。

**缺口说明**：本次可见材料未给出 `interrupt()` 本身的最低版本要求，也未说明非持久化 checkpointer 在中断场景下的具体失败边界；这些无法从现有原文确认。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
3. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
