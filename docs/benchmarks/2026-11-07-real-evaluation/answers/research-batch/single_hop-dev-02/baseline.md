# single_hop-dev-02 / baseline

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered flag: True; response reason: None; model calls: 2; seconds: 11.829.

**结论：** 按冻结文档，用 `interrupt()` 暂停工作流至少需要两个前提：**在节点内调用 `interrupt()`**，以及**启用持久化（checkpointer）并传入 `thread_id`**。前者触发暂停，后者保证状态被保存并能恢复 [1][2]。

**1. 在节点内调用 `interrupt()`**

`interrupt()` 在节点内调用时，LangGraph 通过抛出异常让运行时暂停，保存当前状态并等待外部输入 [1]。Python 从 `langgraph.types` 导入，JS 从 `@langchain/langgraph` 导入 [1]。

```python
from langgraph.types import interrupt

def approval_node(state):
    approved = interrupt("Do you approve this action?")
    return {"approved": approved}
```

**2. 持久化层与 `thread_id`**

触发中断时，LangGraph 用持久化层保存图状态，并无限期等待恢复 [1]。checkpointer 是 human-in-the-loop 工作流的前提，因为人需要查看状态、图也需要在更新后恢复 [2]。checkpointer 以 `thread_id` 为主键；没有它，checkpointer 无法保存状态，也无法在中断后恢复执行 [2]。

```python
checkpointer = MemorySaver()
graph = workflow.compile({ checkpointer })
config = { configurable: { thread_id: "1" } }
```

**恢复方式：** 用 `Command(resume=...)` 作为 `invoke()`/`stream()`/`stream_events()` 的输入；文档明确这是唯一用于该场景的 `Command` 模式，`update`、`goto`、`graph` 用于节点返回，不应作为继续对话的输入 [1]。

**可选条件：** 若使用中断响应 schema 校验恢复值，Python 需 `langgraph>=1.2.12`，JS 需 `@langchain/langgraph` 1.4.16 或更高 [1]。这不是暂停本身的前提，而是 schema 功能的前提。

**边界：** 文档未说明所有 checkpointer 后端都满足同一持久化保证；`"exit"` 模式只在执行退出（含中断）时持久化，进程崩溃中途无法恢复 [2]。因此“能暂停”与“崩溃后可恢复”不是同一条件。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
