结论：两者不矛盾——自动选择策略只适用于“直接传入 schema 类型（`type[StructuredResponseT]`）”的情形；JSON Schema 字典是显式例外，必须用 `ProviderStrategy` 或 `ToolStrategy` 包装，否则不会被自动识别 [1]。

依据与条件：

- 文档把 `response_format` 的取值分为四类：`ToolStrategy[...]`、`ProviderStrategy[...]`、`type[StructuredResponseT]`、`None`；其中只有 `type[StructuredResponseT]` 被描述为“根据模型能力自动选择最佳策略” [1]。
- 自动选择的具体规则是：模型/提供商支持原生结构化输出时用 `ProviderStrategy`（如 OpenAI、Anthropic、xAI），其余模型用 `ToolStrategy` [1]。
- 同一文档的 Warning 明确：JSON Schema 字典直接传给 `response_format` 时不会被自动检测，必须包进显式策略（`ProviderStrategy` 或 `ToolStrategy`）[1]。

调和方式：这是一条“通用规则 + 显式例外”的关系，而非冲突。自动机制针对的是可识别的 schema 类型（如 Pydantic 类这类 `type[...]`）；JSON Schema 字典只是普通 `dict`，类型签名上虽可传入，但不在自动检测范围内，因此文档要求用户手动指定策略，把“选哪种策略”的决定权交还给调用方 [1]。

这与默认行为的描述一致：agent 默认采用 tool calling 策略，仅对支持原生结构化输出的特定模型切换策略——即“自动”始终发生在已识别 schema 的前提下，而非对任意输入都生效 [1]。

实践取舍（基于上述文档规则的推论，非原文新增事实）：若你的 schema 是 Pydantic 类，可直接传类型享受自动选择；若只有 JSON Schema 字典，需自行判断模型是否支持原生结构化输出，再选 `ProviderStrategy`（支持时）或 `ToolStrategy`（兜底）。文档另注：`langchain>=1.1` 时原生支持能力从模型 profile 动态读取，缺失时可手动提供 profile [1]。