# DeepTrace 阶段 1 CLI 单 Agent 参考实现

> **这是隔离参考答案，不是正式项目。**
>
> 这个目录只供学习者卡住时对照。正式项目的目录和代码应按照教学文档亲手创建，不能把整份参考实现复制过去作为完成证明。它拥有独立的依赖、虚拟环境和测试，不依赖正式项目，正式项目也不应导入这里的代码。

完整搭建过程见[阶段 1 教学文档](../../docs/stages/01-cli-single-agent.md)。各阶段的能力边界与验收门禁见[DeepTrace 演进路线图](../../docs/roadmap/deeptrace-evolution.md)。

## 运行条件

需要 Python 3.11 或更高版本、`uv`、可访问公网的网络，以及下面两类真实服务凭据。

- 一个支持 OpenAI-compatible Chat Completions Tool Calling 的模型服务
- Tavily Search API

真实运行和测试会请求模型、Tavily 与公开网页，会消耗 API 配额并可能产生费用。结果也会受到网络、服务额度、限流和目标网页状态影响。测试没有离线替代路径，也不会在凭据缺失时跳过。

## 配置与安装

在 PowerShell 中进入本目录，复制环境变量模板。

```powershell
Copy-Item .env.example .env
```

编辑本地 `.env`，填写真实值。

```dotenv
OPENAI_API_KEY=填写真实模型服务密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=填写支持工具调用的模型名
TAVILY_API_KEY=填写真实Tavily密钥
DEEPTRACE_MAX_STEPS=8
DEEPTRACE_MAX_PAGE_CHARS=20000
```

不要把密钥粘贴到聊天、命令行参数、测试输出或 Git。`.env` 已被本目录的 `.gitignore` 忽略。缺少必需变量时，程序与测试会明确报出变量名并失败，不会静默降级。模板中的占位值也无法通过真实服务鉴权。

安装锁定依赖。

```powershell
uv sync
```

## 运行真实测试

```powershell
uv run pytest -v
```

这条命令会执行完整真实测试，直接调用真实 LLM、真实 Tavily 和真实公开网页。它可能产生费用，也可能因为外部服务或网页临时不可用而失败。请根据失败类型排查配置、额度和网络，不要用 Fake、Mock、Stub、预录响应或跳过测试来替代真实调用。

## 运行一次研究

```powershell
uv run deeptrace "问题"
```

例如可以运行下面的问题。

```powershell
uv run deeptrace "请搜索并抓取 Python 官方文档中的一个页面，然后用中文说明 Python 的一个特点。"
```

运行期间会显示模型调用步数和工具名。最终输出包含答案、成功抓取的来源 URL 与运行状态。`search_web` 返回的摘要只负责发现候选网页。只有 `fetch_webpage` 成功抓取的 URL 才能进入来源列表。

## 两道人工验收题

自动化测试通过后，分别运行下面两题。

```powershell
uv run deeptrace "今天 AI Agent 领域有哪些热点新闻？"
uv run deeptrace "调研当前字节跳动 Agent 开发岗位的招聘要求，并给出来源。"
```

验收时检查两次运行是否都调用了 `search_web` 和 `fetch_webpage`，最终来源是否全部属于本次成功抓取的网页。还应记录实际模型名、运行时间、工具调用顺序、抓取 URL 和失败页面。新闻、招聘页面和搜索排序会变化，不要用固定标题、数量或 URL 作为通过条件。

这里没有宣称联网测试或两道人工题已经通过。你需要在自己的真实凭据和网络环境中完成运行，并保存实际验收结果。

## 阶段 1 的限制

- 运行时是同步的单 Agent 循环，默认最多调用模型 8 步。
- 工具只有 `search_web` 和 `fetch_webpage`。搜索结果最多 5 条，网页正文最多保留 20,000 字符。
- 网页抓取只处理普通公开 HTML，不处理 PDF、登录页面、验证码或浏览器自动化场景。
- 当前安全边界会拒绝 localhost 和显式私有 IP，并禁止自动重定向。它还没有完整的 DNS 重绑定和重定向链 SSRF 防护。
- 当前没有有限重试、缓存、限流、URL 规范化和去重。
- 当前没有 LangChain、LangGraph、Multi-Agent、Planner/Researcher/Writer 拆分、Evidence Store、Verifier、Memory、数据库、FastAPI 或 Web UI。
- 来源列表只能证明网页曾被成功抓取，还没有建立 Claim、Evidence 与 Source 之间的可追踪引用关系。

## 阶段 2 的方向

阶段 2 保持单 Agent 行为不变，先把工具层做稳。搜索、抓取、注册和分发会拆开，搜索结果与网页文档会采用统一结构。工具层还会增加 URL 规范化与去重、超时、有限重试、缓存、限流、响应大小限制，以及 DNS 和重定向链 SSRF 防护。后续编排、证据与产品能力仍按总路线图逐阶段引入。
