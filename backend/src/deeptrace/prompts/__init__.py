"""DeepTrace 提示词公共接口。"""

from deeptrace.prompts.compression import (
    COMPRESSION_SYSTEM_PROMPT,
    build_compression_messages,
)
from deeptrace.prompts.claim_extractor import (
    CLAIM_EXTRACTOR_SYSTEM_PROMPT,
    build_claim_extractor_messages,
)
from deeptrace.prompts.research import FINAL_REPORT_PROMPT, build_system_prompt

__all__ = [
    "CLAIM_EXTRACTOR_SYSTEM_PROMPT",
    "COMPRESSION_SYSTEM_PROMPT",
    "FINAL_REPORT_PROMPT",
    "build_compression_messages",
    "build_claim_extractor_messages",
    "build_system_prompt",
]
