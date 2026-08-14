"""
内容安全工具 — 安全检查与防幻觉原子操作
"""
from __future__ import annotations

import logging

from core.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="content_check",
    description="检查内容安全性",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
    },
)
async def tool_content_check(text: str) -> dict:
    """内容安全检查"""
    from core.utils.content_filter import content_filter
    return content_filter.check_text(text)


@register_tool(
    name="content_filter",
    description="过滤敏感内容",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
    },
)
async def tool_content_filter(text: str) -> str:
    """过滤敏感内容"""
    from core.utils.content_filter import content_filter
    return content_filter.filter_response(text)


@register_tool(
    name="hallucination_check",
    description="检查生成内容的幻觉风险",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
    },
)
async def tool_hallucination_check(text: str) -> dict:
    """防幻觉检查"""
    from core.utils.anti_hallucination import HallucinationGuard
    return HallucinationGuard.verify_academic_content(text)
