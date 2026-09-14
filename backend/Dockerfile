# syntax=docker/dockerfile:1

# ---- Stage 1: 前端构建 ----
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: 锁定的 Python 依赖（含 dev，供测试阶段复用） ----
FROM python:3.12-slim AS python-base
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project

# ---- Stage 3: 在打包环境内运行确定性测试 ----
FROM python-base AS test
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/tests ./tests
COPY backend/Dockerfile ./Dockerfile
COPY docker-compose.yml /docker-compose.yml
RUN uv sync --frozen
RUN uv run pytest -m "not real"

# ---- Stage 4: 发布镜像 ----
FROM python-base
COPY backend/src ./src
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
RUN uv sync --frozen --no-dev
RUN .venv/bin/playwright install --with-deps chromium
COPY --from=frontend /frontend/dist ./src/deeptrace/static
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "deeptrace.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
