"""Environment loading and validation for Basic research."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
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


def _bounded_float(
    name: str, default: float, minimum: float, maximum: float
) -> float:
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


@dataclass(frozen=True)
class Settings:
    """Validated settings for the flat, one-pass pipeline."""

    openai_api_key: str
    openai_base_url: str
    openai_model: str
    tavily_api_key: str
    max_page_chars: int = 20_000
    embedding_model_path: Path = Path(r"D:\Dev\Models\bge-m3")
    embedding_batch_size: int = 8
    min_extracted_chars: int = 500
    min_extracted_tokens: int = 200
    allow_benchmark_dns_proxy: bool = False
    search_query_count: int = 3
    max_search_results_per_query: int = 5
    scraper_concurrency: int = 15
    context_max_results: int = 10
    context_direct_threshold_chars: int = 8_000
    context_chunk_chars: int = 1_000
    context_chunk_overlap_chars: int = 100
    context_similarity_threshold: float = 0.42
    planner_timeout_seconds: float = 60.0
    writer_timeout_seconds: float = 60.0
    max_fetched_pages: int = 20
    max_runtime_seconds: int = 300
    use_memory: bool = False
    memory_path: Path = Path("memory/pages.jsonl")
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    max_cost_usd: Decimal | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        embedding_model_path = Path(
            os.getenv(
                "DEEPTRACE_EMBEDDING_MODEL_PATH", r"D:\Dev\Models\bge-m3"
            ).strip()
        )
        if not embedding_model_path.is_dir():
            raise RuntimeError(
                f"Embedding 模型目录不存在：{embedding_model_path}。"
                "请设置 DEEPTRACE_EMBEDDING_MODEL_PATH。"
            )

        chunk_chars = _bounded_int(
            "DEEPTRACE_CONTEXT_CHUNK_CHARS", 1_000, 100, 20_000
        )
        overlap_chars = _bounded_int(
            "DEEPTRACE_CONTEXT_CHUNK_OVERLAP_CHARS", 100, 0, 19_999
        )
        if overlap_chars >= chunk_chars:
            raise RuntimeError(
                "DEEPTRACE_CONTEXT_CHUNK_OVERLAP_CHARS overlap 必须小于 chunk"
            )

        input_cost = _optional_decimal("DEEPTRACE_INPUT_COST_PER_MILLION")
        output_cost = _optional_decimal("DEEPTRACE_OUTPUT_COST_PER_MILLION")
        max_cost = _optional_decimal("DEEPTRACE_MAX_COST_USD")
        if max_cost is not None and (input_cost is None or output_cost is None):
            raise RuntimeError("设置费用上限前必须同时配置模型单价")

        return cls(
            openai_api_key=_required("OPENAI_API_KEY"),
            openai_base_url=_required("OPENAI_BASE_URL"),
            openai_model=_required("OPENAI_MODEL"),
            tavily_api_key=_required("TAVILY_API_KEY"),
            max_page_chars=_bounded_int(
                "DEEPTRACE_MAX_PAGE_CHARS", 20_000, 1_000, 100_000
            ),
            embedding_model_path=embedding_model_path,
            embedding_batch_size=_bounded_int(
                "DEEPTRACE_EMBEDDING_BATCH_SIZE", 8, 1, 256
            ),
            min_extracted_chars=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_CHARS", 500, 1, 1_000_000
            ),
            min_extracted_tokens=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_TOKENS", 200, 1, 100_000
            ),
            allow_benchmark_dns_proxy=_boolean(
                "DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY", False
            ),
            search_query_count=_bounded_int(
                "DEEPTRACE_SEARCH_QUERY_COUNT", 3, 1, 10
            ),
            max_search_results_per_query=_bounded_int(
                "DEEPTRACE_MAX_SEARCH_RESULTS_PER_QUERY", 5, 1, 8
            ),
            scraper_concurrency=_bounded_int(
                "DEEPTRACE_SCRAPER_CONCURRENCY", 15, 1, 100
            ),
            context_max_results=_bounded_int(
                "DEEPTRACE_CONTEXT_MAX_RESULTS", 10, 1, 10
            ),
            context_direct_threshold_chars=_bounded_int(
                "DEEPTRACE_CONTEXT_DIRECT_THRESHOLD_CHARS",
                8_000,
                0,
                1_000_000,
            ),
            context_chunk_chars=chunk_chars,
            context_chunk_overlap_chars=overlap_chars,
            context_similarity_threshold=_bounded_float(
                "DEEPTRACE_CONTEXT_SIMILARITY_THRESHOLD", 0.42, -1.0, 1.0
            ),
            planner_timeout_seconds=_bounded_float(
                "DEEPTRACE_PLANNER_TIMEOUT_SECONDS", 60.0, 0.1, 600.0
            ),
            writer_timeout_seconds=_bounded_float(
                "DEEPTRACE_WRITER_TIMEOUT_SECONDS", 60.0, 0.1, 600.0
            ),
            max_fetched_pages=_bounded_int(
                "DEEPTRACE_MAX_FETCHED_PAGES", 20, 1, 1_000
            ),
            max_runtime_seconds=_bounded_int(
                "DEEPTRACE_MAX_RUNTIME_SECONDS", 300, 1, 86_400
            ),
            use_memory=_boolean("DEEPTRACE_USE_MEMORY", False),
            memory_path=Path(
                os.getenv("DEEPTRACE_MEMORY_PATH", "memory/pages.jsonl")
            ),
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
            max_cost_usd=max_cost,
        )
