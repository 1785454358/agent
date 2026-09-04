# DeepTrace 阶段 1：CLI 单 Agent

- 状态：已完成
- 用途：记录项目最初的最小闭环及其演进原因
- 当前运行说明：[backend/README.md](../../backend/README.md)

## 阶段目标

阶段 1 验证了一个最小但真实可用的研究 Agent：

1. 用户通过 CLI 提交研究问题。
2. LLM 自主决定调用 `search_web` 或 `fetch_webpage`。
3. 宿主程序校验工具名称和参数，执行真实 Tavily 搜索与网页抓取。
4. 工具结果通过 `tool_call_id` 回填给模型。
5. 模型继续调用工具，或者生成带已抓取来源的最终回答。

这个阶段证明了 Tool Calling 的基本闭环。搜索摘要只用于发现候选页面；只有实际抓取成功的 URL 才能进入最终来源列表。

## 核心机制

```text
用户问题
   ↓
LLM ── tool_calls ──→ Agent Host
 ↑                       ├─ search_web
 └── ToolMessage ←───────└─ fetch_webpage
   ↓
最终回答与来源
```

宿主程序必须保存完整的 Assistant 工具调用消息，并为每次调用返回具有相同 `tool_call_id` 的 ToolMessage。模型只能提出工具调用，真正的网络请求、参数校验、错误处理和来源边界由宿主程序负责。

## 阶段结论

阶段 1 跑通后暴露出三个主要问题：

- 抓取的整页正文不断进入对话，研究轮次增加时上下文快速膨胀。
- HTTPX 与 Trafilatura 对 JavaScript 页面、反爬页面和异常 HTML 不够稳定。
- 手写循环缺少显式状态和节点边界，不利于后续加入证据验证、Memory 和多模块编排。

这些问题已经在阶段 2 中通过 LangGraph、BGE-M3 语义筛选、ResearchNote 压缩和分层抓取链进行处理。当前代码直接维护在 `backend/`，不再使用隔离参考实现，也不需要重新按照旧教程手动创建目录。

## 相关文档

- [项目演进路线图](../roadmap/deeptrace-evolution.md)
- [阶段 2 设计](../superpowers/specs/2026-08-30-stage-02-langgraph-context-compression-design.md)
- [阶段 2 实施记录](../superpowers/plans/2026-08-30-stage-02-langgraph-context-compression.md)
