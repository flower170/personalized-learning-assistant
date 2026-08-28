"""
智能体基类
所有 Agent 继承此类，统一管理消息构建与模型调用
"""
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncGenerator, Optional

from core.models.spark_client import SparkAPIClient, SparkAPIError
from core.models.schemas import Message, ResourceResponse

logger = logging.getLogger(__name__)

# 模型偶发模仿提示词里的"学生：/助手："对话标签，在回答开头误输出角色标签（如"【助手回答】"）。
# 这些前缀在流式输出时会被剥离，保证正文直接以内容开头。
ROLE_LABEL_PREFIXES = (
    "【助手回答】", "【智能助手】", "【AI 助手】", "【AI助手】",
    "【AI】：", "【AI】:", "【AI】",
    "助手回答：", "助手回答:", "助手回答",
    "AI 助手：", "AI助手：", "AI助手:", "AI助手",
    "AI：", "AI:", "助手：", "助手:",
)
_MAX_ROLE_LABEL_LEN = max(len(p) for p in ROLE_LABEL_PREFIXES)


class BaseAgent(ABC):
    """
    智能体抽象基类
    提供统一的模型调用接口和日志/追踪能力
    """

    fallback_model: str = "qwen-turbo"  # 生成失败时降级到的模型（子类可覆盖）

    def __init__(
        self,
        name: str,
        model_name: str,
        system_prompt: str = "",
        temperature: float = 0.7,
    ):
        self.name = name
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.temperature = temperature
        self._client: Optional[SparkAPIClient] = None
        logger.info(f"智能体 [{self.name}] 初始化，模型: {model_name}")

    @property
    def client(self) -> SparkAPIClient:
        """懒加载模型客户端"""
        if self._client is None:
            self._client = SparkAPIClient.for_model(self.model_name)
        return self._client

    def build_messages(self, user_input: str, context: Optional[list[dict]] = None) -> list[dict]:
        """构建完整的消息列表（system + context + user）"""
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        if context:
            messages.extend(context)
        messages.append({"role": "user", "content": user_input})
        return messages

    async def generate(
        self,
        prompt: str,
        context: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        thinking: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> str:
        """非流式生成完整内容（主模型失败自动降级到 fallback_model）

        :param model: 覆盖本次调用的模型（默认用 self.model_name）；降级仍走 fallback_model
        """
        messages = self.build_messages(prompt, context)
        temp = temperature if temperature is not None else self.temperature
        try:
            client = self.client if model is None else SparkAPIClient.for_model(model)
            result = await client.chat(messages, temperature=temp, max_tokens=max_tokens, thinking=thinking)
        except SparkAPIError as e:
            logger.warning(f"[{self.name}] 模型 {model or self.model_name} 失败: {e}，尝试降级到 {self.fallback_model}")
            fallback = self._fallback_client()
            result = await fallback.chat(messages, temperature=temp, max_tokens=max_tokens, thinking=thinking)
        logger.info(f"[{self.name}] 生成完成（{model or self.model_name}），长度={len(result)}字符")
        return result

    async def generate_stream(
        self,
        prompt: str,
        context: Optional[list[dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
        thinking: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成（带自动降级）"""
        messages = self.build_messages(prompt, context)
        temp = temperature if temperature is not None else self.temperature
        try:
            client = self.client if model is None else SparkAPIClient.for_model(model)
            async for chunk in self._strip_role_label(client.chat_stream(messages, temperature=temp, max_tokens=max_tokens, thinking=thinking)):
                yield chunk
        except SparkAPIError as e:
            logger.warning(f"[{self.name}] 模型 {model or self.model_name} 流式失败: {e}，尝试降级到 {self.fallback_model}")
            try:
                fallback = self._fallback_client()
                async for chunk in self._strip_role_label(fallback.chat_stream(messages, temperature=temp, max_tokens=max_tokens, thinking=thinking)):
                    yield chunk
            except SparkAPIError as e2:
                logger.error(f"[{self.name}] 降级也失败: {e2}")
                yield f"\n\n[生成中断: {e2}]"

    @staticmethod
    async def _strip_role_label(stream):
        """剥离流式输出开头的角色标签前缀（如「【助手回答】你好」→「你好」）。

        只判定开头一段（最长标签长度 + 1 个字符），判定完成后后续原样透传，不影响流式节奏。
        防止弱模型模仿提示词里的对话标签格式、在正文前误加"助手回答""AI："等字样。
        """
        buf = ""
        started = False
        async for chunk in stream:
            if started:
                yield chunk
                continue
            buf += chunk
            s = buf.lstrip()
            hit = next((p for p in ROLE_LABEL_PREFIXES if s.startswith(p)), None)
            if hit is not None:
                started = True
                rest = s[len(hit):].lstrip(" \t\r\n:：")
                if rest:
                    yield rest
            elif len(s) >= _MAX_ROLE_LABEL_LEN + 1:
                # 缓冲已超过最长标签，不可能再是角色标签前缀 → 原样输出
                started = True
                yield buf
        # 流结束：缓冲里未及判定阈值的剩余内容必须原样输出，否则短回复会被整个吞掉
        if buf and not started:
            yield buf

    def _fallback_client(self):
        """降级到备用模型（子类可覆盖 fallback_model）"""
        from core.models.spark_client import SparkAPIClient
        return SparkAPIClient.for_model(self.fallback_model)

    def create_task_response(self, resource_type: str, task_id: Optional[str] = None) -> ResourceResponse:
        """创建标准任务响应"""
        return ResourceResponse(
            task_id=task_id or str(uuid.uuid4()),
            resource_type=resource_type,
            status="generating",
            progress=0.0,
        )

    @abstractmethod
    async def process(self, *args, **kwargs):
        """子类实现的处理入口"""
        pass
