# Docker 打包与运行

镜像包含前端工作台、FastAPI 后端和 Chromium。模型服务、搜索凭据和语义记忆模型在运行时配置。

## 构建镜像

在仓库根目录执行，使用 Linux containers：

```bash
docker build -f backend/Dockerfile -t deepresearch:0.2.0 .
```

Python 与前端依赖分别由 `backend/uv.lock` 和 `frontend/package-lock.json` 锁定。首次构建需要下载依赖和浏览器，后续构建可复用缓存。

Linux 镜像使用 CPU 版 Torch，不需要 NVIDIA 驱动。Windows 本地开发仍使用原来的 CUDA 12.1 版。镜像以非 root 用户运行，Chromium 使用安装与运行一致的共享目录。

## 本地单机启动

先将 `backend/.env.example` 复制为 `backend/.env`，填写模型与 Tavily 凭据。关键词记忆模式无需准备 BGE-M3 模型。

```bash
docker run --rm --name deepresearch -p 127.0.0.1:8000:8000 --env-file backend/.env -e DEEPTRACE_RUNTIME_MODE=local -e DEEPTRACE_MEMORY_RETRIEVAL=lexical --mount source=deepresearch-runs,target=/app/runs deepresearch:0.2.0
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。API 健康检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)。运行数据保存在 `deepresearch-runs` 命名卷中。

## 研究额度

每个研究子任务由程序批量检索、去重、抓取和读取原文，再调用模型集中整理一次。Plan-and-Execute 与 Multi-Agent 在核对证据后按缺口安排补查，最多补查两轮。以下配置可在运行环境文件中调整，修改后重启 API；分布式模式同时重启 Worker。

`DEEPTRACE_MODEL_THINKING=auto` 对豆包 Seed 2.0 Lite 关闭额外深度思考生成，其他模型保持服务商默认；可使用 `provider_default` 恢复默认，或对支持该参数的服务使用 `enabled` / `disabled` 显式控制。来源、原文与引用校验继续执行。真实完整链路采样见[运行实测](../showcase/case-research-latency.md)。

| 环境变量 | 默认值 | 范围与含义 |
| --- | --- | --- |
| `DEEPTRACE_RESEARCH_SOURCE_TARGET` | 3 | 1–8，每个子任务本批取材的来源目标；失败时尝试同批候选的替代来源 |
| `DEEPTRACE_MAX_MODEL_CALLS` | 20 | 3–100，同一进程内整次运行的模型请求上限，包含失败请求；预留两次收尾调用 |
| `DEEPTRACE_MAX_INPUT_TOKENS` | 100000 | 10000–2000000，整次运行的模型输入准入预算；调用前估算，返回后按服务商 usage 结算 |
| `DEEPTRACE_RESEARCH_MAX_SECONDS` | 600 | 1–3600，研究调用时间窗口；核验与回答另有 120 秒收尾窗口 |
| `DEEPTRACE_EVALUATOR_TIMEOUT_SECONDS` | 120 | 0.1–600，单次证据核验的超时，仍受整次时间预算约束 |
| `DEEPTRACE_AGENT_MAX_PAGES` | 8 | 1–8，每个子任务成功抓取的网页上限 |
| `DEEPTRACE_AGENT_MAX_ITERATIONS` | 24 | 1–50，可选自由 Agent Loop 的模型决策上限；默认批量研究不使用此循环 |
| `DEEPTRACE_MAX_FETCHED_PAGES` | 80 | 整次运行的抓页预算，失败尝试也计入 |
| `DEEPTRACE_MAX_TOOL_CALLS` | 240 | 整次运行经过工具网关的调用预算，所有子任务共享 |

额度是上限；证据充分时提前结束。输入预算预留 20%（最多 20000）用于收尾；缺失 usage 时保留估算值。工作台默认按研究轮次展示简明阶段，展开操作详情可查看逐次检索、抓取、规划及证据核对记录。

## 分布式启动

将 `.env.docker.example` 复制为 `.env.docker`，配置模型、Tavily 和本地 BGE-M3 路径后执行：

```bash
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
```

Compose 启动 MySQL、Redis、Chroma、API 与独立 Worker。前端与 API 由同一服务提供，访问 [http://127.0.0.1:8000](http://127.0.0.1:8000)。停止服务可执行：

```bash
docker compose --env-file .env.docker down
```

## 镜像验收

确定性测试在打包环境内执行：

```bash
docker build -f backend/Dockerfile --target test -t deepresearch:test .
```

镜像冒烟检查验证非 root 用户能够启动 Chromium、读取已打包前端并写入运行目录。检查使用本地 data URL，禁用容器联网，不调用真实模型和搜索服务。

PowerShell：

```powershell
$smokePath = (Resolve-Path backend/tests/deployment/smoke_image.py).Path
docker run --rm --network none --mount "type=bind,source=$smokePath,target=/tmp/smoke_image.py,readonly" deepresearch:0.2.0 python /tmp/smoke_image.py
```

Bash：

```bash
docker run --rm --network none --mount "type=bind,source=$(pwd)/backend/tests/deployment/smoke_image.py,target=/tmp/smoke_image.py,readonly" deepresearch:0.2.0 python /tmp/smoke_image.py
```

## 保存与导入

镜像归档保存在本地，GitHub 仓库提交构建文件和源码：

```bash
docker save -o deepresearch-0.2.0.tar deepresearch:0.2.0
docker load -i deepresearch-0.2.0.tar
```

`.env`、本地研究记录、模型权重和镜像归档不加入 Git 提交。
