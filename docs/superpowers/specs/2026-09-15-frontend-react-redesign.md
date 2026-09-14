# 前端 React 重构设计

日期：2026-09-15
状态：已确认

## 背景与目标

当前前端是 `backend/src/deeptrace/static/index.html` 单文件页面（内联 CSS/JS，约 10KB），由 FastAPI 根路由直接返回，覆盖模式选择、SSE 事件流、状态行与报告轮询四项功能。

本次重构把它迁移为独立的前端工程，目标有二：

1. **简历技能点**：作品定位是后端 + Agent 工程，加入 React 前端展示前后端分离与前端工程化能力。
2. **提升演示效果**：为 90 秒演示视频提供更专业的界面——三种研究模式说明卡片、来源列表、取消按钮、运行历史。

已确认决策：Vite + React + TypeScript（strict）、TanStack Query 做服务端状态、功能对等 + 演示增强、Docker 多阶段构建集成、延续现有暗色琥珀视觉。

## 非目标

- 不做 SSR / SEO，不引入 Next.js。
- 不引入前端路由（react-router）；整个应用是一个工作台页。
- 不做 E2E 测试与快照测试。
- 不改动后端业务逻辑；仅调整静态文件服务方式。

## 现有后端 API（全部已存在，零后端业务改动）

| 端点 | 用途 |
| --- | --- |
| `POST /researches` | 创建运行，返回 `{id, status, thread_id}`；400 参数错误 / 409 会话忙 |
| `GET /researches` | 运行历史列表 `{id, question, mode, status, created_at}[]` |
| `GET /researches/{run_id}` | 单运行详情，`RunRecord` 序列化（events 截断最近 200 条，含 answer/sources/unresolved_gaps/error） |
| `POST /researches/{run_id}/cancel` | 取消运行 |
| `GET /researches/{run_id}/events` | SSE 事件流；支持 `Last-Event-ID` 断线续传；`done` 事件后关闭 |
| `GET /health` | 健康检查 |

## §1 架构与目录

```text
agent_new/
├── frontend/                  # 新增，Vite + React 18 + TS strict
│   ├── package.json           # 运行时依赖仅 react / react-dom / @tanstack/react-query
│   ├── vite.config.ts         # dev server 5173，/researches、/health 代理到 127.0.0.1:8000
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx           # QueryClientProvider + App
│       ├── App.tsx
│       ├── styles/tokens.css  # 设计 token（CSS 变量）
│       ├── api/client.ts      # 类型化 fetch 封装
│       ├── api/types.ts       # 镜像后端 RunRecord 与事件 payload 的 TS 类型
│       ├── hooks/useRuns.ts       # TanStack Query：运行历史
│       ├── hooks/useRun.ts        # TanStack Query：单运行轮询
│       ├── hooks/useRunEvents.ts  # EventSource 封装
│       └── components/
│           ├── TopBar.tsx
│           ├── ModeCards.tsx
│           ├── StatusBar.tsx
│           ├── RunHistory.tsx
│           ├── EventTimeline.tsx
│           ├── Report.tsx
│           ├── Sources.tsx
│           └── Toast.tsx
└── backend/
    └── src/deeptrace/static/  # 旧 index.html 删除；构建产物由 Docker 写入
```

取舍：不引入 react-router（单页工作台，运行切换用客户端选中状态）；旧单文件页直接删除，不做双轨保留。

## §2 数据流

| 数据 | 方案 | 细节 |
| --- | --- | --- |
| 运行历史 `GET /researches` | `useRuns()`，Query key `['runs']` | `refetchInterval: 10s` + 窗口聚焦重取 |
| 单运行 `GET /researches/{id}` | `useRun(id)` | `refetchInterval` 回调：非终态 2s，终态 `false` 自动停 |
| 事件流（进行中） | `useRunEvents(id, live)` | EventSource；`onerror` 依赖浏览器原生重连（后端 Last-Event-ID 已支持）；收到 `done` 事件手动 close |
| 事件回放（历史运行） | 不走 SSE | `useRun(id)` 返回的 `events`（后端已截断最近 200 条）直接渲染 |
| 提交 / 取消 | mutation | 成功后 `invalidateQueries(['runs'])` 并选中新 run |

本地状态仅两样：`selectedRunId` 与提交中的瞬时 UI 状态。终态集合：`completed / partial / failed / cancelled`。

## §3 组件树与交互

