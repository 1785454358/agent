# GitHub 展示包设计

日期：2026-09-18
状态：用户已确认
仓库：https://github.com/1785454358/agent

## 目标

把 DeepResearch 整理成面向 Agent 开发工程师岗位的 GitHub 展示作品。访客应能在不配置模型、搜索服务和后端的情况下看到一次完整研究流程，并能从 README 快速理解项目的 Agent Harness 设计和源码入口。

展示包保持精简：复用现有工作台，不新建作品站，不模拟完整产品功能，不引入复杂动画或额外服务。

## 名称边界

- 对外项目名统一为 `DeepResearch`，机器可读项目标识统一为 `deepresearch`。
- README、文档标题、前端页面标题、Showcase、API 标题、CLI 帮助、包元数据、CI 镜像标签和 Docker 默认数据库标识不再使用 `ResearchPilot / researchpilot`。
- Python 导入包 `deeptrace`、`DEEPTRACE_*` 环境变量和 `deeptrace` CLI 别名继续保留；它们属于稳定技术命名空间，不作为展示品牌。
- GitHub 仓库地址保持 `https://github.com/1785454358/agent`。

## 交付物

1. 隔离的前端 Showcase Mode。
2. 一张工作台 PNG 截图。
3. 一张简化 Harness SVG 架构图。
4. 面向 Agent 开发岗位重写的 GitHub README 首屏与核心章节。
5. 展示模式组件测试和独立构建检查。

## Showcase Mode

### 启动方式

`frontend/package.json` 增加两个命令：

```text
npm run showcase
npm run build:showcase
```

`showcase` 使用 Vite 的 `showcase` mode。`frontend/src/main.tsx` 只在 `import.meta.env.MODE === "showcase"` 时渲染 Showcase 入口；普通开发、测试和生产构建继续渲染真实 `App`。

### 功能范围

展示模式只提供以下交互：

- 切换 Workflow、Plan-and-Execute、Multi-Agent；
- 选择对应的示例问题；
- 点击开始后显示固定执行轨迹、最终回答和引用来源；
- 清楚显示 `SHOWCASE DATA`，说明内容是固定演示数据；
- 从界面跳转到仓库中的架构文档和关键源码。

不包含真实网络请求、后台轮询、SSE、登录、数据编辑、完整聊天、长期记忆写入或复杂动画。

### 代码边界

新增目录 `frontend/src/showcase/`：

- `fixtures.ts`：三种策略的只读展示数据。
- `ShowcaseApp.tsx`：展示模式状态和页面组合。
- `ShowcaseApp.test.tsx`：隔离与基础交互测试。

展示入口复用现有 `EventTimeline`、`Report`、`Sources` 和图标组件。Showcase 代码不得导入真实 API client 或运行 hooks。真实 `App` 和 API 数据流不增加展示分支。

### 展示数据

三种策略各准备一个围绕当前仓库的示例问题：

- Workflow：模型与外部工具如何经过统一治理；
- Plan-and-Execute：上下文、错误和恢复如何协作；
- Multi-Agent：三个 orchestration strategy 如何共享同一个 Agent Runtime。

事件和回答使用当前代码中的真实术语，引用指向 `1785454358/agent` 仓库中的架构文档和源码。固定数据不声称来自实时联网研究。

## 视觉设计

沿用现有深海军蓝、青绿色和执行轨迹视觉，不重做产品风格。

Showcase 页面包含：

```text
顶部：DeepResearch / SHOWCASE DATA / GitHub 链接
控制区：策略选择 / 示例问题 / 开始展示
主体：执行轨迹
结果：回答 / 引用来源
底部：核心不变量与源码入口
```

唯一突出元素是执行轨迹，它负责表现 Agent 从上下文准备到模型、工具、观察和退出的过程。其余元素保持安静，避免徽章墙、统计卡片和装饰动画。

工作台截图使用桌面宽屏尺寸，默认展示 Plan-and-Execute。截图必须同时包含问题、执行轨迹、回答、引用和 `SHOWCASE DATA` 标记。

简化架构 SVG 只保留：

1. LangGraph Session Graph；
2. Workflow、Plan-and-Execute、Multi-Agent；
3. Shared Agent Loop；
4. Context、Memory、ModelGateway、ToolGateway、Budget、Checkpoint、Evidence Store 和 Ledger。

## README 结构

README 按以下顺序收敛：

1. DeepResearch、CI/License、Agent Harness 一句话定位；
2. 工作台截图；
3. 四个核心能力：共享 Agent Loop、Gateway 边界、三层错误治理、可恢复 Outcome；
4. 三步无 Key Showcase 体验；
5. 三种策略对比；
6. 简化架构图；
7. 本地真实运行和分布式运行入口；
8. 当前验证结果与真实服务边界；
9. 关键源码和文档导览。

README 中所有 GitHub 链接、克隆命令、CI 和源码链接统一指向 `https://github.com/1785454358/agent`。不添加无法证明的性能数据、在线演示地址或生产级声明。

## 错误和隔离

- Showcase fixture 缺失时显示明确错误，不回退到真实 API。
- Showcase 入口不得读取 `.env` 中的 Provider Key。
- 所有来源均为公开仓库 URL，不包含本地绝对路径或凭据。
- `npm run build` 继续构建真实产品；`npm run build:showcase` 单独验证展示入口。
- Showcase Mode 的改动不得改变真实模式的 API、SSE、历史记录和追问行为。

## 验收

1. `npm run showcase` 在无后端、无 Key 环境中打开完整展示。
2. 三种策略均可切换并渲染对应问题、轨迹、回答和来源。
3. Showcase 运行期间不发起真实 API、SSE 或 Provider 请求。
4. 页面在桌面和窄屏下可读，键盘焦点可见，并尊重 reduced motion。
5. `npm run lint`、`npm test`、`npm run build`、`npm run build:showcase` 全部通过。
6. PNG 与 SVG 在 GitHub README 中正常显示。
7. README 的本地链接全部有效，仓库地址统一且没有敏感信息。
8. 文档明确区分固定展示数据、离线测试与真实外部服务验证。
9. 当前工作树不再包含 `ResearchPilot / researchpilot`；`deeptrace / DEEPTRACE_*` 保持可用。
