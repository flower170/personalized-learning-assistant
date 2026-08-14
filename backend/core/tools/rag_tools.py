"""
RAG 检索工具 — 知识库检索原子操作
"""
from __future__ import annotations

import logging
from typing import Optional

from core.tools.registry import register_tool
from services.rag import rag_service

logger = logging.getLogger(__name__)


@register_tool(
    name="rag_retrieve",
    description="从知识库检索相关知识",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "查询内容"},
            "top_k": {"type": "integer", "description": "返回数量"},
            "temp_file_id": {"type": "string", "description": "临时文档ID"},
        },
    },
)
async def tool_rag_retrieve(
    query: str,
    top_k: int = 5,
    temp_file_id: Optional[str] = None,
) -> tuple[str, list[dict]]:
    """RAG 检索"""
    return await rag_service.rag_retrieve(query, top_k=top_k, temp_file_id=temp_file_id)


@register_tool(
    name="rag_search",
    description="语义检索知识库",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer"},
        },
    },
)
async def tool_rag_search(query: str, top_k: int = 5) -> list[dict]:
    """语义检索"""
    return await rag_service.search(query, top_k=top_k)
