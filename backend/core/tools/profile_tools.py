"""
画像工具 — 学生画像读写原子操作
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from core.tools.registry import register_tool
from services.llm import llm_service

logger = logging.getLogger(__name__)


@register_tool(
    name="profile_load",
    description="加载学生画像",
    parameters={
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
        },
    },
)
async def tool_profile_load(student_id: str) -> dict:
    """加载学生画像"""
    from core.models.profile import profile_manager
    profile = profile_manager.get_profile(student_id)
    return profile.model_dump() if profile else {}


@register_tool(
    name="profile_save",
    description="保存学生画像",
    parameters={
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "profile_data": {"type": "object"},
        },
    },
)
async def tool_profile_save(student_id: str, profile_data: dict) -> bool:
    """保存学生画像"""
    from core.models.profile import profile_manager, StudentProfile
    try:
        profile = StudentProfile(**profile_data)
        profile_manager.save_profile(profile)
        return True
    except Exception as e:
        logger.error(f"[Tool] 保存画像失败: {e}")
        return False


@register_tool(
    name="extract_profile_from_text",
    description="从对话文本中提取结构化画像",
    parameters={
        "type": "object",
        "properties": {
            "conversation_text": {"type": "string"},
            "base_info": {"type": "object"},
        },
    },
)
async def tool_extract_profile(conversation_text: str, base_info: Optional[dict] = None) -> Optional[dict]:
    """从对话文本提取画像"""
    from core.models.profile import PROFILE_EXTRACTION_SYSTEM_PROMPT
    prompt = f"{PROFILE_EXTRACTION_SYSTEM_PROMPT}\n\n"
    if base_info:
        prompt += f"[基础信息]\n{json.dumps(base_info, ensure_ascii=False, indent=2)}\n\n"
    prompt += f"[完整对话记录]\n{conversation_text}\n\n请提取完整画像，输出严格JSON格式。"
    try:
        response = await llm_service.simple_chat("", prompt, temperature=0.1)
        from core.capabilities.impl.profile_chat_agent import profile_chat_agent
        parsed = profile_chat_agent._try_extract_json(response)
        return parsed
    except Exception as e:
        logger.error(f"[Tool] 画像提取失败: {e}")
        return None
