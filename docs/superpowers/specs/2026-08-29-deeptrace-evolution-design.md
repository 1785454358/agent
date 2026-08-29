# DeepTrace 从零演进式构建设计

- 状态：已完成讨论，待用户复核书面版本
- 日期：2026-08-29
- 目标读者：希望亲手从零搭建 Agent 项目，并将其用于大模型应用开发岗位求职的开发者
- 关联文档：[DeepTrace MVP 设计规范](2026-08-29-deeptrace-mvp-design.md)

## 1. 文档目的

本设计把 DeepTrace 的开发方式从“先建立完整工程底座”调整为“先获得最小可运行 Agent，再逐步演进”。

学习者先亲手实现一个带搜索和网页抓取工具的 CLI 单 Agent。这个版本跑通以后，再依次拆分模块、引入研究流程编排、Multi-Agent、Evidence Store、Verifier、Gap Controller、Memory、持久化、产品界面和评测体系。

每个阶段都必须具备下面四项交付物：

1. 一份手动搭建文档。
2. 一套独立的完整参考实现。
3. 自动化测试和真实问题验收方法。
4. 一个明确的 Git 提交点。

这种组织方式同时服务三个目标：

- 让学习者知道每一行基础代码为什么存在。
- 保证每个阶段都能运行、演示和排错。
- 保留一条适合在面试中讲解的系统演进路径。

## 2. 开发权限与目录边界

### 2.1 正式项目由用户手动搭建

Codex 不直接创建或修改正式项目中的以下内容：

- `backend/`
- `frontend/`
- 正式数据库迁移
- 正式项目配置文件
- 正式项目测试代码

正式项目的目录和文件由用户按照阶段文档亲手创建。文档必须给出 PowerShell 命令、文件职责、接口约束、实现提示、验证命令和常见错误。

只有用户以后明确授权代为修改正式项目时，Codex 才能写入上述目录。

### 2.2 Codex 可以直接生成的内容

Codex 可以创建或修改：

- `docs/` 下的设计、路线图和手动搭建文档。
- `reference_implementation/` 下的分阶段参考实现。

参考实现不能被正式项目导入，也不能替正式项目完成步骤。

## 3. 仓库总体结构

仓库采用正式项目、学习文档和参考实现三部分分离的结构。

```text
agent_new/
├── backend/                         # 用户手动搭建的正式后端
├── frontend/                        # 产品化阶段由用户手动创建
├── docs/
│   ├── roadmap/
│   │   └── deeptrace-evolution.md   # 九阶段总路线图
│   └── stages/
│       ├── 01-cli-single-agent.md
│       ├── 02-reliable-tools.md
│       ├── 03-modular-agent.md
│       ├── 04-research-workflow.md
│       ├── 05-langgraph-multi-agent.md
│       ├── 06-evidence-verifier.md
│       ├── 07-gap-controller.md
│       ├── 08-memory-persistence.md
│       └── 09-product-evaluation.md
├── reference_implementation/
│   ├── stage_01_cli_agent/
│   ├── stage_02_reliable_tools/
│   ├── stage_03_modular_agent/
│   ├── stage_04_research_workflow/
│   ├── stage_05_langgraph_multi_agent/
│   ├── stage_06_evidence_verifier/
│   ├── stage_07_gap_controller/
│   ├── stage_08_memory_persistence/
│   └── stage_09_product_evaluation/
└── README.md
```

正式项目始终表示当前最新状态。参考实现则保留各阶段的完整快照。

## 4. 总体演进路线

| 阶段 | 核心内容 | 阶段演示结果 |
|---|---|---|
| 1 | CLI 单 Agent、搜索、网页抓取 | 输入问题后，Agent 自主搜索、读取网页并输出带来源答案 |
| 2 | 工具层拆分与可靠性增强 | 面对重复结果、网页失败、超时和危险 URL 时仍能稳定运行 |
| 3 | 单 Agent 工程化拆分 | 模型、工具、状态、事件、Prompt 和 Runner 职责清晰 |
| 4 | Planner、Researcher、Writer 顺序编排 | 先拆题，再逐项研究，最后生成结构化报告 |
| 5 | LangGraph Multi-Agent | 最多三个 Researcher 并行执行，支持状态图和故障隔离 |
| 6 | Evidence Store 与 Verifier | 报告事实拥有 Claim 到 Source 的可验证证据链 |
| 7 | Gap Controller 与第二轮补搜 | 根据证据缺口、冲突和预算决定继续或停止 |
| 8 | PostgreSQL、Memory、Checkpoint 与恢复 | 支持历史召回、证据更新、取消、重启恢复和更新研究 |
| 9 | FastAPI、SSE、Web UI、部署与评测 | 形成可部署、可量化、适合作品集展示的完整项目 |

