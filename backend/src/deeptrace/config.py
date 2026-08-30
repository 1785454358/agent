from __future__ import annotations

from dataclasses import dataclass
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
        )
