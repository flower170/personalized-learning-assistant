"""
混合策略对话上下文记忆（摘要 + 最近 N 轮）

- 长期记忆：早期对话由 LLM 压缩成 running summary
- 短期精度：最近 RECENT_N 轮保留完整原文
- 存储：Redis HASH（mem:{user_id}:{session_id}），Redis 不可用时内存降级

用法：
    ctx = await context_memory.load_context(user_id, session_id)
    # ... 把 ctx.summary / ctx.messages 注入 LLM prompt ...
    await context_memory.append_turn(user_id, session_id, user_msg, assistant_msg)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ======================== Redis 连接配置（可被环境变量覆盖） ========================

try:
    import redis as _redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("[ContextMemory] redis-py 未安装，使用内存降级模式")

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

MEMORY_TTL = int(os.getenv("MEMORY_TTL", str(7 * 24 * 3600)))   # 7 天
RECENT_N = int(os.getenv("MEMORY_RECENT_N", "6"))                # 保留最近 N 轮
BUFFER = int(os.getenv("MEMORY_BUFFER", "4"))                    # 触发压缩的缓冲
CONDENSE_THRESHOLD = RECENT_N + BUFFER                           # len(messages) 超过即压缩
SUMMARY_MODEL = os.getenv("MEMORY_SUMMARY_MODEL", "spark-lite")

MAX_SUMMARY_CHARS = 1000    # summary 字段长度上限
MAX_MSG_CHARS = 500         # 压缩 prompt 中单条消息截断
MAX_PROMPT_CHARS = 6000     # 整个压缩 prompt 上限


# ======================== 摘要 Prompt ========================

SUMMARY_SYSTEM_PROMPT = """你是对话记忆摘要引擎，负责把一段学习辅导对话压缩成简洁摘要。

输入包含「已有摘要」和「需要归档的新对话」。请把两者合并成一段连贯摘要：
1. 保留：学生身份/年级/专业、学习目标与兴趣、已讨论的知识点、学生的薄弱点与偏好、尚未解决的问题、最新进展。
2. 使用简体中文，按时间线组织，信息不重复、不遗漏关键点。
3. 全文控制在 200 字以内，可用要点式。
4. 若「已有摘要」为空，则只总结新对话。

