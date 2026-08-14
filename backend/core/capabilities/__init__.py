"""
A3 能力层 — Level 2 多阶段管道

每个 Capability 使用适配器模式包装原有 Agent：
- ProfileCapability → ProfileChatAgent
- ResourceCapability → Resource Agents (Lecture/Mindmap/Exercise/Reading/Code)
- PlanCapability → PathPlanAgent
- TutorCapability → TutorAgent
"""
from core.capabilities.registry import (
    BaseCapability, CapabilityRegistry,
    CapabilityContext, capability_registry,
)
from core.capabilities.profile import ProfileCapability
from core.capabilities.resource import ResourceCapability
from core.capabilities.plan import PlanCapability
from core.capabilities.tutor import TutorCapability

# 自动注册所有能力
capability_registry.register(ProfileCapability())
capability_registry.register(ResourceCapability())
capability_registry.register(PlanCapability())
capability_registry.register(TutorCapability())

__all__ = [
    "BaseCapability", "CapabilityRegistry", "CapabilityContext",
    "capability_registry",
    "ProfileCapability", "ResourceCapability",
    "PlanCapability", "TutorCapability",
]
