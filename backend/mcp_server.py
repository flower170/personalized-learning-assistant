"""
A3 本地工具 MCP Server（独立 stdio 进程）
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

import mcp.types
from mcp.server import Server
from mcp.server.stdio import stdio_server

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("a3_mcp_server")


async def main():
    from core.tools import tool_registry, list_tools  # noqa: F401
    tool_names = tool_registry.list_names()
    logger.info(f"已注册本地工具: {tool_names}")

    server = Server("a3-local-tools", version="2.0.0")

    @server.list_tools()
    async def handle_list_tools() -> list[mcp.types.Tool]:
        tools: list[mcp.types.Tool] = []
        for tdef in tool_registry.list_tools():
            input_schema = tdef.get("parameters") or {"type": "object", "properties": {}}
            tools.append(mcp.types.Tool(
                name=tdef["name"],
                description=tdef.get("description", ""),
                inputSchema=input_schema,
            ))
        return tools

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None):
        arguments = arguments or {}
        try:
            fn = tool_registry.get(name)
            if fn is None:
                raise KeyError(f"未知工具: {name}")
            logger.info(f"调用工具: {name}(args={list(arguments.keys())})")
            import inspect
            result = fn(**arguments)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, (dict, list)):
                text = json.dumps(result, ensure_ascii=False, default=str)
            elif result is None:
                text = "null"
            else:
                text = str(result)
            return [mcp.types.TextContent(type="text", text=text)]
        except Exception as e:
            logger.exception(f"工具执行失败 [{name}]: {e}")
            err = json.dumps({"error": type(e).__name__, "message": str(e)}, ensure_ascii=False)
            return [mcp.types.TextContent(type="text", text=err, isError=True)]

    async with stdio_server() as (read_stream, write_stream):
        logger.info("A3 本地工具 MCP Server 已启动（stdio）")
        await server.run(read_stream, write_stream, server.create_initialization_options())
        logger.info("A3 本地工具 MCP Server 已关闭")


if __name__ == "__main__":
    asyncio.run(main())