### 4.1 阶段推进规则

- 当前阶段的自动化测试未通过时，不进入下一阶段。
- 当前阶段的真实验收问题无法完成时，不通过增加下一阶段组件来掩盖问题。
- 每次重构必须保持上一阶段已经通过的行为。
- 新目录只在当前代码出现真实拆分需求后创建。
- 每个阶段先解释现有结构解决不了的问题，再引入新的模型或框架。
- 大型阶段可以拆成独立子项目，每个子项目单独设计、计划和验收。

## 5. 阶段 1 的范围

阶段 1 构建一个同步运行的 CLI 单 Agent，只提供两个工具：

- `search_web`
- `fetch_webpage`

模型使用 OpenAI-compatible Chat Completions Tool Calling。搜索使用 Tavily。网页抓取使用 `httpx` 和 Trafilatura。

阶段 1 明确不包含：

- LangChain
- LangGraph
- Multi-Agent
- Planner、Researcher、Writer 角色拆分
- Evidence Store
- Verifier
- Memory
- 数据库
- FastAPI
- Web UI
- PDF、登录网站和浏览器自动化

## 6. 阶段 1 的目录结构

用户按照搭建文档手动创建下面的正式项目结构：

```text
backend/
├── pyproject.toml
├── .env.example
├── src/
│   └── deeptrace/
│       ├── __init__.py
│       ├── config.py
│       ├── cli.py
│       ├── agent.py
│       └── tools.py
└── tests/
    ├── test_agent.py
    ├── test_tools.py
    └── test_live_agent.py
```

| 文件 | 职责 |
|---|---|
| `config.py` | 读取并校验模型、Tavily 和循环次数配置 |
| `cli.py` | 接收终端输入、启动 Agent、显示运行事件和最终答案 |
| `agent.py` | 实现原生 Tool Calling 循环与终止规则 |
| `tools.py` | 实现搜索、网页抓取、Tool Schema 和工具分发 |
| `test_agent.py` | 使用 Fake 模型测试工具循环、错误反馈和终止条件 |
| `test_tools.py` | 测试搜索格式、网页提取、URL 限制和错误结构 |
| `test_live_agent.py` | 显式启用时使用真实 LLM 与 Tavily API Key 验证端到端闭环 |

阶段 1 不创建 `providers/`、`domain/`、`repositories/` 或 `services/`。这些目录在后续阶段出现真实需求时再加入。

## 7. 阶段 1 的运行流程

```text
CLI 读取问题
    ↓
构造 system 和 user 消息
    ↓
调用模型并提供 search_web 与 fetch_webpage 的 Tool Schema
    ↓
模型返回普通答案或 Tool Call
    ↓
程序校验并执行 Tool Call
    ↓
把工具结果追加到消息列表
    ↓
再次调用模型
    ↓
循环直到获得最终答案或达到次数上限
```

阶段 1 的 Agent 可以自行决定：

- 是否需要搜索。
- 使用什么搜索关键词。
- 选择哪些搜索结果。
- 抓取哪些网页。
- 是否继续搜索。
- 什么时候停止并输出答案。

程序负责工具白名单、参数校验、循环上限、工具执行和消息回填。模型不能直接执行网络请求或本地代码。

## 8. 阶段 1 的工具设计

### 8.1 `search_web`

建议函数签名：

```python
def search_web(query: str, max_results: int = 5) -> dict: ...
```

职责：

- 调用 Tavily 搜索。
- 限制结果数量不超过 5。
- 统一返回标题、URL 和搜索摘要。
- 把 Provider 异常转换为结构化工具错误。

搜索摘要只能帮助 Agent 发现和选择网页。阶段 1 可以把摘要放回模型上下文，但最终来源列表只能包含实际抓取过的 URL。

