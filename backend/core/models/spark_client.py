"""
讯飞 Spark API 通用客户端（REST HTTP + OpenAI 兼容格式）
支持 spark-x2-flash / lite / pro / ultra-32k 所有模型
"""
import json
import logging
import base64
from typing import AsyncGenerator, Optional, Callable, Awaitable

import httpx

from core.config import settings, SparkModelConfig

logger = logging.getLogger(__name__)


class SparkAPIClient:
    """
    讯飞 Spark Open API 客户端
    基于 REST HTTP（OpenAI 兼容格式），流式使用 SSE
    无需 WebSocket，认证更简单
    """

    def __init__(self, model_config: SparkModelConfig):
        self.config = model_config
        self._client: Optional[httpx.AsyncClient] = None

    # ======================== HTTP 客户端 ========================

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # 240s：画像抽取等大 prompt 推理耗时可达 ~120s，120s 会误超时降级
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=10.0))
        return self._client

    def _build_headers(self) -> dict:
        """构建认证头（xunfei: Bearer api_key:api_secret；zhipu/bailian: Bearer api_key）"""
        if getattr(self.config, "provider", "xunfei") in ("zhipu", "bailian"):
            return {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            }
        return {
            "Authorization": f"Bearer {self.config.api_key}:{self.config.api_secret}",
            "Content-Type": "application/json",
        }

    def _build_request_data(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = True,
        thinking: Optional[dict] = None,
    ) -> dict:
        """构建请求体（OpenAI 兼容格式）"""
        data = {
            "model": self.config.domain,  # 如 spark-pro, spark-lite, x2-flash 等
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        # 仅 zhipu/GLM 推理模型支持 thinking 控制（如 glm-4.5-flash 关推理防 token 溢出）；
        # 讯飞 Spark 不接受该字段，忽略不传
        if thinking is not None and getattr(self.config, "provider", "xunfei") == "zhipu":
            data["thinking"] = thinking
        return data

    # ======================== 流式调用 (SSE) ========================

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
        thinking: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话（SSE 流式响应）

        :param messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
        :param temperature: 温度 (0-1)
        :param max_tokens: 最大 token 数
        :param on_token: 逐 token 回调
        :param thinking: 推理控制（仅 zhipu/GLM 支持，如 {"type": "disabled"}）
        :yield: 逐段文本
        """
        client = await self._get_client()
        headers = self._build_headers()
        data = self._build_request_data(messages, temperature, max_tokens, stream=True, thinking=thinking)

        try:
            async with client.stream(
                "POST",
                self.config.api_url,
                headers=headers,
                json=data,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"API 错误 [{response.status_code}]: {error_body.decode()[:200]}")
                    raise SparkAPIError(
                        f"HTTP {response.status_code}",
                        code=response.status_code,
                    )

                full_content = ""
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_content += content
                            yield content
                            if on_token:
                                await on_token(content)
                    except json.JSONDecodeError:
                        continue

                # 【修复】空响应检测：HTTP 200 但模型未返回任何内容
                if not full_content:
                    raise SparkEmptyResponseError(self.config.name)

        except SparkAPIError:
            raise  # 直接透传
        except httpx.TimeoutException:
            raise SparkAPIError("请求超时", code=408)
        except httpx.HTTPStatusError as e:
            raise SparkAPIError(f"HTTP {e.response.status_code}", code=e.response.status_code)
        except Exception as e:
            logger.exception(f"流式请求异常: {e}")
            raise SparkConnectionError(str(e))

    # ======================== 非流式调用 ========================

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking: Optional[dict] = None,
    ) -> str:
        """非流式调用，返回完整文本"""
        client = await self._get_client()
        headers = self._build_headers()
        data = self._build_request_data(messages, temperature, max_tokens, stream=False, thinking=thinking)

        try:
            resp = await client.post(
                self.config.api_url,
                headers=headers,
                json=data,
            )
            if resp.status_code != 200:
                raise SparkAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}", code=resp.status_code)

            result = resp.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise SparkEmptyResponseError(self.config.name)
            return content

        except SparkAPIError:
            raise  # 直接透传 SparkAPIError
        except httpx.TimeoutException:
            raise SparkAPIError("请求超时", code=408)
        except Exception as e:
            logger.exception(f"请求异常: {e}")
            raise SparkConnectionError(str(e))

    # ======================== 便捷方法 ========================

    async def simple_chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.7,
    ) -> str:
        """简化的单轮对话"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self.chat(messages, temperature=temperature)

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    @classmethod
    def for_model(cls, model_name: str) -> "SparkAPIClient":
        """按模型名称创建客户端"""
        if model_name == "spark-x2-flash":
            config = settings.SPARK_X2_FLASH
        elif model_name == "spark-lite":
            config = settings.SPARK_LITE
        elif model_name == "spark-pro":
            config = settings.SPARK_PRO
        elif model_name == "spark-ultra-32k":
            config = settings.SPARK_ULTRA_32K
        else:
            config = settings.get_model(model_name)
        if not config:
            raise ValueError(f"未知模型: {model_name}")
        return cls(config)


# ======================== 异常类 ========================

class SparkAPIError(Exception):
    def __init__(self, message: str, code: int = -1):
        self.code = code
        super().__init__(message)


class SparkConnectionError(SparkAPIError):
    """连接错误（是 SparkAPIError 的子类，确保降级机制能捕获）"""
    pass


class SparkEmptyResponseError(SparkAPIError):
    """模型返回空内容（HTTP 200 但内容为空，触发自动降级重试）"""
    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(f"模型 {model_name} 返回空内容，自动切换模型重试", code=200)
