"""
外部 MCP Server 注册配置（热插拔）

在此处添加外部 MCP Server 即可自动接入：
    SERVER_ID: {
        "transport": "sse" | "streamable_http",
        "url": "http://host:port/sse",
        # 可选 headers / auth
        "headers": {"Authorization": "Bearer xxx"}
    }

添加/修改后重启主后端即可生效。
"""
from __future__ import annotations

from typing import Any

EXTERNAL_MCP_SERVERS: dict[str, dict[str, Any]] = {
    # ====== 示例：接入一个 SSE 协议的外部 MCP Server ======
    # "example-filesystem": {
    #     "transport": "sse",
    #     "url": "http://127.0.0.1:8765/sse",
    #     "headers": {},
    # },

    # ====== 示例：接入一个 HTTP 协议的外部 MCP Server ======
    # "research-search": {
    #     "transport": "streamable_http",
    #     "url": "http://127.0.0.1:8766/mcp",
    # },
}


def register_external_server(server_id: str, config: dict[str, Any]):
    """运行时动态注册外部 MCP Server（需重新触发 _load_external_servers）"""
    EXTERNAL_MCP_SERVERS[server_id] = config


def unregister_external_server(server_id: str):
    """运行时动态注销外部 MCP Server"""
    EXTERNAL_MCP_SERVERS.pop(server_id, None)


__all__ = ["EXTERNAL_MCP_SERVERS", "register_external_server", "unregister_external_server"]
