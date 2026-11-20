# comparison-dev-01 / multi_agent

Using only the frozen documentation, compare Graph API and Functional API for a team needing branching/parallel visualization versus migrating existing procedural code.

Status: partial; answered: False; reason: max_follow_ups_reached; model calls: 13; seconds: 58.536.

**结论先行**：若团队首要需求是分支/并行可视化，冻结文档明确指向 Graph API；若首要需求是以最小改动迁移现有过程式代码，则指向 Functional API。两者共享同一底层运行时，可在同一应用混用[1]。但文档未描述迁移到 Graph API 的路径，故“迁移”维度的比较受此缺口限制。

**分支/并行可视化**

| 维度 | Graph API | Functional API |
|---|---|---|
| 表达方式 | 声明式定义节点、边、共享状态，形成可视化图结构[1] | 命令式，将 LangGraph 特性集成进标准过程式代码[1] |
| 分支 | 多决策点条件分支显式且易于可视化[1] | 仅定位“带简单分支逻辑的线性工作流”[1] |
| 并行 | 并行执行路径后续合并被“自然”处理[1] | 文档未说明并行结构支持[1] |
| 可视化 | 明确列为适用场景（调试、文档、团队协作）[1] | 文档未给出可视化机制或支持程度[1] |

因此，需要复杂分支、并行合并与团队可视化理解的团队，文档证据支持选 Graph API[1]。Functional API 的文档定位限于标准控制流与简单分支，未覆盖并行可视化，不能据此推断其具备该能力[1]。

**迁移现有过程式代码**

- Functional API：文档称可在最小重构下为使用标准控制流的现有代码添加 LangGraph 特性，示例以 `@task` 装饰现有函数、函数体基本不变[1]。但完整迁移步骤与限制未展开[1]。
- Graph API：文档只说明其声明式节点/边/状态写法，**未描述**从过程式代码迁移的路径、写法差异或限制[1]。

故迁移场景下，文档支持 Functional API 作为低改动选项；Graph API 因缺少迁移说明，无法在“迁移便利性”上作出有据比较。

**缺口与适用条件**：迁移到 Graph API 的路径属本次可见材料未覆盖，不能推出全部文档无答案。若团队同时需要可视化与迁移，文档未给出兼顾方案，需另行核查 Graph API 迁移文档；上述结论仅基于该份选择指南[1]。

## Sources

1. Choosing between Graph and Functional APIs — https://github.com/langchain-ai/docs/blob/99dd9a9e38d59b9bff54354f6c3ef790c1be946d/src/oss/langgraph/choosing-apis.mdx