```text
App
├── TopBar              # 品牌 + 模式下拉 + 问题输入 + 开始研究按钮
├── ModeCards           # 三张卡片：模式名 / 一句话说明 / 适用场景（文案取自 README 表格），点选联动
├── StatusBar           # 状态点(动画) + 状态文本 + run id + 取消按钮（running 时出现）
├── (左) RunHistory     # 历史列表：问题截断 / 模式 / 状态徽标 / 时间，点击切换查看
└── (右) 主区
    ├── EventTimeline   # 时间刻度轨，major/final 事件高亮（沿用现有 MAJOR/FINAL 集合）
    ├── Report          # 最终回答，pre-wrap
    └── Sources         # 来源编号列表，外链；unresolved_gaps 非空时单独提示块
```

交互流：提交 → 选中新 run → StatusBar running → SSE 事件滚动追加 → 终态后 Report / Sources 填充，RunHistory 刷新。

## §4 视觉系统

延续现有暗色琥珀基因，手写 CSS，不引入 UI 库。

- **Design tokens**（CSS 变量平移自现页面）：`--bg: #0d1117`、`--panel: #11161f`、`--line`、`--amber: #e8b04b`、`--ok: #5fc98f`、`--err: #e06767`；字体三件套（serif 标题 / sans 正文 / mono 数据）。
- **布局**：顶栏 + 双栏工作台（左 280px RunHistory，右主区）；`<720px` 退化为单栏，历史收进可折叠区。
- **事件流**：保留时间刻度轨视觉语言——左侧竖线 + 圆点 + mono 事件类型 + major 琥珀高亮、final 发光。
- **状态徽标**：`completed/partial` 绿、`failed/cancelled` 红、`running` 琥珀脉冲；动画尊重 `prefers-reduced-motion`。
- 新增组件：ModeCards 用 panel 底 + 琥珀选中描边；Sources 编号 + mono 域名摘录，hover 亮边。

## §5 构建与部署集成

**后端 Dockerfile 改为多阶段**（保留现有 `python:3.12-slim`、`uv sync --frozen --no-dev`、`playwright install --with-deps chromium`、非 root `USER app` 逻辑）：

```dockerfile
# 阶段 1：node:22-alpine，WORKDIR /frontend
#   npm ci --ignore-scripts && npm run build → 产出 /frontend/dist
# 阶段 2：现有后端镜像逻辑不变
#   COPY --from=build /frontend/dist → 后端静态目录
```

- `api.py` 根路由服务 dist 的 `index.html`，静态资源走 `StaticFiles` 挂载；产物缺失时返回 503 与提示文案（本地裸跑后端、未构建前端的场景）。
- CI 增加 frontend job：`npm ci && npm run lint && npm run build && npm test`；后端 uv job 不变。
- `backend/tests/deployment/test_compose_config.py` 增加 Dockerfile 多阶段断言（node 构建阶段存在、dist 拷贝存在、原有断言全部保持）。
- `.gitignore` 补 `frontend/node_modules/`、`frontend/dist/`。
- compose 与 `.env.docker.example` 不变：前端是纯静态产物，无环境变量。

## §6 错误处理与测试

**错误处理**：

- fetch 非 2xx → 统一 `ApiError`（状态码 + 后端 `detail`）；TopBar 下方短暂 toast 展示，5s 自动消失。
- SSE 断线：依赖浏览器原生 EventSource 重连；重连期间 StatusBar 显示"重连中…"。
- 创建运行失败（400/409）：按钮恢复可用，错误文案展示，输入保留。
- 空态文案：Report"（报告生成后将在此展示）"；失败态展示 `record.error`。

**测试策略**（Vitest + Testing Library，Node 环境跑，无浏览器）：

- `api/types.ts` 与后端 `RunRecord` 字段一致性：编译级保证为主，配少量存在性断言。
- `useRun` 轮询：mock fetch，验证非终态 2s / 终态停止。
- `useRunEvents`：mock EventSource，验证事件追加、`done` 后 close、卸载清理。
- 组件：TopBar 空问题不发请求；Report / Sources 终态渲染；ModeCards 点选联动。
- 预计 8-12 个用例；不做快照，不上 E2E。

## 验收标准

1. `npm run build` 产物由 Docker 多阶段构建打入后端镜像；`docker compose --env-file .env.docker up --build` 后根路径展示 React 版页面。
2. 现有四项功能（模式选择、SSE 事件流、状态行、报告）行为不回退；新增模式卡片、来源列表、取消按钮、运行历史可用。
3. 本地开发：`uvicorn` 起后端 + `npm run dev` 起 Vite，代理下全功能可用。
4. `npm run lint`、`npm run build`、`npm test`、`uv run pytest -m "not real"` 全部通过；CI 两个 job 均绿。
