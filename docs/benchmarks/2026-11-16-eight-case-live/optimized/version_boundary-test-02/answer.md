**结论**：按冻结文档，`ProviderStrategy` 的 `strict` 参数要求 `langchain>=1.2`；它仅被部分提供商支持，文档明确举例为 OpenAI 和 xAI，且默认值为 `None`（即禁用）[1]。

**依据与边界**：

- **版本边界**：`ProviderStrategy` 类定义（`strict: bool | None = None`）旁的 Info 注释明确写明："The `strict` param requires `langchain>=1.2`" [1]。这意味着在低于 1.2 的 langchain 版本中该参数不可用；文档未说明 1.2 之后是否有进一步版本限制。
- **提供商支持边界**：`strict` 是可选布尔参数，用于启用严格的 schema 遵循（strict schema adherence），"Supported by some providers (e.g., OpenAI and xAI)"，默认 `None`（disabled）[1]。文档以 e.g. 方式举例，因此 OpenAI 与 xAI 是明确列出的支持者，但文档未给出完整支持清单，也未逐一说明 Gemini、Anthropic 等其他原生结构化输出提供商是否支持 `strict`——不能据此推断它们支持或不支持。

**适用范围说明**：以上结论仅基于所给冻结文档摘录；文档未覆盖的内容（完整提供商清单、各提供商对 strict 的具体行为差异）无法从本材料确认。