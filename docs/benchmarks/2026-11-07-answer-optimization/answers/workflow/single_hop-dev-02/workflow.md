# single_hop-dev-02 / workflow

Using only the frozen documentation, what prerequisites are required to pause a LangGraph workflow with interrupt()?

Status: completed; answered: True; reason: None; model calls: 6; seconds: 30.805.

**结论：** 按冻结文档，用 `interrupt()` 暂停 LangGraph 工作流需同时满足三项前置条件：①在节点内调用 `interrupt()`，且传入的 payload 必须可 JSON 序列化；②图编译时配置了 checkpointer（Agent Server 场景由服务器自动处理持久化）；③调用时在 config 中提供 `thread_id`。此外，Python 从 `langgraph.types` 导入 `interrupt`，JS 从 `@langchain/langgraph` 导入 [1][2][3]。

**逐项条件**

1. **调用位置与参数**：`interrupt()` 应在节点函数内、需要暂停的位置调用，payload 须为 JSON 可序列化值 [1]。
2. **持久化（checkpointer）**：文档明确列出“需要 checkpointer 来持久化图状态”，产品环境建议用持久化 checkpointer [1]；human-in-the-loop 工作流需要 checkpointer，以便查看状态并在更新后恢复执行 [3]。图需在编译时配置 checkpointer（或 store，或两者）[2]。例外：使用 Agent Server 时无需手动配置 checkpointer/store，服务器在后台处理持久化 [2]。
3. **thread_id**：checkpointer 以 `thread_id` 为主键存取检查点；没有它，checkpointer 无法保存状态，也无法在 interrupt 后恢复执行 [3]。

**暂停与恢复的机制关系**：触发中断时，LangGraph 通过持久化层保存图状态并等待恢复 [1]；恢复方式是重新调用图并传入 `Command(resume=...)`，该值成为节点内 `interrupt()` 的返回值 [1]。文档强调 `Command(resume=...)` 是唯一适合作为 `invoke()`/`stream()` 输入的 Command 模式，其他参数（`update`、`goto`、`graph`）用于节点返回 [1]。

**导入来源**：Python 为 `from langgraph.types import interrupt`；JS 为 `import { interrupt } from "@langchain/langgraph"` [1]。

**取舍与边界**：checkpointer 是暂停/恢复的必要条件而非可选优化；若省略 `thread_id`，即使配置了 checkpointer 也无法定位并恢复该次中断 [3]。Agent Server 是唯一被文档明确豁免手动配置持久化的场景 [2]。

**缺口说明**：本次可见材料未说明 `interrupt()` 在非节点上下文（如条件边）调用是否可行，也未给出不同 checkpointer 后端对暂停行为的差异；这些不能由现有材料推断。

## Sources

1. Interrupts — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/interrupts.mdx
2. Persistence — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/persistence.mdx
3. Checkpointers — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/checkpointers.mdx
