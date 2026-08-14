"""
LLM 对话工具 — 大模型调用原子操作
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from core.tools.registry import register_tool
from services.llm import llm_service

logger = logging.getLogger(__name__)


@register_tool(
    name="llm_chat",
    description="调用大模型进行非流式对话",
    parameters={
        "type": "object",
        "properties": {
            "messages": {"type": "array", "description": "消息列表 [role, content]"},
            "model": {"type": "string", "description": "模型名称"},
            "temperature": {"type": "number", "description": "温度 0-1"},
        },
    },
)
async def llm_chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
) -> str:
    """调用大模型生成完整回复"""
    return await llm_service.generate(messages, model=model, temperature=temperature)


@register_tool(
    name="llm_chat_stream",
    description="调用大模型进行流式对话",
    parameters={
        "type": "object",
        "properties": {
            "messages": {"type": "array"},
            "model": {"type": "string"},
            "temperature": {"type": "number"},
        },
    },
)
async def llm_chat_stream(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """调用大模型流式生成"""
    async for chunk in llm_service.generate_stream(messages, model=model, temperature=temperature):
        yield chunk


@register_tool(
    name="simple_chat",
    description="简化的单轮对话（system + user）",
    parameters={
        "type": "object",
        "properties": {
            "system_prompt": {"type": "string"},
            "user_message": {"type": "string"},
        },
    },
)
async def simple_chat(system_prompt: str, user_message: str, **kwargs) -> str:
    """简化的单轮对话"""
    return await llm_service.simple_chat(
        system_prompt, user_message,
        model=kwargs.get("model"),
        temperature=kwargs.get("temperature", 0.7),
    )
