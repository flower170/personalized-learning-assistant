"""
智能辅导答疑能力 — 多模态个性化学习辅导

适配器模式：包装 TutorAgent 为 BaseCapability
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

from core.protocol import AgentState, CapabilityManifest
from core.capabilities.registry import BaseCapability

logger = logging.getLogger(__name__)

MANIFEST = CapabilityManifest(
    name="tutor",
    description="基于学生画像的多模态智能辅导答疑",
    stages=["load_profile", "rag_retrieve", "generate_answer", "complete"],
    tools_used=["llm_chat_stream", "rag_retrieve", "profile_load", "mermaid_render"],
)


class TutorCapability(BaseCapability):
    """智能辅导答疑能力 — 适配 TutorAgent"""

    def __init__(self):
        self._name = "tutor"
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
        if self._agent is None:
            from core.capabilities.impl.tutor_agent import tutor_agent
            self._agent = tutor_agent
        return self._agent

    async def execute(
        self,
        state: AgentState,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行辅导答疑能力管道"""
        question = kwargs.get("question") or state.get("tutor_question") or state.get("user_message", "")
        student_id = kwargs.get("student_id") or state.get("user_id", "anonymous")
        conversation_history = kwargs.get("conversation_history") or state.get("tutor_history", [])
        language = kwargs.get("language", "") or state.get("language", "")

        if not question:
            yield {"event": "error", "message": "问题不能为空"}
            return

        yield {"event": "tutor_start", "stage": "load_profile",
               "data": "💡 正在分析你的问题..."}

        content_buffer = ""
        async for chunk in self.agent.answer(
            question=question,
            student_id=student_id,
            conversation_history=conversation_history,
            language=language,
        ):
            if chunk:
                content_buffer += chunk
                yield {"event": "tutor_chunk", "data": chunk}

        yield {"event": "tutor_complete", "stage": "complete", "data": "解答完成"}