### 8.2 `fetch_webpage`

建议函数签名：

```python
def fetch_webpage(url: str) -> dict: ...
```

职责：

- 只接受 `http` 和 `https` URL。
- 拒绝 localhost 和显式私有 IP。
- 使用 `httpx` 下载普通 HTML。
- 使用 Trafilatura 提取正文。
- 截断过长正文。
- 返回 URL、标题、正文和字符数。
- 把超时、状态码、内容类型和解析失败转换为结构化错误。

阶段 1 不实现浏览器降级、完整 DNS 重绑定防护和复杂重定向策略。这些能力属于阶段 2。

### 8.3 Tool Schema 与分发器

两个 Python 函数拥有对应的 JSON Schema。工具分发器只执行白名单中的工具：

```python
def execute_tool(name: str, arguments: dict) -> dict: ...
```

未知工具、非法参数和执行异常都必须转换成 JSON 可序列化结果。工具失败不会直接终止 Agent，模型可以根据错误选择重试、改换来源或输出部分答案。

## 9. 单 Agent 循环

阶段 1 使用同步 Chat Completions Tool Calling，使消息变化和循环逻辑保持直观。并行 Researcher 出现时再迁移到异步运行时。

Agent Runner 持有：

- 对话消息列表。
- 最大模型调用轮数，默认 8。
- 本次实际搜索记录。
- 本次实际抓取 URL 集合。
- 面向终端的安全事件回调。

每轮执行下面的判断：

1. 调用模型。
2. 如果返回 Tool Call，保存 assistant 消息，逐个执行工具，再保存 tool 消息。
3. 如果返回最终文本，检查来源列表中的 URL 是否属于实际抓取集合。
4. 如果达到轮数上限，返回明确的未完成结果。

第一版不保存模型私有思维链。运行日志只展示模型阶段、工具名、查询、URL、结果数、正文字符数、耗时和错误摘要。

## 10. 阶段 1 的配置

