"""
DuckDuckGo 联网搜索工具 — Level 1 原子能力

使用 ddgs 库实现无需 API key 的搜索功能，返回结构化结果。
"""
from __future__ import annotations

import logging
from typing import Optional

from core.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="duckduckgo_search",
    description="使用 DuckDuckGo 进行联网搜索，获取最新信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询词"},
            "max_results": {"type": "integer", "description": "最大返回结果数，默认5"},
            "region": {"type": "string", "description": "搜索区域，如 zh-CN"},
        },
        "required": ["query"],
    },
)
async def duckduckgo_search(
    query: str,
    max_results: int = 5,
    region: str = "zh-CN",
) -> list[dict]:
    """
    使用 DuckDuckGo 搜索获取最新信息

    :param query: 搜索查询词
    :param max_results: 最大返回结果数
    :param region: 搜索区域
    :return: 搜索结果列表，每项包含 title, url, snippet
    """
    try:
        from ddgs import DDGS

        # 国内环境 Google 后端被墙，优先 Bing；失败再逐级降级
        region_ddgs = "cn-zh" if region in ("zh-CN", "zh-cn", "cn-zh", "cn") else region
        backends = ["bing", "duckduckgo", "google", "auto"]
        results: list[dict] = []

        with DDGS() as ddgs:
            for backend in backends:
                try:
                    for result in ddgs.text(query, max_results=max_results, region=region_ddgs, backend=backend):
                        results.append({
                            "title": result.get("title", ""),
                            "url": result.get("href", ""),
                            "snippet": result.get("body", ""),
                        })
                    if results:
                        break
                except Exception as e:
                    logger.warning(f"[DuckDuckGo搜索] backend={backend} 失败: {e}")
                    continue

        logger.info(f"[DuckDuckGo搜索] 查询 '{query}' → 获取 {len(results)} 条结果 (backend={backend if results else 'none'})")
        return results

    except ImportError:
        logger.error("[DuckDuckGo搜索] ddgs 库未安装，请执行 pip install ddgs>=9.9.1")
        return []
    except Exception as e:
        logger.error(f"[DuckDuckGo搜索] 失败: {e}")
        return []


@register_tool(
    name="web_search",
    description="通用网络搜索（封装 DuckDuckGo）",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询词"},
            "count": {"type": "integer", "description": "返回结果数"},
        },
        "required": ["query"],
    },
)
async def web_search(query: str, count: int = 5) -> list[dict]:
    """
    通用网络搜索接口

    :param query: 搜索查询词
    :param count: 返回结果数
    :return: 搜索结果列表
    """
    return await duckduckgo_search(query, max_results=count)


def format_search_results(results: list[dict]) -> str:
    """
    将搜索结果格式化为可读文本

    :param results: 搜索结果列表
    :return: 格式化后的文本
    """
    if not results:
        return "未找到相关搜索结果"

    formatted = "\n\n".join(
        f"【{i + 1}】{result['title']}\n链接: {result['url']}\n摘要: {result['snippet']}"
        for i, result in enumerate(results)
    )
    return formatted