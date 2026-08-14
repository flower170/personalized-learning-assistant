"""
A3 核心协议层

参考 DeepTutor 架构设计：
- Level 1: Tools（单次调用的工具）
- Level 2: Capabilities（多阶段管道）

提供全局共享的类型定义，被 services/、capabilities、graph.py 统一引用。
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Callable, Literal, Optional, Protocol, Union

from typing_extensions import TypedDict, Annotated
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)

# ======================== 意图类型 ========================
IntentType = Literal["profile", "resource", "plan", "tutor", "chat", "unknown"]
BizMode = Literal["profile", "resource", "plan", "tutor", "chat", ""]

# ======================== 核心数据类型 ========================


class AgentState(TypedDict):
    """全局 LangGraph 共享状态

    包含所有子图（画像、资源、路径、辅导）的完整上下文，
    以 session_id 为隔离单元，Redis 做持久化。
    """
    # ---- 用户与会话 ----
    user_id: str
    user_message: str
    session_id: str
    explicit_type: str                      # 前端显式指定的类型
    language: str                           # 语言偏好（zh-CN, en-US, ja-JP 等）

    # ---- 业务模式隔离 ----
    current_biz_mode: BizMode
    biz_session_ids: dict[str, str]         # {"profile": "sid1", "resource": "sid2", ...}
    switch_requested: bool
    switch_confirmed: bool

    # ---- 意图识别 ----
    intent: IntentType
    confidence: float
    intent_reason: str

    # ---- 对话历史 ----
    messages: Annotated[list, add_messages]

    # ---- 混合对话记忆（摘要 + 最近 N 轮）----
    context_summary: str                 # 早期对话 LLM 摘要
    context_history: list[dict]          # 最近 N 轮逐字历史 [{role, content}, ...]

    # ---- 画像 ----
    profile_question: Optional[str]
    profile_reply: Optional[str]
    profile_completed: bool
    profile_data: Optional[dict]

    # ---- 资源生成 ----
    resource_topic: Optional[str]
    resource_course: Optional[str]
    resource_types: list[str]
    resource_user_demand: Optional[str]
    resource_results: dict[str, str]
    resource_image_urls: dict[str, str]     # 类型 → 图片URL (思维导图)
    resource_video_first: bool              # 视频推荐关键词标记
    resource_skip_sync: bool                # 同步模式跳过资源执行
    resource_clarification_msg: Optional[str]  # 资源类型不明确时的引导询问

    # ---- 路径规划 ----
    plan_topic: Optional[str]
    plan_goal: Optional[str]
    plan_total_days: int
    plan_daily_minutes: int
    plan_result: Optional[dict]

    # ---- 智能辅导 ----
    tutor_question: Optional[str]
    tutor_reply: Optional[str]
    tutor_history: list[dict]

    # ---- 流式输出缓冲 ----
    sse_buffer: list[str]

    # ---- 错误 ----
    error: Optional[str]


def create_initial_state(
    user_id: str,
    user_message: str,
    session_id: str = "",
    explicit_type: str = "",
    language: str = "",
    context_summary: str = "",
    context_history: Optional[list] = None,
) -> AgentState:
    """创建初始 AgentState"""
    intent: IntentType = (
        explicit_type
        if explicit_type in ("profile", "resource", "plan", "tutor")
        else "unknown"
    )
    return AgentState(
        user_id=user_id,
        user_message=user_message,
        session_id=session_id,
        explicit_type=explicit_type,
        language=language,
        current_biz_mode=intent if intent != "unknown" else "",
        biz_session_ids={},
        switch_requested=False,
        switch_confirmed=False,
        intent=intent,
        confidence=0.0 if not intent else 1.0,
        intent_reason="前端显式指定" if intent else "",
        messages=[],
        # 混合对话记忆
        context_summary=context_summary,
        context_history=list(context_history or []),
        # 画像
        profile_question=None,
        profile_reply=None,
        profile_completed=False,
        profile_data=None,
        # 资源
        resource_topic=None,
        resource_course="",
        resource_types=[],
        resource_user_demand="",
        resource_results={},
        resource_image_urls={},
        resource_clarification_msg=None,
        resource_skip_sync=False,
        resource_video_first=False,
        # 路径
        plan_topic=None,
        plan_goal="",
        plan_total_days=30,
        plan_daily_minutes=60,
        plan_result=None,
        # 辅导
        tutor_question=None,
        tutor_reply=None,
        tutor_history=[],
        # 通用
        sse_buffer=[],
        error=None,
    )


class ToolDefinition(TypedDict):
    """Level 1 工具定义 — 单次调用的原子能力"""
    name: str
    description: str
    parameters: dict[str, Any]


class CapabilityManifest(TypedDict):
    """Level 2 能力清单 — 多阶段管道"""
    name: str
    description: str
    stages: list[str]                       # 管道阶段名称列表
    tools_used: list[str]                   # 该能力使用的工具列表


# ======================== 工具/能力执行协议 ========================


class ToolFunc(Protocol):
    """Level 1 工具可调用协议"""
    async def __call__(self, **kwargs: Any) -> Any: ...


class Capability(Protocol):
    """Level 2 能力协议 — 每个能力是一个多阶段管道"""
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


# ======================== SSE 事件类型 ========================


class SSEEvent(TypedDict, total=False):
    """SSE 推送事件"""
    event: str                              # start / chunk / end / error / complete
    type: str                               # 资源类型 / 阶段名称
    data: str                               # 文本内容
    image_url: Optional[str]                # 图片URL（思维导图）
    raw_mermaid: Optional[str]              # 原始 Mermaid 代码
    message: str                            # 错误或提示消息


# ======================== 能力清单 ========================

# 注册所有可用能力
CAPABILITY_REGISTRY: dict[str, CapabilityManifest] = {}

def register_capability(manifest: CapabilityManifest):
    """注册能力到全局清单"""
    CAPABILITY_REGISTRY[manifest["name"]] = manifest
    logger.info(f"[能力注册] {manifest['name']}: {manifest['description']}")


__all__ = [
    "AgentState", "create_initial_state",
    "ToolDefinition", "CapabilityManifest", "Capability",
    "ToolFunc", "SSEEvent",
    "IntentType", "BizMode",
    "CAPABILITY_REGISTRY", "register_capability",
]
