FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic

RUN uv sync --frozen --no-dev
RUN .venv/bin/playwright install --with-deps chromium
RUN useradd --create-home --uid 10001 app && chown -R app:app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000
CMD ["uvicorn", "deeptrace.api:app", "--host", "0.0.0.0", "--port", "8000"]
