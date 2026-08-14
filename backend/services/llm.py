"""
统一 LLM 服务层

支持多 Provider：
- 讯飞星火 Spark（通过现有 SparkAPIClient）
- OpenAI 兼容接口（ChatOpenAI / 通义千问）

上层（tools / capabilities）通过 LLMService 调用，不直接依赖具体客户端。
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from core.config import settings
from core.models.spark_client import SparkAPIClient, SparkAPIError

logger = logging.getLogger(__name__)


class LLMService:
    """统一大模型调用服务

    封装底层模型客户端差异，提供统一的 generate / generate_stream 接口。
    自动降级：首选模型失败时尝试备用模型。
    """

    # 模型优先级（降级顺序）——仅使用当前已授权模型
    FALLBACK_CHAIN = [
        "spark-4.0-ultra",      # 旗舰（已授权）
        "spark-lite",           # 轻量兜底（已授权）
    ]

    def __init__(self, default_model: str = "spark-4.0-ultra"):
        self.default_model = default_model
        self._clients: dict[str, SparkAPIClient] = {}
        logger.info(f"[LLMService] 初始化，默认模型: {default_model}")

    def _get_client(self, model_name: str) -> SparkAPIClient:
        """获取或创建模型客户端（懒加载）"""
        if model_name not in self._clients:
            try:
                self._clients[model_name] = SparkAPIClient.for_model(model_name)
            except ValueError:
                logger.warning(f"[LLMService] 未知模型: {model_name}，使用默认")
                self._clients[model_name] = SparkAPIClient.for_model(self.default_model)
        return self._clients[model_name]

    async def generate(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """非流式生成完整内容"""
        model = model or self.default_model
        client = self._get_client(model)
        try:
            return await client.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except SparkAPIError as e:
            logger.warning(f"[LLMService] {model} 失败: {e}，尝试降级")
            return await self._fallback_generate(messages, model, temperature, max_tokens)

    async def generate_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        model = model or self.default_model
        client = self._get_client(model)
        try:
            async for chunk in client.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield chunk
        except SparkAPIError as e:
            logger.warning(f"[LLMService] {model} 流式失败: {e}，尝试降级")
            async for chunk in self._fallback_stream(messages, model, temperature, max_tokens):
                yield chunk

    async def _fallback_generate(
        self,
        messages: list[dict],
        failed_model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """降级非流式生成"""
        for model_name in self.FALLBACK_CHAIN:
            if model_name == failed_model:
                continue
            try:
                client = self._get_client(model_name)
                return await client.chat(messages, temperature=temperature, max_tokens=max_tokens)
            except SparkAPIError:
                continue
        raise SparkAPIError("所有模型均已降级失败")

    async def _fallback_stream(
        self,
        messages: list[dict],
        failed_model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """降级流式生成"""
        for model_name in self.FALLBACK_CHAIN:
            if model_name == failed_model:
                continue
            try:
                client = self._get_client(model_name)
                async for chunk in client.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                    yield chunk
                return
            except SparkAPIError:
                continue
        yield "\n\n[生成中断: 所有模型均已降级失败]"

    async def simple_chat(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """简化的单轮对话"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.generate(messages, model=model, temperature=temperature)

    async def simple_chat_stream(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """简化的单轮流式对话"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        async for chunk in self.generate_stream(messages, model=model, temperature=temperature):
            yield chunk

    def list_available_models(self) -> list[str]:
        """列出可用模型"""
        return settings.list_models()

    @property
    def is_available(self) -> bool:
        """检查 LLM 服务是否可用"""
        return settings.is_configured


# 全局 LLM 服务实例
llm_service = LLMService()
