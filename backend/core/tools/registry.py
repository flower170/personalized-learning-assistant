"""
A3 工具注册表 — Level 1 原子能力注册与管理

改造点（MCP 集成）：
- 注册机制保留（装饰器注册） → 供 MCP Server 进程读取 tool_def 和本地 fn
- execute 接口改造：强制通过 MCP Client 调用（独立进程 stdio / 外部 SSE/HTTP）
- 模式切换：通过 A3_TOOL_MODE 环境变量控制
  - "mcp"   （主后端默认）：execute/list_tools 走 MCP Client
  - "local" （MCP Server 进程模式）：execute 直接调用本地 fn
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

from core.protocol import ToolDefinition

logger = logging.getLogger(__name__)


# 运行模式：主后端进程使用 "mcp"，MCP Server 进程使用 "local"
TOOL_MODE = os.environ.get("A3_TOOL_MODE", "mcp").lower()


class ToolRegistry:
    """工具注册表 — 管理所有 Level 1 工具"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._fns: dict[str, Callable] = {}
        self._mode: str = TOOL_MODE
        self._mcp_synced = False

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        """动态切换模式（mcp / local）"""
        if mode not in ("mcp", "local"):
            raise ValueError(f"未知模式: {mode}，必须是 'mcp' 或 'local'")
        self._mode = mode
        logger.info(f"[ToolRegistry] 模式切换为: {mode}")

    def register(
        self,
        name: str,
        description: str,
        parameters: Optional[dict] = None,
    ) -> Callable:
        """装饰器：注册工具（定义与函数都保存在本地，供 MCP Server 暴露）"""
        def decorator(func: Callable) -> Callable:
            tool_def = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters or {},
            )
            self._tools[name] = tool_def
            self._fns[name] = func
            logger.debug(f"[ToolRegistry] 注册工具: {name}")
            return func
        return decorator

    def get(self, name: str) -> Optional[Callable]:
        """获取本地工具函数（仅 MCP Server 进程使用）"""
        return self._fns.get(name)

    def get_def(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义（本地缓存，同步可用）"""
        return self._tools.get(name)

    # ==================== 模式感知：list_tools ====================

    def list_tools(self) -> list[ToolDefinition]:
        """
        列出所有工具定义
        - local 模式：返回本地注册的定义
        - mcp   模式：返回本地定义 + 从 MCP Client 汇总（同步优先返回本地缓存，
                    首次调用后后台异步补全外部工具）
        """
        if self._mode == "local":
            return list(self._tools.values())
        # mcp 模式：优先返回本地已注册定义（保证 Capability manifest 兼容性）
        base = list(self._tools.values())
        seen = {t["name"] for t in base}
        # 尝试从 MCP Client 单例读取已缓存的外部工具
        try:
            from core.mcp_client import _mcp_client_instance
            cli = _mcp_client_instance
            if cli is not None and cli._initialized:
                for tdef in cli._server_cached_tools or []:
                    if tdef.get("name") not in seen:
                        base.append(tdef)
                        seen.add(tdef["name"])
        except Exception:
            pass
        return base

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        if name in self._tools:
            return True
        if self._mode == "mcp":
            try:
                from core.mcp_client import _mcp_client_instance
                cli = _mcp_client_instance
                if cli is not None and cli._initialized:
                    return name in cli._tool_to_server
            except Exception:
                pass
        return False

    # ==================== 模式感知：execute ====================

    async def execute(self, name: str, **kwargs) -> Any:
        """
        执行工具（强制 async，与原代码兼容）
        - local 模式：直接调用本地 fn（自动 async/await）
        - mcp   模式：通过 MCP Client 路由到对应 Server 调用
        """
        if self._mode == "local":
            return await self._execute_local(name, **kwargs)
        # mcp 模式
        from core.mcp_client import get_mcp_client
        cli = get_mcp_client()
        await cli.ensure_initialized()
        return await cli.call_tool(name, **kwargs)

    async def _execute_local(self, name: str, **kwargs) -> Any:
        fn = self._fns.get(name)
        if not fn:
            raise KeyError(f"未知工具: {name}")
        import inspect
        result = fn(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result


# 全局工具注册表实例
tool_registry = ToolRegistry()


# ==================== 便捷别名 ====================

register_tool = tool_registry.register
get_tool = tool_registry.get
list_tools = tool_registry.list_tools


# 向后兼容：原来的 execute 是同步的，现在改造为 async execute_async 是主入口；
# 为了兼容已有同步调用场景，提供同步包装。
def execute_sync(name: str, **kwargs) -> Any:
    """同步执行工具（自动运行事件循环，仅兼容老代码；新代码统一使用 async execute）"""
    return asyncio.run(tool_registry.execute(name, **kwargs))


__all__ = [
    "ToolRegistry", "tool_registry",
    "register_tool", "get_tool", "list_tools",
    "execute_sync", "TOOL_MODE",
]
