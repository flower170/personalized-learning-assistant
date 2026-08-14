"""
A3 服务层 — 统一外部服务接口

所有服务自包含实现，不依赖 app/ 旧代码。
"""
from services.llm import LLMService, llm_service
from services.cache import (
    CacheService, cache_service,
    ProfileChatCache, profile_chat_cache,
    BIZ_PROFILE, BIZ_RESOURCE, BIZ_PLAN,
    STAGE_BASE_INFO, STAGE_ACADEMIC, STAGE_DIMENSION, STAGE_COMPLETED,
    STANDARD_DIMS,
)
from services.database import DatabaseService, database_service
from services.rag import RAGService, rag_service, SparkKnowledgeBase, kb_client
from services.context_memory import ContextMemory, context_memory, ContextPayload

__all__ = [
    "LLMService", "llm_service",
    "CacheService", "cache_service",
    "ProfileChatCache", "profile_chat_cache",
    "BIZ_PROFILE", "BIZ_RESOURCE", "BIZ_PLAN",
    "STAGE_BASE_INFO", "STAGE_ACADEMIC", "STAGE_DIMENSION", "STAGE_COMPLETED",
    "STANDARD_DIMS",
    "DatabaseService", "database_service",
    "RAGService", "rag_service",
    "SparkKnowledgeBase", "kb_client",
    "ContextMemory", "context_memory", "ContextPayload",
]
