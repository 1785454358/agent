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