只输出摘要正文，不要任何前缀、引号或解释。"""


@dataclass
class ContextPayload:
    """一次对话的上下文载荷"""
    summary: str = ""                                     # 早期对话 LLM 摘要
    messages: list[dict] = field(default_factory=list)    # 最近 N 轮 [{role, content}, ...]


class ContextMemory:
    """Redis 混合记忆（含内存降级）"""

    def __init__(self):
        self._redis = None
        self._mem: dict[str, dict] = {}
        self._fallback = False
        self._connect()

    # ---- 连接 ----

    def _connect(self):
        if not REDIS_AVAILABLE:
            self._fallback = True
            logger.info("[ContextMemory] 内存降级 (redis-py 未安装)")
            return
        try:
            self._redis = _redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                password=REDIS_PASSWORD, decode_responses=True,
                socket_connect_timeout=2, socket_timeout=3,
                protocol=2,  # 兼容旧版 Redis(3.x 不支持 RESP3 HELLO)
            )
            self._redis.ping()
            logger.info(f"[ContextMemory] Redis 连接成功 ({REDIS_HOST}:{REDIS_PORT}/{REDIS_DB})")
        except Exception as e:
            self._redis = None
            self._fallback = True
            logger.error(f"[ContextMemory] Redis 连接失败，降级到内存: {e}")

    # ---- Key / 底层读写 ----

    def _key(self, user_id: str, session_id: str) -> str:
        return f"mem:{user_id}:{session_id}"

    def _read(self, key: str) -> tuple[str, list]:
        summary = ""
        messages: list = []
        if self._fallback:
            data = self._mem.get(key, {})
            summary = data.get("summary", "")
            try:
                messages = json.loads(data["messages"]) if data.get("messages") else []
            except (json.JSONDecodeError, TypeError):
                messages = []
            return summary, messages
        if self._redis:
            try:
                summary = self._redis.hget(key, "summary") or ""
                raw = self._redis.hget(key, "messages") or "[]"
                messages = json.loads(raw) if isinstance(raw, str) else []
            except Exception as e:
                logger.warning(f"[ContextMemory] 读取失败: {e}")
        return summary, messages

    def _write(self, key: str, summary: str, messages: list):
        payload = {
            "summary": (summary or "")[:MAX_SUMMARY_CHARS],
            "messages": json.dumps(messages, ensure_ascii=False),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        if self._fallback:
            self._mem[key] = payload
            return
        if self._redis:
            try:
                # Redis 3.0 不支持多字段 HSET,用单字段循环写入
                for _f, _v in payload.items():
                    self._redis.hset(key, _f, _v)
                self._redis.expire(key, MEMORY_TTL)
            except Exception as e:
                logger.error(f"[ContextMemory] 写入失败: {e}")

    # ---- 对外 API ----

    async def load_context(
        self, user_id: str, session_id: str, recent_n: Optional[int] = None,
    ) -> ContextPayload:
        """读取上下文；若历史超阈值，先把旧消息压缩进 summary 再裁剪"""
        n = recent_n or RECENT_N
        key = self._key(user_id, session_id)
        summary, messages = self._read(key)

        if len(messages) > CONDENSE_THRESHOLD and n > 0:
            older = messages[:-n]            # 待归档的旧消息
            recent = messages[-n:]           # 保留的最近轮
            new_summary = await self._condense(summary, older)
            if new_summary:
                summary = new_summary
                logger.info(f"[ContextMemory] 已压缩 {len(older)} 条旧消息 (user={user_id})")
            else:
                logger.warning(f"[ContextMemory] 摘要生成失败，保留原摘要继续")
            messages = recent
            self._write(key, summary, messages)

        return ContextPayload(summary=summary, messages=messages[-n:])

    async def append_turn(
        self, user_id: str, session_id: str,
        user_message: str, assistant_message: str,
    ):
        """记录一轮对话（user + assistant），写路径不调 LLM"""
        if not session_id:
            return
        key = self._key(user_id, session_id)
        summary, messages = self._read(key)
        messages.append({"role": "user", "content": user_message})
        messages.append({"role": "assistant", "content": assistant_message})
        self._write(key, summary, messages)   # 保留已有摘要，否则每轮会把摘要清空

    async def _condense(self, existing_summary: str, older: list[dict]) -> str:
        """用 LLM 把旧消息合并进已有摘要"""
        if not older:
            return existing_summary
        try:
            from services.llm import llm_service

            older_text = "\n".join(
                f"{'学生' if m.get('role') == 'user' else '助手'}: {str(m.get('content', ''))[:MAX_MSG_CHARS]}"
                for m in older
            )[:MAX_PROMPT_CHARS]
            user_prompt = (
                f"[已有摘要]\n{existing_summary or '（无）'}\n\n"
                f"[需要归档的新对话]\n{older_text}"
            )
            result = await llm_service.simple_chat(
                SUMMARY_SYSTEM_PROMPT,
                user_prompt,
                model=SUMMARY_MODEL,
                temperature=0.3,
            )
            return (result or "").strip()[:MAX_SUMMARY_CHARS]
        except Exception as e:
            logger.warning(f"[ContextMemory] 摘要调用失败: {e}")
            return ""

    # ---- 健康检查 ----

    def health_check(self) -> dict:
        return {
            "redis_connected": not self._fallback and self._redis is not None,
            "fallback_mode": self._fallback,
            "memory_sessions": len(self._mem),
            "recent_n": RECENT_N,
            "condense_threshold": CONDENSE_THRESHOLD,
        }


context_memory = ContextMemory()


__all__ = ["ContextMemory", "context_memory", "ContextPayload", "RECENT_N"]
