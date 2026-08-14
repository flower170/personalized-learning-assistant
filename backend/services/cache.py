"""
统一缓存服务层 — 自包含实现（不依赖 app/）

内联了原 app/redis/profile_chat_cache.py 的完整逻辑：
- Redis 连接（含内存降级）
- 会话管理（HASH 结构）
- 业务模式隔离
- 画像对话进度追踪
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ======================== Redis 连接配置 ========================

try:
    import redis as _redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("[Cache] redis-py 未安装，使用内存降级模式")

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
SESSION_TTL = 7 * 24 * 3600  # 7 天

# ======================== 阶段/业务模式常量 ========================

# 采集阶段
STAGE_BASE_INFO = "base_info"
STAGE_ACADEMIC = "academic"
STAGE_DIMENSION = "dimension"
STAGE_COMPLETED = "completed"

# 业务模式
BIZ_PROFILE = "profile"
BIZ_RESOURCE = "resource"
BIZ_PLAN = "plan"

# 6+1 标准维度（命名与 StudentProfile schema / 抽取 prompt 保持一致）
STANDARD_DIMS = [
    "knowledge_base", "cognitive_style", "preferred_pace",
    "error_prone_areas", "interests", "goal_attribute",
]
EXTRA_DIM = "daily_available_hours"


# ======================== 核心实现 ========================

class ProfileChatCache:
    """画像对话 Redis 会话缓存（含内存降级）"""

    def __init__(self):
        self._redis = None
        self._mem: dict[str, dict] = {}
        self._fallback = False
        self._connect()

    def _connect(self):
        if not REDIS_AVAILABLE:
            self._fallback = True
            logger.info("[Cache] 使用内存降级模式 (redis-py 未安装)")
            return
        try:
            self._redis = _redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                password=REDIS_PASSWORD, decode_responses=True,
                socket_connect_timeout=2, socket_timeout=3,
                protocol=2,  # 兼容旧版 Redis(3.x 不支持 RESP3 HELLO)
            )
            self._redis.ping()
            logger.info("[Cache] Redis 连接成功")
        except Exception as e:
            self._redis = None
            self._fallback = True
            logger.error(f"[Cache] Redis 连接失败，降级到内存: {e}")

    # ---- Key 管理 ----

    def _key(self, student_id: str, session_id: str, biz_mode: str = "") -> str:
        if biz_mode:
            return f"a3:{student_id}:{biz_mode}:{session_id}"
        return f"profile_chat:{student_id}:{session_id}"

    def _biz_mode_key(self, student_id: str) -> str:
        return f"a3:{student_id}:current_biz_mode"

    def _ttl(self) -> int:
        return SESSION_TTL

    # ---- 业务模式 ----

    def set_biz_mode(self, student_id: str, mode: str) -> bool:
        key = self._biz_mode_key(student_id)
        try:
            self._hset(key, "mode", mode)
            self._expire_key(key, SESSION_TTL)
            return True
        except Exception as e:
            logger.error(f"[Cache] 设置业务模式失败: {e}")
            return False

    def get_biz_mode(self, student_id: str) -> str:
        key = self._biz_mode_key(student_id)
        try:
            return self._hget(key, "mode", "")
        except Exception:
            return ""

    def clear_biz_mode(self, student_id: str):
        key = self._biz_mode_key(student_id)
        try:
            self._delete(key)
        except Exception:
            pass

    # ---- 会话初始化 ----

    def init_chat_session(self, student_id: str, base_info: dict,
                          biz_mode: str = BIZ_PROFILE) -> str:
        existing = self._find_active_session(student_id, biz_mode)
        if existing:
            session_id = existing
            logger.info(f"[Cache] 复用会话: {session_id} (mode={biz_mode})")
            self._hset(self._key(student_id, session_id, biz_mode),
                       "base_info", json.dumps(base_info, ensure_ascii=False))
            self._expire(student_id, session_id)
            return session_id

        session_id = uuid.uuid4().hex[:12]
        key = self._key(student_id, session_id, biz_mode)

        init_data = {"session_id": session_id, "created_at": datetime.now().isoformat()}
        base_info = {**init_data, **base_info}

        self._hset(key, "base_info", json.dumps(base_info, ensure_ascii=False))
        self._hset(key, "chat_history", json.dumps([], ensure_ascii=False))
        self._hset(key, "collect_progress", json.dumps({
            "stage": STAGE_BASE_INFO, "current_dim": None,
            "dims_done": [], "asked_count": 0,
        }, ensure_ascii=False))
        self._hset(key, "temp_profile_draft", json.dumps({}, ensure_ascii=False))
        self._expire(student_id, session_id)
        logger.info(f"[Cache] 新会话: {session_id} (student={student_id})")
        return session_id

    def _find_active_session(self, student_id: str, biz_mode: str = BIZ_PROFILE) -> Optional[str]:
        prefix = f"profile_chat:{student_id}:" if not biz_mode else f"a3:{student_id}:{biz_mode}:"
        if self._fallback:
            for skey in self._mem:
                if skey.startswith(prefix):
                    data = self._mem[skey]
                    progress = data.get("collect_progress", "{}")
                    if isinstance(progress, str):
                        try:
                            progress = json.loads(progress)
                        except json.JSONDecodeError:
                            progress = {}
                    if progress.get("stage") != STAGE_COMPLETED:
                        return skey.split(":")[-1]
            return None
        if not self._redis:
            return None
        try:
            keys = self._redis.keys(f"{prefix}*")
            for key in keys:
                progress_raw = self._redis.hget(key, "collect_progress")
                if progress_raw:
                    try:
                        progress = json.loads(progress_raw)
                        if progress.get("stage") != STAGE_COMPLETED:
                            return key.split(":")[-1]
                    except json.JSONDecodeError:
                        continue
            return None
        except Exception as e:
            logger.warning(f"[Cache] 查找会话失败: {e}")
            return None

    # ---- 消息管理 ----

    def append_chat_msg(self, student_id: str, session_id: str, role: str,
                        content: str, biz_mode: str = ""):
        key = self._key(student_id, session_id, biz_mode)
        history_raw = self._hget(key, "chat_history", "[]")
        try:
            history = json.loads(history_raw)
        except json.JSONDecodeError:
            history = []
        history.append({"role": role, "content": content,
                        "timestamp": datetime.now().isoformat()})
        self._hset(key, "chat_history", json.dumps(history, ensure_ascii=False))
        self._expire(student_id, session_id)

    # ---- 上下文读取 ----

    def get_full_context(self, student_id: str, session_id: str,
                         biz_mode: str = "") -> dict:
        key = self._key(student_id, session_id, biz_mode)
        return {
            "base_info": self._safe_json(self._hget(key, "base_info", "{}")),
            "chat_history": self._safe_json(self._hget(key, "chat_history", "[]")),
            "collect_progress": self._safe_json(self._hget(key, "collect_progress", "{}")),
            "temp_profile_draft": self._safe_json(self._hget(key, "temp_profile_draft", "{}")),
            "consecutive_valid_replies": self._safe_json(self._hget(key, "consecutive_valid_replies", "0")),
        }

    def get_recent_chats(self, student_id: str, session_id: str,
                         n: int = 10) -> list[dict]:
        ctx = self.get_full_context(student_id, session_id)
        history = ctx.get("chat_history", [])
        return history[-n:] if len(history) > n else history

    def save_full_context(self, student_id: str, session_id: str, context: dict,
                          biz_mode: str = ""):
        """把完整 context 写回 Redis HASH（供后台抽取任务回填 temp_profile_draft 等）"""
        fields = ["base_info", "chat_history", "collect_progress",
                  "temp_profile_draft", "consecutive_valid_replies"]
        updates = {}
        for f in fields:
            val = context.get(f)
            if val is not None:
                try:
                    updates[f] = json.dumps(val, ensure_ascii=False)
                except (TypeError, ValueError):
                    continue
        if updates:
            self.batch_update_session(student_id, session_id, updates, biz_mode)

    # ---- 进度管理 ----

    def update_collect_progress(self, student_id: str, session_id: str,
                                stage: str, current_dim: Optional[str] = None,
                                dims_done: Optional[list] = None,
                                asked_count: Optional[int] = None,
                                biz_mode: str = ""):
        key = self._key(student_id, session_id, biz_mode)
        progress = self._safe_json(self._hget(key, "collect_progress", "{}"))
        progress["stage"] = stage
        if current_dim is not None:
            progress["current_dim"] = current_dim
        if dims_done is not None:
            progress["dims_done"] = dims_done
        if asked_count is not None:
            progress["asked_count"] = asked_count
        self._hset(key, "collect_progress", json.dumps(progress, ensure_ascii=False))
        self._expire(student_id, session_id)

    # ---- 草稿 ----

    def save_temp_draft(self, student_id: str, session_id: str, draft: dict):
        key = self._key(student_id, session_id)
        self._hset(key, "temp_profile_draft", json.dumps(draft, ensure_ascii=False))
        self._expire(student_id, session_id)

    def get_temp_draft(self, student_id: str, session_id: str) -> dict:
        raw = self._hget(self._key(student_id, session_id), "temp_profile_draft", "{}")
        return self._safe_json(raw)

    # ---- 会话终止 ----

    def end_chat_session(self, student_id: str, session_id: str, archive: bool = True):
        key = self._key(student_id, session_id)
        if archive:
            self.update_collect_progress(student_id, session_id, stage=STAGE_COMPLETED)
            logger.info(f"[Cache] 会话归档: {session_id}")
        else:
            self._delete(key)
            logger.info(f"[Cache] 会话已删除: {session_id}")

    # ---- 批量写入 ----

    def batch_update_session(self, student_id: str, session_id: str,
                             updates: dict[str, str], biz_mode: str = ""):
        if not updates:
            return
        key = self._key(student_id, session_id, biz_mode)
        if self._fallback:
            if key not in self._mem:
                self._mem[key] = {}
            self._mem[key].update(updates)
            return
        if self._redis:
            try:
                # Redis 3.0 不支持多字段 HSET,用单字段循环写入
                for field, val in updates.items():
                    self._redis.hset(key, field, val)
                self._expire(student_id, session_id)
            except Exception as e:
                logger.error(f"[Cache] 批量写入失败: {e}")

    # ---- 健康检查 ----

    def health_check(self) -> dict:
        return {
            "redis_connected": not self._fallback and self._redis is not None,
            "fallback_mode": self._fallback,
            "memory_sessions": len(self._mem),
        }

    # ---- 底层操作（带内存降级）----

    def _hset(self, key: str, field: str, value: str):
        if self._fallback:
            if key not in self._mem:
                self._mem[key] = {}
            self._mem[key][field] = value
            return
        if self._redis:
            try:
                self._redis.hset(key, field, value)
            except Exception as e:
                logger.error(f"[Cache] Redis hset 失败: {e}")

    def _hget(self, key: str, field: str, default: str = "") -> str:
        if self._fallback:
            return self._mem.get(key, {}).get(field, default)
        if self._redis:
            try:
                val = self._redis.hget(key, field)
                return val if val is not None else default
            except Exception as e:
                logger.error(f"[Cache] Redis hget 失败: {e}")
                return default
        return default

    def _expire_key(self, key: str, ttl: int):
        if self._fallback or not self._redis:
            return
        try:
            self._redis.expire(key, ttl)
        except Exception:
            pass

    def _expire(self, student_id: str, session_id: str):
        self._expire_key(self._key(student_id, session_id), self._ttl())

    def _delete(self, key: str):
        if self._fallback:
            self._mem.pop(key, None)
            return
        if self._redis:
            try:
                self._redis.delete(key)
            except Exception as e:
                logger.warning(f"[Cache] delete 失败: {e}")

    @staticmethod
    def _safe_json(raw: str) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {} if raw.startswith("{") else []


# ======================== 全局实例 ========================

profile_chat_cache = ProfileChatCache()


# ======================== 统一缓存服务（对外接口）========================

class CacheService:
    """统一缓存服务 — 对外提供简洁接口"""

    def __init__(self):
        self._cache = profile_chat_cache

    def init_chat_session(self, student_id: str, base_info: dict,
                          biz_mode: str = BIZ_PROFILE) -> str:
        return self._cache.init_chat_session(student_id, base_info, biz_mode)

    def get_full_context(self, student_id: str, session_id: str,
                         biz_mode: str = "") -> dict:
        return self._cache.get_full_context(student_id, session_id, biz_mode)

    def batch_update_session(self, student_id: str, session_id: str,
                             updates: dict[str, str], biz_mode: str = ""):
        self._cache.batch_update_session(student_id, session_id, updates, biz_mode)

    def append_chat_msg(self, student_id: str, session_id: str, role: str,
                        content: str, biz_mode: str = ""):
        self._cache.append_chat_msg(student_id, session_id, role, content, biz_mode)

    def end_chat_session(self, student_id: str, session_id: str, archive: bool = True):
        self._cache.end_chat_session(student_id, session_id, archive)

    def get_recent_chats(self, student_id: str, session_id: str,
                         n: int = 10) -> list[dict]:
        return self._cache.get_recent_chats(student_id, session_id, n)

    def set_biz_mode(self, student_id: str, mode: str) -> bool:
        return self._cache.set_biz_mode(student_id, mode)

    def get_biz_mode(self, student_id: str) -> str:
        return self._cache.get_biz_mode(student_id)

    def clear_biz_mode(self, student_id: str):
        self._cache.clear_biz_mode(student_id)

    async def get_json(self, key: str) -> Optional[Any]:
        """通用 JSON 缓存读取"""
        if self._cache._fallback or not self._cache._redis:
            return None
        try:
            val = self._cache._redis.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    async def set_json(self, key: str, value: Any, ttl: int = 3600):
        """通用 JSON 缓存写入"""
        if self._cache._fallback or not self._cache._redis:
            return
        try:
            self._cache._redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception:
            pass

    def health_check(self) -> dict:
        return self._cache.health_check()


cache_service = CacheService()


__all__ = [
    "CacheService", "cache_service",
    "ProfileChatCache", "profile_chat_cache",
    "BIZ_PROFILE", "BIZ_RESOURCE", "BIZ_PLAN",
    "STAGE_BASE_INFO", "STAGE_ACADEMIC", "STAGE_DIMENSION", "STAGE_COMPLETED",
    "STANDARD_DIMS", "EXTRA_DIM",
    "REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD",
]
