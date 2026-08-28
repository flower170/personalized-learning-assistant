"""
统一数据库服务层

封装 SQLAlchemy 异步 MySQL 操作，支持连接池、会话管理。
降级策略：MySQL 不可用时自动降级到文件存储。
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# 加载 .env 文件（保证数据库凭据从环境变量读取，避免硬编码在仓库中）
import os
from pathlib import Path

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
    except Exception:
        pass

# MySQL 配置（从环境变量读取，默认本机开发值）
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "a3_learning"),
}

ASYNC_DB_URL = (
    f"mysql+aiomysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"
)
SYNC_DB_URL = (
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"
)


class DatabaseService:
    """统一数据库服务

    特性：
    - 异步 SQLAlchemy 引擎 + 连接池
    - 自动重连
    - MySQL 不可用时降级日志
    """

    def __init__(self):
        self._engine = None
        self._async_session_maker: Optional[async_sessionmaker] = None
        self._available = False
        self._init()

    def _init(self):
        """初始化数据库连接（失败不阻断）"""
        try:
            # 先尝试同步初始化检查连接
            from sqlalchemy import create_engine
            sync_engine = create_engine(SYNC_DB_URL, pool_size=2, max_overflow=5, pool_pre_ping=True)
            sync_engine.connect().close()
            sync_engine.dispose()

            # 创建异步引擎
            self._engine = create_async_engine(
                ASYNC_DB_URL,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False,
            )
            self._async_session_maker = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            self._available = True
            logger.info("[DatabaseService] MySQL 异步连接成功")
        except Exception as e:
            self._available = False
            logger.warning(f"[DatabaseService] MySQL 不可用，降级到文件存储: {e}")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[Optional[AsyncSession], None]:
        """获取异步数据库会话"""
        if not self._available or not self._async_session_maker:
            logger.warning("[DatabaseService] 数据库不可用，返回 None")
            yield None
            return
        session = self._async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"[DatabaseService] 会话异常: {e}")
            raise
        finally:
            await session.close()

    async def execute(self, statement: Any, params: Optional[dict] = None) -> Any:
        """执行原生 SQL"""
        async with self.get_session() as session:
            if session is None:
                return None
            result = await session.execute(statement, params or {})
            return result

    async def fetch_one(self, sql: str, params: Optional[dict] = None) -> Optional[dict]:
        """查询单条记录"""
        async with self.get_session() as session:
            if session is None:
                return None
            result = await session.execute(text(sql), params or {})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None

    async def fetch_all(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        """查询多条记录"""
        async with self.get_session() as session:
            if session is None:
                return []
            result = await session.execute(text(sql), params or {})
            rows = result.fetchall()
            return [dict(row._mapping) for row in rows]

    async def save_profile(self, student_id: str, profile_data: dict) -> bool:
        """保存学生画像"""
        sql = """
            INSERT INTO student_profiles (student_id, profile_json, version, name, grade, major, updated_at)
            VALUES (:sid, :data, :ver, :name, :grade, :major, NOW())
            ON DUPLICATE KEY UPDATE
                profile_json = VALUES(profile_json),
                version = version + 1,
                name = VALUES(name),
                grade = VALUES(grade),
                major = VALUES(major),
                updated_at = NOW()
        """
        try:
            await self.execute(
                text(sql),
                {
                    "sid": student_id,
                    "data": json.dumps(profile_data, ensure_ascii=False),
                    "ver": profile_data.get("version", 1),
                    "name": profile_data.get("name", ""),
                    "grade": profile_data.get("grade", ""),
                    "major": profile_data.get("major", ""),
                },
            )
            return True
        except Exception as e:
            logger.error(f"[DatabaseService] 保存画像失败: {e}")
            return False

    async def load_profile(self, student_id: str) -> Optional[dict]:
        """加载学生画像"""
        return await self.fetch_one(
            "SELECT profile_json, version, name, grade, major, updated_at FROM student_profiles WHERE student_id = :sid",
            {"sid": student_id},
        )

    async def save_resource(
        self,
        student_id: str,
        resource_type: str,
        topic: str,
        content: str,
        course: str = "",
    ) -> Optional[int]:
        """保存学习资源"""
        sql = """
            INSERT INTO learning_resources (student_id, resource_type, topic, course, content, created_at)
            VALUES (:sid, :type, :topic, :course, :content, NOW())
        """
        try:
            result = await self.execute(
                text(sql),
                {
                    "sid": student_id,
                    "type": resource_type,
                    "topic": topic,
                    "course": course,
                    "content": content,
                },
            )
            if result:
                return result.lastrowid
            return None
        except Exception as e:
            logger.error(f"[DatabaseService] 保存资源失败: {e}")
            return None

    async def save_chat_history(
        self,
        session_id: str,
        student_id: str,
        role: str,
        content: str,
        intent: str = "",
    ) -> bool:
        """保存对话历史"""
        sql = """
            INSERT INTO chat_history (session_id, student_id, role, content, intent, created_at)
            VALUES (:sid, :uid, :role, :content, :intent, NOW())
        """
        try:
            await self.execute(
                text(sql),
                {
                    "sid": session_id,
                    "uid": student_id,
                    "role": role,
                    "content": content,
                    "intent": intent,
                },
            )
            return True
        except Exception as e:
            logger.error(f"[DatabaseService] 保存对话历史失败: {e}")
            return False

    @property
    def is_available(self) -> bool:
        return self._available


# 全局数据库服务实例
database_service = DatabaseService()
