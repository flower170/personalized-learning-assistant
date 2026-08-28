"""
MySQL 数据库模型 (SQLAlchemy)
存储画像、资源、路径数据
"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, String, Text, Integer, Float, DateTime, JSON, text
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# 加载 .env 文件（保证数据库凭据从环境变量读取，避免硬编码在仓库中）
import os
from pathlib import Path

_env_path = Path(__file__).parent.parent.parent / ".env"
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

DB_URL = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"

engine = None
SessionLocal = None
Base = declarative_base()


def init_db():
    """初始化数据库连接与表结构"""
    global engine, SessionLocal
    try:
        engine = create_engine(DB_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)
        logger.info("[Database] MySQL 连接成功")
        return True
    except Exception as e:
        logger.warning(f"[Database] MySQL 连接失败，使用文件存储降级: {e}")
        return False


def get_session():
    """获取数据库会话"""
    if SessionLocal is None:
        init_db()
    if SessionLocal:
        return SessionLocal()
    return None


# ======================== 数据表模型 ========================

class StudentProfileDB(Base):
    """学生画像表"""
    __tablename__ = "student_profiles"

    student_id = Column(String(64), primary_key=True)
    profile_json = Column(JSON, nullable=False, comment="完整画像 JSON")
    version = Column(Integer, default=1)
    name = Column(String(64), default="")
    grade = Column(String(32), default="")
    major = Column(String(64), default="")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class LearningResourceDB(Base):
    """学习资源表"""
    __tablename__ = "learning_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(64), index=True, nullable=False)
    resource_type = Column(String(32), nullable=False, comment="lecture/mindmap/exercise/reading/code")
    topic = Column(String(128), nullable=False, comment="知识点")
    course = Column(String(128), default="")
    content = Column(Text, nullable=False, comment="资源内容 Markdown")
    content_summary = Column(String(256), default="", comment="内容摘要")
    tags = Column(JSON, default=list, comment="标签列表")
    created_at = Column(DateTime, default=datetime.now)


class LearningPathDB(Base):
    """学习路径表"""
    __tablename__ = "learning_paths"

    student_id = Column(String(64), primary_key=True)
    path_json = Column(JSON, nullable=False, comment="完整路径 JSON")
    version = Column(Integer, default=1)
    topic = Column(String(128), default="")
    progress = Column(Float, default=0.0, comment="0~100 进度百分比")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ChatHistoryDB(Base):
    """对话历史表"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True, nullable=False)
    student_id = Column(String(64), index=True, nullable=False)
    role = Column(String(16), nullable=False, comment="user/assistant/system")
    content = Column(Text, nullable=False)
    intent = Column(String(32), default="", comment="profile/resource/plan")
    created_at = Column(DateTime, default=datetime.now)
