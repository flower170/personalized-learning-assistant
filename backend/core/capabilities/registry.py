"""
A3 能力注册表 — Level 2 多阶段能力管道注册与管理

参考 DeepTutor 设计：
- 每个 Capability 是一个多阶段管道
- 使用 BaseCapability 适配器模式包装原有 Agent
- 提供独立的注册表管理
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional, Protocol

from core.protocol import AgentState, CapabilityManifest

logger = logging.getLogger(__name__)


# ======================== 能力协议 ========================

class CapabilityContext:
    """能力执行上下文 — 供能力管道内部使用"""
    def __init__(self, state: AgentState, **kwargs):
        self.state = state
        self.kwargs = kwargs
        self._storage: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.kwargs.get(key, self.state.get(key, default))

    def set(self, key: str, value: Any):
        self._storage[key] = value

    @property
    def user_id(self) -> str:
        return self.state.get("user_id", "")

    @property
    def session_id(self) -> str:
        return self.state.get("session_id", "")

    @property
    def message(self) -> str:
        return self.state.get("user_message", "")


class BaseCapability(Protocol):
    """能力基类协议 — 所有 Capability 须实现此接口"""
    name: str
    description: str
    manifest: CapabilityManifest

    async def execute(
        self,
        state: AgentState,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行能力管道，产出 SSE 事件流"""
        ...
        yield {"event": "complete"}


# ======================== 能力注册表 ========================

class CapabilityRegistry:
    """能力注册表 — 管理所有 Level 2 能力"""

    def __init__(self):
        self._capabilities: dict[str, BaseCapability] = {}
        self._manifests: dict[str, CapabilityManifest] = {}

    def register(self, capability: BaseCapability):
        """注册能力实例"""
        name = capability.name
        self._capabilities[name] = capability
        self._manifests[name] = capability.manifest
        logger.info(f"[CapabilityRegistry] 注册能力: {name} — {capability.description}")

    def get(self, name: str) -> Optional[BaseCapability]:
        """获取能力实例"""
        return self._capabilities.get(name)

    def get_manifest(self, name: str) -> Optional[CapabilityManifest]:
        """获取能力清单"""
        return self._manifests.get(name)

    def list_capabilities(self) -> list[CapabilityManifest]:
        """列出所有能力清单"""
        return list(self._manifests.values())

    def has(self, name: str) -> bool:
        """检查能力是否存在"""
        return name in self._capabilities

    def list_names(self) -> list[str]:
        """列出所有能力名称"""
        return list(self._capabilities.keys())


# 全局能力注册表实例
capability_registry = CapabilityRegistry()


__all__ = [
    "CapabilityContext",
    "BaseCapability",
    "CapabilityRegistry",
    "capability_registry",
]
