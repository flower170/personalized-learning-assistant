"""
媒体工具 — Mermaid 渲染等媒体操作
"""
from __future__ import annotations

import logging
from typing import Optional

from core.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="mermaid_render",
    description="将 Mermaid 代码渲染为图片",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "包含 Mermaid 代码的文本"},
            "student_id": {"type": "string"},
        },
    },
)
async def tool_mermaid_render(text: str, student_id: str = "anonymous") -> dict:
    """Mermaid → PNG 渲染"""
    from core.utils.mermaid_render import render_mermaid_from_text, extract_mermaid_code
    try:
        img_url, local_path, raw_code = await render_mermaid_from_text(text, student_id)
        if not raw_code:
            raw_code = extract_mermaid_code(text)
        return {
            "image_url": img_url,
            "local_path": str(local_path) if local_path else None,
            "raw_mermaid": raw_code,
            "success": img_url is not None,
        }
    except Exception as e:
        logger.error(f"[Tool] Mermaid 渲染失败: {e}")
        return {"image_url": None, "raw_mermaid": extract_mermaid_code(text), "success": False}
