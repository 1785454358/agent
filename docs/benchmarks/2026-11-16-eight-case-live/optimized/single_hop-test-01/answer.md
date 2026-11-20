**结论**：`create_agent` 把校验后的结构化输出放在 agent 状态的 `structured_response` 键（Python；JS 为 `structuredResponse`）[1]。给 `response_format` 直接传一个 schema 类型（`type[StructuredResponseT]`）时，LangChain 按模型能力自动选策略：模型/提供商支持原生结构化输出就用 `ProviderStrategy`，否则用 `ToolStrategy`[1]。

**依据与条件**

- 返回位置：文档说明用户设置 schema 后，模型生成的结构化数据会被捕获、校验，并返回到 agent 状态的 `structured_response` 键；同页还写明它位于 agent 最终状态的该键中[1]。
- 策略选择：`response_format` 可传 `ToolStrategy[...]`、`ProviderStrategy[...]`、`type[StructuredResponseT]` 或 `None`；其中 `type[StructuredResponseT]` 表示“schema 类型——根据模型能力自动选择最佳策略”[1]。
- 选择规则：直接给 schema 类型时，若所选模型和提供商支持原生结构化输出（文档举例 OpenAI、Anthropic/Claude、xAI/Grok）则选 `ProviderStrategy`；其他所有模型选 `ToolStrategy`[1]。
- 边界：原生结构化输出能力在 `langchain>=1.1` 时从模型 profile 动态读取；若不可用需另行指定或手动配置 profile；若同时使用 tools，模型须同时支持 tools 与结构化输出[1]。这些属于文档给出的条件，是否适用于某个具体模型取决于其 profile/提供商能力[1]。