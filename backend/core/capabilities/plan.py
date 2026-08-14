"""
学习路径规划能力 — 个性化分阶段学习路径生成

适配器模式：包装 PathPlanAgent 为 BaseCapability
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from core.protocol import AgentState, CapabilityManifest
from core.capabilities.registry import BaseCapability

logger = logging.getLogger(__name__)

MANIFEST = CapabilityManifest(
    name="plan",
    description="基于学生画像和时间约束，生成个性化分阶段学习路径",
    stages=["load_profile", "generate_plan", "split_tasks", "complete"],
    tools_used=["llm_chat", "profile_load"],
)


class PlanCapability(BaseCapability):
    """学习路径规划能力 — 适配 PathPlanAgent"""

    def __init__(self):
        self._name = "plan"
        self._description = MANIFEST["description"]
        self._manifest = MANIFEST
        self._plan_agent = None  # 懒加载

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    @property
    def plan_agent(self):
        if self._plan_agent is None:
            from core.capabilities.impl.path_plan_agent import path_plan_agent
            self._plan_agent = path_plan_agent
        return self._plan_agent

    async def execute(
        self,
        state: AgentState,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行路径规划能力管道"""
        topic = kwargs.get("topic") or state.get("plan_topic") or state.get("user_message", "")
        student_id = kwargs.get("student_id") or state.get("user_id", "anonymous")
        course = kwargs.get("course") or state.get("resource_course", "")
        goal = kwargs.get("goal") or state.get("plan_goal", "")
        total_days = kwargs.get("total_days") or state.get("plan_total_days", 30)
        daily_minutes = kwargs.get("daily_minutes") or state.get("plan_daily_minutes", 60)
        user_demand = kwargs.get("user_demand", "")

        yield {"event": "plan_start", "stage": "load_profile",
               "data": f"📋 正在为「{topic}」规划学习路径..."}

        try:
            path = await self.plan_agent.generate_plan(
                student_id=student_id, topic=topic, course=course,
                goal=goal, total_days=total_days, daily_minutes=daily_minutes,
                user_demand=user_demand,
            )
            stages = path.get("stages", [])
            nodes = path.get("nodes", [])

            yield {"event": "plan_complete", "stage": "complete",
                   "data": f"✅ 已规划 {len(stages)} 个学习阶段，共 {total_days} 天",
                   "plan": path, "stages": stages, "nodes": nodes}
        except Exception as e:
            logger.exception(f"[PlanCapability] 规划异常")
            yield {"event": "error", "message": f"规划失败: {str(e)[:100]}"}

    async def generate_plan(self, **kwargs) -> dict:
        """直接调用路径规划（非流式，供 API 层使用）"""
        return await self.plan_agent.generate_plan(**kwargs)
