# live-langgraph-memory-20261107 / workflow

依据 LangGraph 官方 Python 文档，对比 checkpointer 和 Store 的数据范围，说明什么条件下可以跨线程、跨进程重启保留数据。再解释 interrupt() 后如何恢复，节点是否从开头重新运行，以及外部写入如何避免重复副作用。请给出官方引用和必要条件，不要把内存后端当成持久化后端。

Status: completed; answered flag: True; response reason: None; model calls: 12; seconds: 103.849.

**结论**：checkpointer 存单个 thread 的图状态快照，Store 存图状态之外、跨 thread 的应用键值数据 [1]。跨线程靠 Store；跨进程重启靠持久化后端，内存后端不算持久化 [1]。interrupt() 恢复时被中断节点从函数开头重跑，interrupt 前的副作用会再次执行，需幂等或后置 [2][3]。

**数据范围对比**

| 维度 | Checkpointer | Store |
|---|---|---|
| 持久化内容 | 图状态快照（检查点） | 应用自定义键值数据 |
| 作用域 | 单个 thread | 跨 thread |
| 记忆类型 | 短期、thread 作用域 | 长期、跨 thread |
| 典型用途 | 对话连续性、human-in-the-loop、time travel、容错 | 用户偏好、事实、共享知识 |

多数应用两者并用：checkpointer 跟踪当前 thread，store 跟踪跨 thread 的持久信息 [1]。

**跨线程与跨进程重启的条件**

- 跨线程保留：数据须写入 Store，而非仅存在图状态中 [1]。
- 跨进程重启保留：须使用持久化 checkpointer（如 PostgresSaver、SqliteSaver）[1]。
- 内存后端不满足：MemorySaver/InMemorySaver 把检查点存在 RAM，进程重启后全部丢失 [1]。

**interrupt() 恢复**

必要条件：有 checkpointer 持久化图状态（生产用持久化 checkpointer）、config 中有 thread ID、在目标位置调用 interrupt()（payload 须 JSON 可序列化）[3]。恢复时用相同 thread ID 重新调用图并传入 `Command(resume=...)`，该值成为 interrupt() 的返回值 [3]。

```python
graph.invoke(Command(resume=value), config={"configurable": {"thread_id": "same-thread"}})
```

**节点是否从头重跑**

是。恢复时被中断的节点从该节点函数开头重新运行，interrupt 之前的代码会再次执行 [3]。检查点在 super-step 边界保存，不在节点函数内部，因此节点级重跑会重放暂停前的副作用 [2]。

**避免重复副作用**

官方机制 [2][3]：

- interrupt 前的副作用应幂等（upsert、幂等键、写前读检查）。
- 把副作用放在 interrupt 之后，或拆到独立节点。
- 节点提交副作用后失败再重试仍可能重复，需幂等操作或在外部系统去重写入。
- 任务级恢复时已完成任务返回存储结果、不重复执行，但外层入口/节点仍从头重放 [2]。

**缺口说明**：本次可见材料未给出各持久化后端的具体配置参数与性能指标，无法据此比较后端选型；如需可核查对应后端文档。

## Sources

1. Persistence - Docs by LangChain — https://docs.langchain.com/oss/python/langgraph/persistence
2. Graph API overview - Docs by LangChain — https://docs.langchain.com/oss/python/langgraph/graph-api
3. Interrupts - Docs by LangChain — https://docs.langchain.com/oss/python/langgraph/interrupts
