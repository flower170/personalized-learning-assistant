"""
A3 MCP Client 适配层 — 统一调度 stdio / SSE / HTTP 多通道

对外单一接口：
    mcp_client.call_tool(name, **kwargs) -> Any
    mcp_client.list_tools() -> list[ToolDefinition]

支持：
1. 内置本地工具 MCP Server（stdio，自动拉起子进程）
2. 外部 MCP Server（SSE/HTTP，通过 config 注册）
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from core.protocol import ToolDefinition

logger = logging.getLogger(__name__)


class McpToolClient:
    """MCP 多通道工具客户端"""

    def __init__(self, backend_root: Optional[Path] = None):
        self._backend_root = backend_root or Path(__file__).resolve().parent.parent
        self._python_exe = self._backend_root / ".venv" / "Scripts" / "python.exe"
        self._server_script = self._backend_root / "mcp_server.py"
        # 运行时状态
        self._lock = asyncio.Lock()
        self._server_ctxs: dict[str, Any] = {}  # server_id -> 传输上下文管理器 (stdio/sse/http)
        self._tool_to_server: dict[str, str] = {}  # tool_name -> server_id
        self._server_sessions: dict[str, Any] = {}  # server_id -> ClientSession
        self._initialized = False

    # ==================== 初始化 ====================

    async def ensure_initialized(self):
        """懒加载初始化：启动本地 stdio MCP Server + 加载外部 MCP 配置"""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            # 1. 启动本地 stdio MCP Server
            await self._start_local_stdio()
            # 2. 注册外部 MCP Servers
            await self._load_external_servers()
            self._initialized = True
            logger.info(f"MCP Client 初始化完成，已发现工具: {list(self._tool_to_server.keys())}")

    async def _start_local_stdio(self):
        """拉起本地工具 MCP Server 子进程并建立会话"""
        try:
            from mcp.client.stdio import stdio_client, StdioServerParameters
            from mcp import ClientSession

            params = StdioServerParameters(
                command=str(self._python_exe),
                args=[str(self._server_script)],
                cwd=str(self._backend_root),
            )
            ctx = stdio_client(params)
            # SDK >= 1.0 返回 _AsyncGeneratorContextManager，用 __aenter__ 取流
            read, write = await ctx.__aenter__()
            self._server_ctxs["local"] = ctx
            session = ClientSession(read, write)
            await session.__aenter__()  # SDK >= 1.0: 需先进入会话启动 dispatcher
            self._server_sessions["local"] = session
            await session.initialize()
            await self._index_session_tools("local", session)
            logger.info(f"本地 stdio MCP Server 会话已建立，工具数: {len([k for k,v in self._tool_to_server.items() if v=='local'])}")
        except Exception as e:
            logger.exception(f"启动本地 stdio MCP Server 失败: {e}")
            raise

    async def _load_external_servers(self):
        """从 core/mcp_config.py 读取外部 MCP Server 配置并建立会话"""
        try:
            from core.mcp_config import EXTERNAL_MCP_SERVERS
        except ImportError:
            EXTERNAL_MCP_SERVERS = {}
        for sid, cfg in EXTERNAL_MCP_SERVERS.items():
            try:
                session = await self._connect_external(sid, cfg)
                if session is not None:
                    await self._index_session_tools(sid, session)
                    self._server_sessions[sid] = session
                    logger.info(f"外部 MCP Server [{sid}] 连接成功")
            except Exception as e:
                logger.warning(f"外部 MCP Server [{sid}] 连接跳过: {e}")

    async def _connect_external(self, sid: str, cfg: dict):
        """连接外部 MCP Server（支持 sse / streamable_http）"""
        transport = cfg.get("transport", "sse").lower()
        url = cfg.get("url")
        if not url:
            return None
        from mcp import ClientSession
        if transport == "sse":
            from mcp.client.sse import sse_client
            ctx = sse_client(url)
            read, write = await ctx.__aenter__()
        elif transport in ("http", "streamable_http"):
            from mcp.client.streamable_http import streamable_http_client
            ctx = streamable_http_client(url)
            read, write = await ctx.__aenter__()
        else:
            raise ValueError(f"未知 transport: {transport}")
        self._server_ctxs[sid] = ctx
        session = ClientSession(read, write)
        await session.__aenter__()  # SDK >= 1.0: 需先进入会话启动 dispatcher
        self._server_sessions[sid] = session
        await session.initialize()
        return session

    async def _index_session_tools(self, server_id: str, session):
        """从会话列出工具并建立 tool_name -> server_id 索引"""
        from mcp.types import ListToolsResult
        result = await session.list_tools()
        tools = getattr(result, "tools", []) or []
        for t in tools:
            name = getattr(t, "name", None)
            if name:
                self._tool_to_server[name] = server_id

    # ==================== 对外 API ====================

    async def list_tools(self) -> list[ToolDefinition]:
        """列出所有可用工具（本地+外部）"""
        await self.ensure_initialized()
        result: list[ToolDefinition] = []
        seen: set[str] = set()
        for sid, session in self._server_sessions.items():
            try:
                lr = await session.list_tools()
                for t in getattr(lr, "tools", []) or []:
                    name = getattr(t, "name", "")
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    schema = getattr(t, "inputSchema", None) or {}
                    result.append(ToolDefinition(
                        name=name,
                        description=getattr(t, "description", "") or "",
                        parameters=schema,
                    ))
            except Exception as e:
                logger.warning(f"[{sid}] list_tools 失败: {e}")
        return result

    async def call_tool(self, name: str, **kwargs) -> Any:
        """调用工具，自动路由到对应的 MCP Server"""
        await self.ensure_initialized()
        server_id = self._tool_to_server.get(name)
        if server_id is None:
            # 尝试重新索引一次（可能是新注册的外部 Server）
            await self._reload_all_tools()
            server_id = self._tool_to_server.get(name)
            if server_id is None:
                raise KeyError(f"[MCP] 未找到工具: {name}. 可用: {sorted(self._tool_to_server.keys())}")
        session = self._server_sessions.get(server_id)
        if session is None:
            raise RuntimeError(f"[MCP] Server [{server_id}] 无可用会话")
        raw = await session.call_tool(name, arguments=kwargs)
        return self._parse_result(raw, name)

    async def _reload_all_tools(self):
        self._tool_to_server.clear()
        for sid, session in self._server_sessions.items():
            await self._index_session_tools(sid, session)

    @staticmethod
    def _parse_result(raw: Any, tool_name: str) -> Any:
        """将 MCP CallToolResult（TextContent[] / JSON）解析为 Python 对象"""
        try:
            content = getattr(raw, "content", None) or []
            if not content:
                return None
            # SDK >= 1.0: 错误标志在 CallToolResult 顶层 is_error
            is_err = bool(getattr(raw, "is_error", False))
            # 拼接所有 text 片段
            texts: list[str] = []
            for c in content:
                ctype = getattr(c, "type", "")
                if ctype == "text":
                    t = getattr(c, "text", "")
                    texts.append(t)
            combined = "\n".join(texts).strip()
            if is_err and combined:
                logger.warning(f"[MCP][{tool_name}] 返回错误: {combined[:200]}")
            if not combined:
                return None
            # 尝试 JSON 解析
            try:
                return json.loads(combined)
            except (json.JSONDecodeError, ValueError):
                return combined
        except Exception as e:
            logger.exception(f"[MCP][{tool_name}] 解析结果失败: {e}")
            return raw

    # ==================== 生命周期 ====================

    async def close(self):
        """关闭所有会话和子进程"""
        for sid, session in list(self._server_sessions.items()):
            try:
                await session.__aexit__(None, None, None)  # SDK >= 1.0: 退出会话停掉 dispatcher
            except Exception:
                pass
        self._server_sessions.clear()
        self._tool_to_server.clear()
        # 退出所有传输上下文管理器（stdio / sse / http），释放子进程与连接
        for sid, ctx in list(self._server_ctxs.items()):
            try:
                await ctx.__aexit__(None, None, None)
            except Exception:
                pass
        self._server_ctxs.clear()
        self._initialized = False
        logger.info("MCP Client 已关闭")


# 全局单例
_mcp_client_instance: Optional[McpToolClient] = None


def get_mcp_client() -> McpToolClient:
    global _mcp_client_instance
    if _mcp_client_instance is None:
        _mcp_client_instance = McpToolClient()
    return _mcp_client_instance


__all__ = ["McpToolClient", "get_mcp_client"]
