"""Environment loading and validation for Basic research."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少必需的环境变量：{name}。"
            "请将 .env.example 复制为 .env 并填入真实凭据。"
        )
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")


def _choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise RuntimeError(f"{name} must be one of: {allowed}")
    return value


def _optional_decimal(name: str) -> Decimal | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{name} must be a decimal") from exc
    if value < 0:
        raise RuntimeError(f"{name} 不能为负数")
    return value


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} 必须为正整数")
    return value


@dataclass(frozen=True)
class Settings:
    """Validated settings shared by all research modes."""

    openai_api_key: str
    openai_base_url: str
    openai_model: str
    tavily_api_key: str
    runtime_mode: str = "local"
    mysql_dsn: str = ""
    redis_url: str = ""
    redis_job_stream: str = "deeptrace:research:jobs"
    redis_consumer_group: str = "research-workers"
    redis_consumer_name: str = "worker-1"
    redis_claim_idle_ms: int = 60_000
    worker_lease_seconds: int = 120
    worker_max_attempts: int = 3
    redis_cancel_ttl_seconds: int = 86_400
    max_page_chars: int = 20_000
    embedding_model_path: Path = Path(r"D:\Dev\Models\bge-m3")
    embedding_batch_size: int = 8
    memory_retrieval: str = "semantic"
    chroma_url: str = ""
    chroma_collection: str = "deeptrace-long-term-memory"
    chroma_persist_path: Path = Path("chroma")
    memory_top_k: int = 5
    min_extracted_chars: int = 500
    min_extracted_tokens: int = 200
    allow_benchmark_dns_proxy: bool = False
    search_query_count: int = 3
    max_search_results_per_query: int = 5
    scraper_concurrency: int = 15
    # Token budget for every model call. Local models are large-window; the
    # budget is a safety net, not an always-on compressor.
    model_context_tokens: int = 256_000
    context_safety_tokens: int = 4_096
    planner_timeout_seconds: float = 60.0
    writer_timeout_seconds: float = 60.0
    max_fetched_pages: int = 20
    max_tool_calls: int = 30
    tool_timeout_seconds: float = 45.0
    # Agentic execution loop and tool error recovery.
    agent_max_iterations: int = 8
    agent_tool_retry_attempts: int = 3
    agent_tool_retry_base_seconds: float = 0.5
    agent_max_discovered_urls: int = 200
    agent_consecutive_error_limit: int = 3
    agent_completion_nudge_limit: int = 2
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    openai_max_tokens: int | None = None
    # 开发模式：run.completed 事件输出各角色 Token/耗时明细表。
    show_usage_report: bool = False
    # 详细事件：推送 tool.started/tool.completed 等细粒度过程事件。
    verbose_events: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        runtime_mode = _choice(
            "DEEPTRACE_RUNTIME_MODE", "local", {"local", "distributed"}
        )
        mysql_dsn = os.getenv("DEEPTRACE_MYSQL_DSN", "").strip()
        redis_url = os.getenv("DEEPTRACE_REDIS_URL", "").strip()
        memory_retrieval = _choice(
            "DEEPTRACE_MEMORY_RETRIEVAL", "semantic", {"lexical", "semantic"}
        )
        chroma_url = os.getenv("DEEPTRACE_CHROMA_URL", "").strip().rstrip("/")
        if runtime_mode == "distributed":
            if not mysql_dsn:
                raise RuntimeError(
                    "DEEPTRACE_MYSQL_DSN is required in distributed mode"
                )
            if not redis_url:
                raise RuntimeError(
                    "DEEPTRACE_REDIS_URL is required in distributed mode"
                )
            if memory_retrieval == "semantic" and not chroma_url:
                raise RuntimeError(
                    "DEEPTRACE_CHROMA_URL is required for semantic memory "
                    "in distributed mode"
                )
        # 语义召回必须显式配置本地 BGE-M3 模型目录；留空时 lexical 模式不受影响。
        embedding_model_path = Path(
            os.getenv("DEEPTRACE_EMBEDDING_MODEL_PATH", "").strip()
        )

        input_cost = _optional_decimal("DEEPTRACE_INPUT_COST_PER_MILLION")
        output_cost = _optional_decimal("DEEPTRACE_OUTPUT_COST_PER_MILLION")

        return cls(
            openai_api_key=_required("OPENAI_API_KEY"),
            openai_base_url=_required("OPENAI_BASE_URL"),
            openai_model=_required("OPENAI_MODEL"),
            tavily_api_key=_required("TAVILY_API_KEY"),
            runtime_mode=runtime_mode,
            mysql_dsn=mysql_dsn,
            redis_url=redis_url,
            redis_job_stream=os.getenv(
                "DEEPTRACE_REDIS_JOB_STREAM", "deeptrace:research:jobs"
            ).strip(),
            redis_consumer_group=os.getenv(
                "DEEPTRACE_REDIS_CONSUMER_GROUP", "research-workers"
            ).strip(),
            redis_consumer_name=os.getenv(
                "DEEPTRACE_REDIS_CONSUMER_NAME", "worker-1"
            ).strip(),
            redis_claim_idle_ms=_bounded_int(
                "DEEPTRACE_REDIS_CLAIM_IDLE_MS", 60_000, 1_000, 86_400_000
            ),
            worker_lease_seconds=_bounded_int(
                "DEEPTRACE_WORKER_LEASE_SECONDS", 120, 10, 86_400
            ),
            worker_max_attempts=_bounded_int(
                "DEEPTRACE_WORKER_MAX_ATTEMPTS", 3, 1, 20
            ),
            redis_cancel_ttl_seconds=_bounded_int(
                "DEEPTRACE_REDIS_CANCEL_TTL_SECONDS", 86_400, 60, 604_800
            ),
            max_page_chars=_bounded_int(
                "DEEPTRACE_MAX_PAGE_CHARS", 20_000, 1_000, 100_000
            ),
            embedding_model_path=embedding_model_path,
            embedding_batch_size=_bounded_int(
                "DEEPTRACE_EMBEDDING_BATCH_SIZE", 8, 1, 256
            ),
            memory_retrieval=memory_retrieval,
            chroma_url=chroma_url,
            chroma_collection=os.getenv(
                "DEEPTRACE_CHROMA_COLLECTION", "deeptrace-long-term-memory"
            ).strip(),
            chroma_persist_path=Path(
                os.getenv("DEEPTRACE_CHROMA_PERSIST_PATH", "chroma").strip()
            ),
            memory_top_k=_bounded_int("DEEPTRACE_MEMORY_TOP_K", 5, 1, 50),
            min_extracted_chars=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_CHARS", 500, 1, 1_000_000
            ),
            min_extracted_tokens=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_TOKENS", 200, 1, 100_000
            ),
            allow_benchmark_dns_proxy=_boolean(
                "DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY", False
            ),
            search_query_count=_bounded_int("DEEPTRACE_SEARCH_QUERY_COUNT", 3, 1, 10),
            max_search_results_per_query=_bounded_int(
                "DEEPTRACE_MAX_SEARCH_RESULTS_PER_QUERY", 5, 1, 8
            ),
            scraper_concurrency=_bounded_int(
                "DEEPTRACE_SCRAPER_CONCURRENCY", 15, 1, 100
            ),
            model_context_tokens=_bounded_int(
                "DEEPTRACE_MODEL_CONTEXT_TOKENS", 256_000, 8_000, 2_000_000
            ),
            context_safety_tokens=_bounded_int(
                "DEEPTRACE_CONTEXT_SAFETY_TOKENS", 4_096, 0, 100_000
            ),
            planner_timeout_seconds=_bounded_float(
                "DEEPTRACE_PLANNER_TIMEOUT_SECONDS", 60.0, 0.1, 600.0
            ),
            writer_timeout_seconds=_bounded_float(
                "DEEPTRACE_WRITER_TIMEOUT_SECONDS", 60.0, 0.1, 600.0
            ),
            max_fetched_pages=_bounded_int("DEEPTRACE_MAX_FETCHED_PAGES", 20, 1, 1_000),
            max_tool_calls=_bounded_int("DEEPTRACE_MAX_TOOL_CALLS", 30, 1, 200),
            tool_timeout_seconds=_bounded_float(
                "DEEPTRACE_TOOL_TIMEOUT_SECONDS", 45, 0.1, 600
            ),
            agent_max_iterations=_bounded_int(
                "DEEPTRACE_AGENT_MAX_ITERATIONS", 8, 1, 50
            ),
            agent_tool_retry_attempts=_bounded_int(
                "DEEPTRACE_AGENT_TOOL_RETRY_ATTEMPTS", 3, 1, 10
            ),
            agent_tool_retry_base_seconds=_bounded_float(
                "DEEPTRACE_AGENT_TOOL_RETRY_BASE_SECONDS", 0.5, 0.0, 60.0
            ),
            agent_max_discovered_urls=_bounded_int(
                "DEEPTRACE_AGENT_MAX_DISCOVERED_URLS", 200, 1, 5_000
            ),
            agent_consecutive_error_limit=_bounded_int(
                "DEEPTRACE_AGENT_CONSECUTIVE_ERROR_LIMIT", 3, 1, 20
            ),
            agent_completion_nudge_limit=_bounded_int(
                "DEEPTRACE_AGENT_COMPLETION_NUDGE_LIMIT", 2, 0, 10
            ),
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
            openai_max_tokens=_optional_int("OPENAI_MAX_TOKENS"),
            show_usage_report=_boolean("DEEPTRACE_SHOW_USAGE_REPORT", False),
            verbose_events=_boolean("DEEPTRACE_VERBOSE_EVENTS", False),
        )
