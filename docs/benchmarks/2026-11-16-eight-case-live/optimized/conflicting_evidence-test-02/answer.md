结论：两者并不矛盾——自动选择只适用于直接传入的 schema 类型对象（type[StructuredResponseT]），而 JSON Schema 字典是另一种表示形式，不在自动检测范围内，必须手动包一层策略。

**自动选择的条件** [1]

当把 schema 类型直接传给 `response_format` 时，LangChain 会基于模型能力自动选策略：

- 模型/提供商支持原生结构化输出（如 OpenAI、Anthropic、xAI）→ 选 `ProviderStrategy`
- 其他所有模型 → 选 `ToolStrategy`

**字典的例外** [1]

文档明确警告：JSON Schema 字典直接传给 `response_format` 时不会被自动检测，必须显式包装：

```python
from langchain.agents.structured_output import ProviderStrategy  # 或 ToolStrategy

agent = create_agent(
    model,
    response_format=ProviderStrategy({"type": "object", "properties": {...}})
)
```

**调和逻辑**

`response_format` 的联合类型只接受 `ToolStrategy`、`ProviderStrategy`、`type[StructuredResponseT]` 或 `None` [1]。自动分派的触发条件是“schema 类型对象”这一表示形式；裸字典不属于该类型，无法触发自动检测，因此需要用户显式声明用哪种策略来包装它。可见文档未进一步说明为何字典不做自动检测，只给出了这一区分和手动包装的要求。

**附带条件** [1]

- 自动选择依赖模型 profile 数据（`langchain>=1.1` 动态读取）；数据缺失时需手动指定 profile 或改用显式策略。
- 若同时使用工具，模型须支持工具与结构化输出并行。