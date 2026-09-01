"""环境变量读取、默认值与配置校验。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path

from dotenv import load_dotenv

def _required(name: str) -> str:
    """读取必需的环境变量，如果未配置则抛出异常"""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少必需的环境变量：{name}。"
            "请将 .env.example 复制为 .env 并填入真实凭据。"
        )
    return value

def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """读取整数类型的环境变量，验证是否在有效范围内"""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value

def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    """读取浮点环境变量，并限制在可解释的配置范围内。"""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    """读取明确的布尔开关，避免任意非空字符串被误判为 True。"""
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
    """应用配置类，存储所有必要的配置参数"""
    openai_api_key: str      # OpenAI API 密钥
    openai_base_url: str     # OpenAI API 基础 URL
    openai_model: str        # 使用的模型名称
    tavily_api_key: str      # Tavily 搜索 API 密钥
    max_steps: int = 8       # Agent 最大执行步数
    max_page_chars: int = 20_000  # 网页内容最大字符数
    embedding_model_path: Path = Path(r"D:\Dev\Models\bge-m3")
    min_relevance_score: float = 0.45
    embedding_batch_size: int = 8
    compression_concurrency: int = 3
    min_extracted_chars: int = 500
    min_extracted_tokens: int = 200
    soft_max_steps: int = 8
    hard_max_steps: int = 12
    query_loop_threshold: float = 0.85
    token_encoding: str = "cl100k_base"
    allow_benchmark_dns_proxy: bool = False
    max_research_tasks: int = 4
    max_task_rounds: int = 3
    min_sources_per_task: int = 2
    max_fetched_pages: int = 20
    max_runtime_seconds: int = 600
    max_api_tokens: int = 120_000
    writer_token_reserve_ratio: float = 0.15
    verification_token_reserve_ratio: float = 0.20
    research_runtime_ratio: float = 0.70
    max_verification_gaps_per_task: int = 2
    max_verification_fetches_per_task: int = 3
    max_verification_rounds_per_task: int = 1
    input_cost_per_million: Decimal | None = None
    output_cost_per_million: Decimal | None = None
    max_cost_usd: Decimal | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量创建配置实例"""
        load_dotenv()  # 加载 .env 文件
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

        soft_max_steps = _bounded_int("DEEPTRACE_SOFT_MAX_STEPS", 8, 1, 100)
        hard_max_steps = _bounded_int("DEEPTRACE_HARD_MAX_STEPS", 12, 1, 100)
        if soft_max_steps > hard_max_steps:
            raise RuntimeError("soft_max_steps 不能大于 hard_max_steps")

        token_encoding = os.getenv("DEEPTRACE_TOKEN_ENCODING", "cl100k_base").strip()
        if not token_encoding:
            raise RuntimeError("DEEPTRACE_TOKEN_ENCODING 不能为空")

        input_cost = _optional_decimal("DEEPTRACE_INPUT_COST_PER_MILLION")
        output_cost = _optional_decimal("DEEPTRACE_OUTPUT_COST_PER_MILLION")
        max_cost = _optional_decimal("DEEPTRACE_MAX_COST_USD")
        if max_cost is not None and (input_cost is None or output_cost is None):
            raise RuntimeError("设置费用上限前必须同时配置模型单价")

        writer_reserve_ratio = _bounded_float(
            "DEEPTRACE_WRITER_TOKEN_RESERVE_RATIO", 0.15, 0.05, 0.40
        )
        verification_reserve_ratio = _bounded_float(
            "DEEPTRACE_VERIFICATION_TOKEN_RESERVE_RATIO",
            0.20,
            0.05,
            0.40,
        )
        if writer_reserve_ratio + verification_reserve_ratio >= 0.80:
            raise RuntimeError("Writer 与 Verification Token 预留之和必须小于 0.80")

        return cls(
            openai_api_key=_required("OPENAI_API_KEY"),
            openai_base_url=_required("OPENAI_BASE_URL"),
            openai_model=_required("OPENAI_MODEL"),
            tavily_api_key=_required("TAVILY_API_KEY"),
            max_steps=_bounded_int("DEEPTRACE_MAX_STEPS", 8, 1, 20),
            max_page_chars=_bounded_int(
                "DEEPTRACE_MAX_PAGE_CHARS", 20_000, 1_000, 100_000
            ),
            embedding_model_path=embedding_model_path,
            min_relevance_score=_bounded_float(
                "DEEPTRACE_MIN_RELEVANCE_SCORE", 0.45, 0.0, 1.0
            ),
            embedding_batch_size=_bounded_int(
                "DEEPTRACE_EMBEDDING_BATCH_SIZE", 8, 1, 256
            ),
            compression_concurrency=_bounded_int(
                "DEEPTRACE_COMPRESSION_CONCURRENCY", 3, 1, 32
            ),
            min_extracted_chars=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_CHARS", 500, 1, 1_000_000
            ),
            min_extracted_tokens=_bounded_int(
                "DEEPTRACE_MIN_EXTRACTED_TOKENS", 200, 1, 100_000
            ),
            soft_max_steps=soft_max_steps,
            hard_max_steps=hard_max_steps,
            query_loop_threshold=_bounded_float(
                "DEEPTRACE_QUERY_LOOP_THRESHOLD", 0.85, 0.0, 1.0
            ),
            token_encoding=token_encoding,
            allow_benchmark_dns_proxy=_boolean(
                "DEEPTRACE_ALLOW_BENCHMARK_DNS_PROXY", False
            ),
            max_research_tasks=_bounded_int(
                "DEEPTRACE_MAX_RESEARCH_TASKS", 4, 1, 5
            ),
            max_task_rounds=_bounded_int(
                "DEEPTRACE_MAX_TASK_ROUNDS", 3, 1, 20
            ),
            min_sources_per_task=_bounded_int(
                "DEEPTRACE_MIN_SOURCES_PER_TASK", 2, 1, 5
            ),
            max_fetched_pages=_bounded_int(
                "DEEPTRACE_MAX_FETCHED_PAGES", 20, 1, 1_000
            ),
            max_runtime_seconds=_bounded_int(
                "DEEPTRACE_MAX_RUNTIME_SECONDS", 600, 1, 86_400
            ),
            max_api_tokens=_bounded_int(
                "DEEPTRACE_MAX_API_TOKENS", 120_000, 1, 100_000_000
            ),
            writer_token_reserve_ratio=writer_reserve_ratio,
            verification_token_reserve_ratio=verification_reserve_ratio,
            research_runtime_ratio=_bounded_float(
                "DEEPTRACE_RESEARCH_RUNTIME_RATIO", 0.70, 0.50, 0.90
            ),
            max_verification_gaps_per_task=_bounded_int(
                "DEEPTRACE_MAX_VERIFICATION_GAPS_PER_TASK", 2, 1, 10
            ),
            max_verification_fetches_per_task=_bounded_int(
                "DEEPTRACE_MAX_VERIFICATION_FETCHES_PER_TASK", 3, 1, 10
            ),
            max_verification_rounds_per_task=_bounded_int(
                "DEEPTRACE_MAX_VERIFICATION_ROUNDS_PER_TASK", 1, 1, 10
            ),
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
            max_cost_usd=max_cost,
        )
