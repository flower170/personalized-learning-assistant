"""
A3 核心引擎 — 协议层 + 工具层 + 能力层 + LangGraph 编排
"""
from core.protocol import (
    AgentState, create_initial_state,
    ToolDefinition, CapabilityManifest,
    IntentType, BizMode,
    CAPABILITY_REGISTRY, register_capability,
)
from core.tools import (
    tool_registry, register_tool, get_tool, list_tools,
)
from core.capabilities import (
    capability_registry,
    ProfileCapability, ResourceCapability,
    PlanCapability, TutorCapability,
)

# 获取能力的便捷函数
def get_capability(name: str):
    return capability_registry.get(name)

__all__ = [
    # 协议
    "AgentState", "create_initial_state",
    "ToolDefinition", "CapabilityManifest",
    "IntentType", "BizMode",
    "CAPABILITY_REGISTRY", "register_capability",
    # 工具
    "tool_registry", "register_tool", "get_tool", "list_tools",
    # 能力
    "capability_registry", "get_capability",
    "ProfileCapability", "ResourceCapability",
    "PlanCapability", "TutorCapability",
]