`.env.example` 只声明变量名，不保存真实密钥：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
TAVILY_API_KEY=
DEEPTRACE_MAX_STEPS=8
DEEPTRACE_MAX_PAGE_CHARS=20000
```

配置加载在 CLI 启动时完成。缺少必需变量时，程序列出缺失变量并退出，不发起任何外部请求。

## 11. 错误处理与最小安全边界

| 场景 | 阶段 1 行为 |
|---|---|
| API Key 缺失 | CLI 启动失败并列出缺失变量 |
| 模型调用失败 | 输出明确错误并以非零状态退出 |
| Tavily 调用失败 | 向 Agent 返回结构化工具错误 |
| 网页超时或 4xx/5xx | 向 Agent 返回包含 URL 和错误类型的结果 |
| 非 HTML 内容 | 返回 `unsupported_content_type` |
| 正文提取为空 | 返回 `empty_content` |
| 非法工具名 | 返回 `unknown_tool`，不执行任何函数 |
| 参数校验失败 | 返回 `invalid_arguments` |
| 达到 8 轮上限 | 返回 `max_steps_reached` 和已有来源 |
| localhost 或显式私有 IP | 返回 `unsafe_url` |

网页文本在交给模型时添加明确的不可信数据边界。网页内容不能改变系统目标、工具权限或密钥处理规则。

## 12. 终端交互

CLI 至少支持：

```powershell
uv run python -m deeptrace.cli "今天 AI Agent 领域有哪些热点新闻？"
```

运行期间输出简短事件：

```text
[agent] 正在分析问题
[tool] search_web query="AI Agent 最新新闻"
[tool] 获得 5 条搜索结果
[tool] fetch_webpage url="https://example.com/article"
[tool] 提取正文 8421 字符
[agent] 正在整理答案
```

最终输出包含：

- 对问题的直接回答。
- Agent 实际抓取过的来源 URL。
- 无法确认的信息。
- 工具失败对结果造成的影响。

阶段 1 的来源还不是 Evidence。可验证的引用关系在阶段 6 引入。

## 13. 阶段 1 的测试设计

测试分为默认确定性测试和显式启用的真实集成测试。用户已经具备 LLM 与 Tavily API Key，因此阶段 1 必须提供真实 API 测试入口。

运行普通 `pytest` 时只执行 Fake 测试，不读取真实 API Key，也不调用网络。真实测试使用 `live` Marker，只有明确传入 `-m live` 时执行。

### 13.1 工具测试

- Tavily 响应被转换成稳定的数据结构。
- 搜索结果数量受到限制。
- HTML 正文能够被提取并截断。
- 非 HTML、空正文、超时和 HTTP 错误返回稳定错误码。
- 未知工具不会执行。
- localhost 和显式私有 IP 被拒绝。

### 13.2 Agent 测试

- Fake 模型先调用搜索，再调用抓取，最后返回答案。
- 一轮中出现多个 Tool Call 时全部得到正确 tool message。
- 工具失败后错误能够回填给模型。
- 达到最大轮数时安全终止。
- 最终来源只能来自实际抓取 URL 集合。
- 普通回答不触发任何工具。

### 13.3 真实 API 集成测试

真实测试从本地环境读取：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `TAVILY_API_KEY`

推荐命令：

```powershell
uv run pytest -m live -v
```

真实测试至少验证：

- 模型能够返回合法 Tool Call。
- Tavily 能够返回至少一条搜索结果。
- Agent 至少成功抓取一个公开 HTML 页面。
- 最终运行在最大步数以内结束。
- 最终结果包含至少一个本次实际抓取的 URL。
- 测试输出和异常不包含完整 API Key。

真实新闻和招聘页面会变化，因此测试不能断言固定文章标题、固定招聘数量或完整答案文本。它只断言工具链和关键不变量。

真实测试默认不进入普通 CI。只有 CI 配置了受保护 Secret，并且明确启用 `live` Job 时才运行。

### 13.4 真实问题验收

至少运行两个问题：

```text
今天 AI Agent 领域有哪些热点新闻？
```

```text
调研当前字节跳动 Agent 开发岗位的招聘要求，并给出来源。
```

验收时记录模型名称、运行时间、工具调用顺序、抓取 URL、最终答案和失败页面。真实集成测试通过以后再执行这两项人工验收。

## 14. 阶段 1 的完成标准

满足以下条件后才能进入阶段 2：

1. 用户可以通过 CLI 提交任意中文问题。
2. 真实模型能够自主调用搜索与抓取工具。
3. 一次运行可以完成多次 Tool Call。
4. 最终来源都属于本次实际抓取 URL。
5. 工具失败不会造成无提示崩溃。
6. 达到循环上限后能够安全停止。
7. 默认单元测试不依赖真实网络和 API Key。
8. `pytest -m live` 能使用真实 LLM 与 Tavily API Key 完成端到端测试。
9. 两个真实验收问题至少各完成一次可解释运行。

## 15. 手动搭建文档的写法

阶段 1 的手动搭建文档保存为：

`docs/stages/01-cli-single-agent.md`

文档按照真实操作顺序拆成七部分：

1. 手动创建最小 Python 项目。
2. 完成一次不带工具的真实模型调用。
3. 分别实现和测试搜索、网页抓取函数。
4. 定义 Tool Schema 与工具分发器。
5. 实现单 Agent Tool Calling 循环。
6. 增加运行边界和终端事件。
7. 完成 Fake 测试、真实 API 集成测试与真实问题验收。

每个操作步骤都必须包含：

- 当前步骤解决的问题。
- 用户需要手动执行的 PowerShell 命令。
- 用户需要手动创建的目录与文件。
- 文件职责和函数接口。
- 先编写的失败测试。
- 失败测试的预期现象。
- 实现要求和关键提示。
- 实现后的验证命令。
- 常见错误与排查方法。
- 建议的 Git Commit。

搭建文档不能用“自行实现”“稍后补充”或省略关键接口的占位描述。文档提供足够明确的动作与验收标准，但不直接复制整份参考实现，使用户仍然需要亲手完成代码。

## 16. 参考实现规则

阶段 1 的参考实现保存为：

`reference_implementation/stage_01_cli_agent/`

参考实现拥有独立的：

- `pyproject.toml`
- `.env.example`
- Python 包
- 自动化测试
- Fixture 和 Fake 模型
- 使用 `live` Marker 的真实 API 集成测试
- `README.md`
- 运行命令

参考实现必须满足以下隔离规则：

- 不导入正式项目代码。
- 不要求正式项目目录存在。
- 不和正式项目共享 Python 包或虚拟环境。
- 普通测试默认不调用网络和真实模型。
- 只有执行 `pytest -m live` 时才读取真实 LLM 与 Tavily API Key。
- 真实密钥只保存在用户本地 `.env` 或环境变量中，不能写入参考实现和 Git。
- 文件和步骤能够映射到同阶段搭建文档。
- 参考实现生成时不创建 `backend/` 或 `frontend/`。

后续每个阶段保留独立快照。参考实现的重复代码是有意设计，用于查看两个相邻阶段之间的真实变化。

## 17. 后续阶段的模块演进

### 17.1 阶段 2　可靠工具层

阶段 2 在不改变单 Agent 行为的前提下完成：

- 把 `tools.py` 拆成 `tools/search.py`、`tools/fetch.py` 和 `tools/registry.py`。
- 定义统一搜索结果和网页文档结构。
- 增加 URL 规范化、去重、DNS 与重定向安全检查。
- 增加超时、有限重试、响应大小限制和稳定错误类型。
- 保持搜索摘要不能作为正式证据的约束。

### 17.2 阶段 3　单 Agent 工程化拆分

阶段 3 仍然只有一个 Agent：

- 模型调用从 Agent 循环中分离。
- Tool Schema 与 Python 函数注册统一管理。
- 消息状态、运行事件和使用量单独建模。
- Prompt 从执行代码中分离。
- CLI 只负责输入输出。
- Agent Runner 只负责循环和终止。

### 17.3 阶段 4　研究流程编排

加入 Planner、Researcher 和 Writer，先顺序执行：

```text
用户问题
  ↓
