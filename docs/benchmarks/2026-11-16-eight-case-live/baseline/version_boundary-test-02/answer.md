**结论**：`ProviderStrategy` 的 `strict` 参数要求 `langchain>=1.2`；其 provider 支持边界是：仅当所选模型与 provider 支持原生结构化输出时适用，文档列举 OpenAI、Anthropic (Claude)、xAI (Grok) 为例，其他模型使用 `ToolStrategy` [1]。

**版本边界**：`strict: bool | None = None` 参数明确要求 `langchain>=1.2` [1]。

**Provider 支持边界**：当直接提供 schema 类型时，LangChain 自动选择策略——若模型和 provider 支持原生结构化输出（例如 OpenAI、Anthropic (Claude)、xAI (Grok)）则使用 `ProviderStrategy`，所有其他模型使用 `ToolStrategy` [1]。文档另在 Provider strategy 章节提及 Gemini 也支持原生结构化输出 [1]。

**补充条件**：原生结构化输出支持从模型的 profile 数据动态读取（需 `langchain>=1.1`）；若数据不可用，需手动指定 profile 或使用其他条件；若同时指定 tools，模型必须支持 tools 与结构化输出的同时使用 [1]。