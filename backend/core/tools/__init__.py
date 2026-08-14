"""
A3 工具层 — Level 1 原子能力

工具列表：
1. llm_chat / llm_chat_stream — 大模型对话
2. simple_chat — 简化的单轮对话
3. rag_retrieve / rag_search — 知识库检索
4. duckduckgo_search / web_search — DuckDuckGo 联网搜索
5. profile_load / profile_save — 画像读写
6. content_check / content_filter — 内容安全
7. hallucination_check — 防幻觉
8. mermaid_render — Mermaid 渲染
9. extract_profile_from_text — 文本画像提取
"""
from core.tools.registry import (
    ToolRegistry, tool_registry,
    register_tool, get_tool, list_tools,
)

# 导入工具实现（触发 @register_tool 装饰器注册）
from core.tools import llm_tools
from core.tools import rag_tools
from core.tools import search_tools
from core.tools import profile_tools
from core.tools import safety_tools
from core.tools import media_tools

__all__ = [
    "ToolRegistry", "tool_registry",
    "register_tool", "get_tool", "list_tools",
]
