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
    tool_names = [t["name"] for t in tool_registry.list_tools()]
    logger.info(f"已注册本地工具: {tool_names}")

    # SDK >= 1.0: 通过 Server 构造参数注册工具处理器（替代旧的 list_tools/call_tool 装饰器）
    async def handle_list_tools(ctx, params) -> mcp.types.ListToolsResult:
        tools: list[mcp.types.Tool] = []
        for tdef in tool_registry.list_tools():
            input_schema = tdef.get("parameters") or {"type": "object", "properties": {}}
            tools.append(mcp.types.Tool(
                name=tdef["name"],
                description=tdef.get("description", ""),
                input_schema=input_schema,
            ))
        return mcp.types.ListToolsResult(tools=tools)

    async def handle_call_tool(ctx, params: mcp.types.CallToolRequestParams) -> mcp.types.CallToolResult:
        name = params.name
        arguments = params.arguments or {}
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
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=text)]
            )
        except Exception as e:
            logger.exception(f"工具执行失败 [{name}]: {e}")
            err = json.dumps({"error": type(e).__name__, "message": str(e)}, ensure_ascii=False)
            return mcp.types.CallToolResult(
                content=[mcp.types.TextContent(type="text", text=err)],
                is_error=True,
            )

    server = Server(
        "a3-local-tools",
        version="2.0.0",
        on_list_tools=handle_list_tools,
        on_call_tool=handle_call_tool,
    )

    async with stdio_server() as (read_stream, write_stream):
        logger.info("A3 本地工具 MCP Server 已启动（stdio）")
        await server.run(read_stream, write_stream, server.create_initialization_options())
        logger.info("A3 本地工具 MCP Server 已关闭")


if __name__ == "__main__":
    asyncio.run(main())
