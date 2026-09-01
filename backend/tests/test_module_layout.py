"""模块化目录的公共接口契约。"""

from datetime import date

from deeptrace.context import (
    CompressionRuntime,
    CompressionService,
    chunk_document,
    retrieve_notes,
    select_relevant_chunks,
)
from deeptrace.evidence import EvidenceStore, ingest_notes
from deeptrace.config import Settings
from deeptrace.models import RawDocument, ResearchNote, ResearchPlan, TokenUsage
from deeptrace.observability import (
    TokenEstimator,
    TokenLedger,
    calculate_round_metrics,
    format_round_metrics,
    format_token_summary,
)
from deeptrace.orchestration import GraphState, ResearchWorkflowNodes, build_research_graph
from deeptrace.prompts.compression import build_compression_messages
from deeptrace.prompts.research import FINAL_REPORT_PROMPT, build_system_prompt
from deeptrace.tools import EXTERNAL_TOOL_SCHEMAS, RESEARCHER_TOOL_SCHEMAS, ToolContext
from deeptrace.tools.scraper import AsyncWebFetcher, normalize_url_before_fetch
from deeptrace.tools.search import search_web
from deeptrace.verification import check_claim_rules
from deeptrace import AgentResult, ResearchAgent, build_real_agent


def test_foundation_packages_expose_stable_interfaces() -> None:
    assert Settings.__name__ == "Settings"
    assert RawDocument.__name__ == "RawDocument"
    assert ResearchNote.__name__ == "ResearchNote"
    assert ResearchPlan.__name__ == "ResearchPlan"
    assert TokenUsage.__name__ == "TokenUsage"
    assert EvidenceStore.__name__ == "EvidenceStore"
    assert callable(ingest_notes)
    assert callable(check_claim_rules)


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


def test_tools_package_exposes_search_and_scraper_interfaces() -> None:
    assert {item["function"]["name"] for item in EXTERNAL_TOOL_SCHEMAS} == {
        "search_web",
        "fetch_webpage",
    }
    assert {item["function"]["name"] for item in RESEARCHER_TOOL_SCHEMAS} == {
        "search_web",
        "fetch_webpage",
        "complete_research_task",
    }
    assert ToolContext.__name__ == "ToolContext"
    assert AsyncWebFetcher.__name__ == "AsyncWebFetcher"
    assert search_web.__name__ == "search_web"
    assert normalize_url_before_fetch("https://example.com/") == "https://example.com/"


def test_context_package_exposes_compression_pipeline() -> None:
    assert CompressionRuntime.__name__ == "CompressionRuntime"
    assert CompressionService.__name__ == "CompressionService"
    assert chunk_document.__name__ == "chunk_document"
    assert retrieve_notes.__name__ == "retrieve_notes"
    assert select_relevant_chunks.__name__ == "select_relevant_chunks"


def test_public_agent_and_orchestration_interfaces() -> None:
    assert AgentResult.__name__ == "AgentResult"
    assert ResearchAgent.__name__ == "ResearchAgent"
    assert callable(build_real_agent)
    assert GraphState.__name__ == "GraphState"
    assert ResearchWorkflowNodes.__name__ == "ResearchWorkflowNodes"
    assert callable(build_research_graph)


def test_observability_package_exposes_token_interfaces() -> None:
    assert TokenEstimator.__name__ == "TokenEstimator"
    assert TokenLedger.__name__ == "TokenLedger"
    assert callable(calculate_round_metrics)
    assert callable(format_round_metrics)
    assert callable(format_token_summary)
