"""主模型可调用的工具注册表。"""

from __future__ import annotations

from typing import Any

from deeptrace.tools.search import ToolContext, search_web


JsonObject = dict[str, Any]

SEARCH_TOOL_SCHEMA: JsonObject = {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "搜索公开网页。结果只是候选线索，需抓取后才能作为证据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "default": 5,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }

FETCH_TOOL_SCHEMA: JsonObject = {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "抓取公开 HTML 页面，并返回压缩后的研究笔记。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "minLength": 1}},
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    }

EXTERNAL_TOOL_SCHEMAS: list[JsonObject] = [SEARCH_TOOL_SCHEMA, FETCH_TOOL_SCHEMA]

COMPLETE_TASK_TOOL_SCHEMA: JsonObject = {
    "type": "function",
    "function": {
        "name": "complete_research_task",
        "description": "结束当前研究任务并报告覆盖与缺口，不执行外部操作。",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1},
                "summary": {"type": "string", "minLength": 1},
                "covered_topics": {"type": "array", "items": {"type": "string"}},
                "unresolved_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "task_id",
                "summary",
                "covered_topics",
                "unresolved_topics",
            ],
            "additionalProperties": False,
        },
    },
}

RESEARCHER_TOOL_SCHEMAS = [*EXTERNAL_TOOL_SCHEMAS, COMPLETE_TASK_TOOL_SCHEMA]

__all__ = [
    "COMPLETE_TASK_TOOL_SCHEMA",
    "EXTERNAL_TOOL_SCHEMAS",
    "FETCH_TOOL_SCHEMA",
    "RESEARCHER_TOOL_SCHEMAS",
    "SEARCH_TOOL_SCHEMA",
    "ToolContext",
    "search_web",
]
