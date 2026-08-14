"""
画像构建能力 — 对话式采集 ≥6 维度学生画像

适配器模式：包装 ProfileChatAgent 为 BaseCapability
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional

from core.protocol import AgentState, CapabilityManifest
from core.capabilities.registry import BaseCapability

logger = logging.getLogger(__name__)

# 注册清单
MANIFEST = CapabilityManifest(
    name="profile",
    description="通过自然语言对话逐步采集学生信息，构建≥6维度动态画像",
    stages=["init_session", "collect_info", "extract_profile", "complete"],
    tools_used=["llm_chat", "simple_chat", "profile_load", "profile_save", "extract_profile_from_text"],
)


class ProfileCapability(BaseCapability):
    """画像构建能力 — 适配 ProfileChatAgent"""

    def __init__(self):
        self._name = "profile"
        self._description = MANIFEST["description"]
        self._manifest = MANIFEST
        self._agent = None  # 懒加载

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
    def agent(self):
        """懒加载 Agent 实例"""
        if self._agent is None:
            from core.capabilities.impl.profile_chat_agent import profile_chat_agent
            self._agent = profile_chat_agent
        return self._agent

    async def execute(
        self,
        state: AgentState,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行画像构建能力管道"""
        action = kwargs.get("action", "chat")
        student_id = kwargs.get("student_id") or state.get("user_id", "")
        session_id = kwargs.get("session_id") or state.get("session_id", "")
        message = kwargs.get("message") or state.get("user_message", "")

        if action == "init" or not session_id:
            yield {"event": "profile_init", "stage": "init_session"}
            sid, first_q = await self.agent.init_chat(
                student_id=student_id,
                name=kwargs.get("name", ""),
                grade=kwargs.get("grade", ""),
                major=kwargs.get("major", ""),
            )
            yield {"event": "profile_question", "stage": "collect_info",
                   "session_id": sid, "data": first_q}
            return

        reply, is_completed, profile, radar = await self.agent.chat(
            student_id=student_id, session_id=session_id, user_message=message,
        )

        if is_completed:
            yield {"event": "profile_complete", "stage": "complete", "data": reply,
                   "profile": profile.model_dump() if profile else None,
                   "radar_scores": radar.model_dump() if radar else None}
        else:
            yield {"event": "profile_question", "stage": "collect_info", "data": reply}

    # ---- 便捷方法（供 API 层直接调用）----

    async def init_chat(self, student_id: str, name: str = "",
                        grade: str = "", major: str = "", language: str = "") -> tuple[str, str]:
        return await self.agent.init_chat(student_id, name, grade, major, language)

    async def chat(self, student_id: str, session_id: str, message: str, language: str = "") -> tuple:
        return await self.agent.chat(student_id, session_id, message, language)

    def get_progress(self, student_id: str, session_id: str):
        return self.agent.get_progress(student_id, session_id)

    def reset_session(self, student_id: str):
        self.agent.reset_session(student_id)
