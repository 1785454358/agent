"""主模型可调用的工具注册表。"""

from __future__ import annotations

from typing import Any

from deeptrace.tools.search import ToolContext, search_web


JsonObject = dict[str, Any]

TOOL_SCHEMAS: list[JsonObject] = [
    {
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
    },
    {
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
    },
]

__all__ = ["TOOL_SCHEMAS", "ToolContext", "search_web"]
