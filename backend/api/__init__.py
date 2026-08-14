"""
A3 API 层 — FastAPI 路由 + WebSocket 端点
"""
from .main import app
from .routes import router

__all__ = ["app", "router"]