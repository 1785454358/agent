**结论**：`create_agent` 把校验后的结构化输出放在 agent 最终状态的 `structured_response` 键中；直接向 `response_format` 传入 schema 类型（`type[StructuredResponseT]`）会让 LangChain 按模型能力自动选策略——模型/提供商支持原生结构化输出时用 `ProviderStrategy`，否则用 `ToolStrategy`。[1]

**返回位置**：文档说明，模型生成结构化数据后会被捕获、校验，并返回到 agent 状态的 `'structured_response'` 键；并明确为“agent's final state”的 `structured_response` 键。示例中 `result["structured_response"]` 得到 `ContactInfo(...)` 实例。[1]

**策略选择**：`response_format` 可接收 `ToolStrategy[StructuredResponseT]`、`ProviderStrategy[StructuredResponseT]`、`type[StructuredResponseT]` 或 `None`。当直接提供 schema 类型时，LangChain 自动选择：若所选模型和提供商支持原生结构化输出（如 OpenAI、Anthropic/Claude、xAI/Grok），用 `ProviderStrategy`；其他所有模型用 `ToolStrategy`。文档还注明 `langchain>=1.1` 时原生结构化输出支持会动态读取模型 profile 数据；若不可用需另行指定或手动配置，且若同时使用工具，模型须支持工具与结构化输出同时使用。[1]