Planner 生成 3 到 6 个研究任务
  ↓
Researcher 逐项搜索和抓取
  ↓
Writer 汇总研究结果
```

每个模块使用结构化输入输出。该阶段开始建立 ResearchPlan、ResearchTask 和 RunState，但不引入 Evidence Store。

### 17.4 阶段 5　LangGraph Multi-Agent

- Planner、Researcher 和 Writer 迁移为图节点。
- 最多三个 Researcher 并行执行。
- 一个 Researcher 失败时保留其他结果。
- 图状态记录任务、网页、错误和轮次。
- 增加并发、网页、Token、费用和时间预算。
- CLI 输出节点级安全事件。

### 17.5 阶段 6　Evidence Store 与 Verifier

阶段 6 引入：

```text
Claim → ClaimEvidence → Evidence → Source
```

Researcher 不再直接生成报告，而是保存 Source、抽取可定位 Evidence、生成最小 Claim，再由 Verifier 判断 Evidence 与 Claim 的关系。

第一版使用内存 Repository，并把证据图导出为 JSON。数据库延后到阶段 8，避免同时学习证据模型和数据库迁移。

Report Writer 只能读取通过发布边界的 Claim。搜索摘要、未抓取页面、未验证 Claim 和过期 Evidence 不能进入确定事实部分。

### 17.6 阶段 7　Gap Controller

Gap Controller 根据以下信息决定继续搜索或停止：

- 高优先级任务覆盖率。
- 关键 Claim 是否有足够证据。
- 是否存在未解决冲突。
- 新一轮是否产生新 Evidence。
- 剩余网页、Token、费用和时间预算。

最多进行两轮研究。证据不足时生成明确的部分报告。

### 17.7 阶段 8　持久化、Memory 与恢复

阶段 8 引入 PostgreSQL、pgvector 和 LangGraph Checkpoint：

- 持久化运行、任务、Source、Evidence、Claim、关系和报告。
- Worker 重启后从 Checkpoint 恢复。
- 已完成的工具调用不会重复执行和计费。
- 历史 Claim 和 Evidence 直接构成研究 Memory。
- 时间敏感 Evidence 必须按规则重新验证。
- 更新研究展示新增、变化、失效和保持不变的结论。
- 支持取消、恢复和父子运行关系。

### 17.8 阶段 9　产品化与评测

阶段 9 分成两个独立子项目。

产品子项目包括 FastAPI、SSE、React Web UI、证据查看、Docker Compose 和部署说明。

评测子项目包括 30 题中文评测集、确定性指标、LLM Judge 与人工抽查、Baseline、消融实验、成本与延迟统计、README、演示脚本和简历描述。

## 18. 与 GitHub 开源项目的对比评测

最终评测必须加入 GitHub 开源 DeepResearch 项目作为外部基线，首批至少包括：

- [Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher)

可以在资源允许时增加其他活跃项目，但不能因为项目数量增加而降低复现质量。

### 18.1 对比原则

- 每个外部项目固定到具体 Commit SHA。
- 保存许可证、安装步骤、配置文件和运行命令。
- 使用相同的开发集问题和运行时间基准。
- 在项目允许的范围内使用相同模型或同等级模型。
- 尽量使用相同搜索 Provider 和结果数量限制。
- 无法统一的条件必须单独列出，不能假装完全公平。
- 外部项目不可用时记录 `unavailable`，不能记为零分。
- DeepTrace 不复制外部项目的核心图、Prompt、Verifier 或停止策略。

### 18.2 对比指标

质量指标：

- Citation Validity
- Citation Correctness
- Citation Completeness
- Research Coverage
- Source Quality
- Conflict Handling
- Freshness

工程指标：

- 成功率
- 端到端延迟
- 模型 Token 与费用
- 搜索、抓取和模型调用次数
- 重复网页比例
- 每条有效 Evidence 的平均成本
- 失败类型与失败恢复情况

### 18.3 实验分层

完整 30 题评测优先用于 DeepTrace 内部版本比较：

1. 单次搜索加直接回答。
2. 单 Researcher，无补充循环。
3. Multi-Agent，无 Verifier。
4. 完整流程，固定执行两轮。
5. DeepTrace 完整版。
6. Memory 首次研究与更新研究。

外部 GitHub 项目先在 20 题开发集运行。环境和费用稳定后，再决定是否运行 10 题隐藏集。

每次实验记录：

- 数据集哈希。
- 项目 Commit SHA。
- 模型与搜索 Provider。
- 配置哈希。
- 运行时间。
- 原始报告和引用。
- Token、费用和延迟。
- 错误与不可用原因。

最终报告同时展示质量和成本，不使用一个综合分数掩盖差异。

## 19. 数据模型的引入顺序

```text
阶段 1    messages + visited_urls
阶段 3    RunState + ToolEvent
阶段 4    ResearchPlan + ResearchTask
阶段 6    Source + Evidence + Claim + ClaimEvidence
阶段 8    ResearchRun + Report + Checkpoint + Memory metadata
```

阶段 1 不提前建立最终领域模型。每次新增模型前，阶段文档必须说明现有结构无法表达什么，以及迁移后哪些测试保证行为没有退化。

## 20. 文档与实现生成顺序

本设计通过书面复核后，先使用 `writing-plans` Skill 为阶段 1 生成详细实施计划。计划获准执行后，只生成：

1. `docs/roadmap/deeptrace-evolution.md`
2. `docs/stages/01-cli-single-agent.md`
3. `reference_implementation/stage_01_cli_agent/`

实施计划和执行过程都不创建正式项目目录。阶段 1 的手动搭建文档与参考实现同步交付，用户按照文档在正式项目中亲手操作。

阶段 1 由用户手动跑通并确认后，再开始阶段 2 的设计、计划、文档和参考实现。阶段 2 到阶段 9 不共用一份提前生成的详细计划。

## 21. 设计决策摘要

1. 采用纵向演进式构建，每个阶段都有可运行版本。
2. 第一版使用原生 OpenAI-compatible Tool Calling，不使用 Agent 框架。
3. 第一版只使用 Tavily 和普通 HTML 抓取。
4. 第一版使用同步代码，Multi-Agent 阶段再迁移异步。
5. 正式项目全部由用户按照文档手动创建。
6. Codex 只直接生成文档和隔离的参考实现。
7. Evidence Store 与 Verifier 在基础编排跑通后引入。
8. 数据库在证据模型稳定以后引入。
9. GitHub 开源项目只作为可复现外部基线和参考，不作为核心代码来源。
10. 每个阶段通过自动化测试和真实问题验收后才能继续。
