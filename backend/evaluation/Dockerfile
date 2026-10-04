# syntax=docker/dockerfile:1
# Scorer only: never install the production project or its incompatible SDK.
FROM python:3.12-slim
WORKDIR /evaluation
ENV RAGAS_DO_NOT_TRACK=true LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
# Setup may download the public tokenizer; tests may not.
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
COPY ragas_quality.py ragas_tools.py ./
COPY data ./data
COPY tests ./tests
RUN --network=none python -m pytest tests -q
