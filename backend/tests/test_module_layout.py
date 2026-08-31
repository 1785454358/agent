"""模块化目录的公共接口契约。"""

from datetime import date

from deeptrace.config import Settings
from deeptrace.models import RawDocument, ResearchNote, TokenUsage
from deeptrace.prompts.compression import build_compression_messages
from deeptrace.prompts.research import FINAL_REPORT_PROMPT, build_system_prompt


def test_foundation_packages_expose_stable_interfaces() -> None:
    assert Settings.__name__ == "Settings"
    assert RawDocument.__name__ == "RawDocument"
    assert ResearchNote.__name__ == "ResearchNote"
    assert TokenUsage.__name__ == "TokenUsage"


def test_prompts_are_built_in_prompts_package() -> None:
    system = build_system_prompt(date(2026, 8, 31))
    messages = build_compression_messages(
        active_query="Agent 岗位要求",
        title="招聘页面",
        url="https://example.com/job",
        chunks=[(0, "要求熟悉 LangGraph")],
    )
    assert "2026-08-31" in system
    assert "停止调用工具" in FINAL_REPORT_PROMPT
    assert "Agent 岗位要求" in str(messages[1].content)
