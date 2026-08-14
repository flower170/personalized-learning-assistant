"""
A3 FastAPI 应用主入口

包含：
- WebSocket 端点（流式交互）
- CORS 配置
- 生命周期管理
- 静态文件托管

参考 DeepTutor 架构：
- WebSocket /ws/{session_id} 支持 LangGraph 编排
- REST API 通过 api/routes.py 注册
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from api.routes import router as api_router
from api.online_routes import router as online_router
from api.onboarding_routes import router as onboarding_router
from core.graph import run_orchestrator
from services.cache import cache_service
from core.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


# ======================== 生命周期 ========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("🚀 A3 多智能体学习系统启动中...")

    # 检查 LLM 配置
    if not settings.is_configured:
        logger.warning("⚠️ API 密钥未配置！请在 .env 文件中配置 SPARK_APP_ID / SPARK_API_KEY / SPARK_API_SECRET")
    else:
        logger.info(f"✅ 已配置 {len(settings.list_models())} 个模型: {settings.list_models()}")

    # 初始化能力层（导入即触发注册）
    import core.capabilities  # noqa: F401

    # 初始化数据库（失败不阻断）
    try:
        from core.models.database import init_db
        init_db()
    except Exception as e:
        logger.warning(f"MySQL 初始化跳过: {e}")

    # 检查缓存服务
    cache_health = cache_service.health_check()
    logger.info(f"📦 缓存服务: {'Redis' if not cache_health.get('fallback_mode') else '内存降级'} | "
                f"会话数: {cache_health.get('memory_sessions', 0)}")

    logger.info("✅ 所有能力已就绪")
    logger.info("🎯 A3 系统启动完成")
    yield

    # 清理
    from services.rag import kb_client
    await kb_client.close()
    logger.info("👋 A3 系统已关闭")


# ======================== FastAPI 应用 ========================

app = FastAPI(
    title="A3 多智能体学习系统",
    description="基于 LangGraph + 大模型的个性化学习工作区",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
_static_dir = Path(__file__).parent.parent / "static"
_static_dir.mkdir(parents=True, exist_ok=True)
(_static_dir / "mindmap").mkdir(parents=True, exist_ok=True)
(_static_dir / "uploads").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# 注册 REST 路由
app.include_router(api_router)
app.include_router(online_router)
app.include_router(onboarding_router)


# ======================== WebSocket 端点 ========================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 流式交互端点

    支持 LangGraph 编排的完整能力：
    - profile: 画像构建
    - resource: 资源生成
    - plan: 路径规划
    - tutor: 智能辅导

    消息格式 (JSON):
        {"message": "...", "student_id": "...", "explicit_type": "..."}

    响应格式 (JSON 流):
        {"event": "...", "data": "...", ...}
    """
    await websocket.accept()
    logger.info(f"[WS] 新连接: session_id={session_id}")

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"message": raw}

            message = data.get("message", raw if isinstance(raw, str) else "")
            student_id = data.get("student_id", session_id)
            explicit_type = data.get("explicit_type", "")

            # 通过 LangGraph 编排执行
            from core.graph import run_orchestrator as run_graph
            result = await run_graph(
                user_id=student_id,
                message=message,
                session_id=session_id,
                explicit_type=explicit_type,
            )

            # 构建响应
            intent = result.get("intent", "unknown")
            reply = ""

            if result.get("profile_reply"):
                reply = result["profile_reply"]
            elif result.get("resource_results"):
                types = list(result["resource_results"].keys())
                reply = f"✅ 已生成 {len(types)} 类资源: {', '.join(types)}"
            elif result.get("plan_result"):
                stages = result["plan_result"].get("stages", [])
                reply = f"✅ 已规划 {len(stages)} 个学习阶段"
            elif result.get("tutor_reply"):
                reply = result["tutor_reply"]
            else:
                sse = result.get("sse_buffer", [])
                reply = sse[-1] if sse else "好的"

            await websocket.send_json({
                "reply": reply,
                "intent": intent,
                "session_id": result.get("session_id", session_id),
                "is_completed": result.get("profile_completed", False),
            })

    except WebSocketDisconnect:
        logger.info(f"[WS] 断开连接: session_id={session_id}")
    except Exception as e:
        logger.exception(f"[WS] 异常: {e}")
        try:
            await websocket.send_json({"error": str(e)[:200]})
        except Exception:
            pass


# ======================== 健康检查 ========================

@app.get("/")
async def root():
    from core import capability_registry
    names = capability_registry.list_names()
    return {
        "service": "A3 多智能体学习系统",
        "version": "2.0.0",
        "status": "running",
        "models": settings.list_models(),
        "capabilities": names or ["profile", "resource", "plan", "tutor"],
    }


@app.get("/health")
async def health():
    # 知识库服务健康检查（仅 spark 后端，已移除 Chroma/FAISS 空壳）
    _kb_health = {"backend": "spark（讯飞知识库 + 本地关键词降级）", "local_keyword_fallback": "enabled"}
    try:
        from services.rag import rag_service as _rag_svc
        _kb_health = await _rag_svc.health_check()
    except Exception as _e:
        _kb_health["error"] = str(_e)[:100]
    return {
        "status": "healthy",
        "api_configured": settings.is_configured,
        "models_available": len(settings.list_models()),
        "cache": cache_service.health_check(),
        "kb": _kb_health,
    }


# ======================== 直接启动 ========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
