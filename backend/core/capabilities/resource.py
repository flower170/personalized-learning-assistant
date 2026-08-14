"""
多智能体资源生成能力 — 5类个性化学习资源协同生成

适配器模式：包装 Lecture/Mindmap/Exercise/Reading/Code Agents 为 BaseCapability
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Optional

import httpx

from core.protocol import AgentState, CapabilityManifest
from core.capabilities.registry import BaseCapability
from core.tools import get_tool

logger = logging.getLogger(__name__)

MANIFEST = CapabilityManifest(
    name="resource",
    description="多智能体协同生成6类个性化学习资源（讲解/导图/练习/阅读/代码/视频）",
    stages=["analyze_profile", "rag_retrieve", "generate_resource", "post_process", "complete"],
    tools_used=["llm_chat_stream", "rag_retrieve", "profile_load", "mermaid_render",
                "content_check", "hallucination_check"],
)

RESOURCE_TYPES = ["lecture", "mindmap", "exercise", "reading", "code", "video"]
RESOURCE_LABELS = {
    "lecture": "课程讲解文档", "mindmap": "知识点思维导图",
    "exercise": "练习题目", "reading": "拓展阅读材料", "code": "代码实操案例",
    "video": "视频教程推荐",
}


class ResourceCapability(BaseCapability):
    """多智能体资源生成能力 — 适配 5 个 Resource Agents"""

    def __init__(self):
        self._name = "resource"
        self._description = MANIFEST["description"]
        self._manifest = MANIFEST
        self._agents = None  # 懒加载
        self._profile_cache: dict[str, str] = {}

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
    def agents(self) -> dict:
        """懒加载所有资源 Agent"""
        if self._agents is None:
            from core.capabilities.impl.resource_agents import (
                lecture_agent, mindmap_agent,
                exercise_agent, reading_agent, code_agent, video_agent,
            )
            self._agents = {
                "lecture": lecture_agent, "mindmap": mindmap_agent,
                "exercise": exercise_agent, "reading": reading_agent,
                "code": code_agent, "video": video_agent,
            }
        return self._agents

    async def _generate_videos_fast(
        self, topic: str, course: str, student_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """视频快速通道：直接搜索 Bilibili API → 自带封面，不走 LLM"""
        import asyncio as _asyncio

        yield {"type": "video", "event": "start", "stage": "generate_resource",
               "data": f"🔍 正在 Bilibili 搜索「{topic}」相关视频..."}

        # 1. 直接调用 Bilibili 搜索 API
        video_results = []
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
                resp = await client.get(
                    "https://api.bilibili.com/x/web-interface/search/type",
                    params={
                        "search_type": "video",
                        "keyword": topic,
                        "page": 1,
                    },
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://www.bilibili.com/",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0:
                        for item in data.get("data", {}).get("result", [])[:8]:
                            video_results.append({
                                "title": item.get("title", "").replace('<em class="keyword">', '').replace('</em>', ''),
                                "bvid": item.get("bvid", ""),
                                "url": f"https://www.bilibili.com/video/{item.get('bvid', '')}",
                                "cover": item.get("pic", ""),
                                "duration": item.get("duration", ""),
                                "play": item.get("play", 0),
                                "description": (item.get("description", "") or "")[:80],
                                "author": item.get("author", ""),
                            })
        except Exception as e:
            logger.warning(f"[视频快速通道] Bilibili 搜索失败: {e}")

        if not video_results:
            yield {"type": "video", "event": "end", "stage": "post_process",
                   "content": "## 🎬 视频教程推荐\n\n暂无搜索结果，请尝试其他关键词。",
                   "video_covers": {}}
            return

        # 确保双数
        target = len(video_results)
        if target > 6:
            target = 6
        elif target > 4:
            target = 4
        elif target > 2:
            target = 2
        video_results = video_results[:target]

        # 2. 构建输出：直接用 Bilibili 返回的封面
        content = "## 🎬 视频教程推荐\n\n"
        covers = {}
        for i, vr in enumerate(video_results, 1):
            title = vr["title"][:50]
            url = vr["url"]
            desc = vr["description"] or "Bilibili 热门教程视频"
            duration = vr["duration"] or "详见视频页"
            author = vr["author"]

            content += "---\n"
            content += f"### {i}. [{title}]({url})\n"
            content += f"- **平台**: Bilibili\n"
            content += f"- **链接**: {url}\n"
            if author:
                content += f"- **作者**: {author}\n"
            content += f"- **时长**: {duration}\n"
            content += f"- **推荐理由**: {desc}\n"
            content += f"- **搜索关键词**: {topic}\n"
            content += "\n"

            # 封面直接用 Bilibili 返回的高清图
            if vr["cover"]:
                cover_url = vr["cover"] + "@672w_378h_1c"
                covers[url] = cover_url

        # 3. 流式输出内容
        chunk_size = max(1, len(content) // 8)
        for i in range(0, len(content), chunk_size):
            yield {"type": "video", "event": "chunk",
                   "data": content[i:i + chunk_size]}
            await _asyncio.sleep(0.03)

        # 4. 终点事件（含封面映射）
        yield {"type": "video", "event": "end", "stage": "post_process",
               "content": content, "video_covers": covers}

    def _load_profile_context(self, student_id: str) -> str:
        """加载画像上下文"""
        if student_id in self._profile_cache:
            return self._profile_cache[student_id]
        from core.models.profile import profile_manager
        try:
            profile = profile_manager.get_profile(student_id)
            parts = []
            kb = profile.knowledge_base or {}
            if kb.get("mastered"): parts.append(f"已掌握: {', '.join(kb['mastered'][:5])}")
            if kb.get("weak"): parts.append(f"薄弱: {', '.join(kb['weak'][:3])}")
            if profile.interests: parts.append(f"兴趣: {', '.join(profile.interests[:3])}")
            if profile.preferred_pace and profile.preferred_pace != "适中":
                parts.append(f"节奏: {profile.preferred_pace}")
            if profile.cognitive_style: parts.append(f"风格: {profile.cognitive_style}")
            ctx = " | ".join(parts)
            self._profile_cache[student_id] = ctx
            return ctx
        except Exception:
            return ""

    async def execute(
        self,
        state: AgentState,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行资源生成能力管道"""
        topic = kwargs.get("topic") or state.get("resource_topic") or state.get("user_message", "")
        course = kwargs.get("course") or state.get("resource_course", "")
        student_id = kwargs.get("student_id") or state.get("user_id", "anonymous")
        types = kwargs.get("resource_types") or state.get("resource_types") or RESOURCE_TYPES
        user_demand = kwargs.get("user_demand") or state.get("resource_user_demand", "")
        additional_info = kwargs.get("additional_info", "")
        temp_file_id = kwargs.get("temp_file_id")

        if not topic:
            yield {"event": "error", "message": "知识点主题不能为空"}
            return

        yield {"event": "resource_start", "stage": "analyze_profile",
               "data": f"📚 正在为「{topic}」生成学习资源..."}

        # Stage 1: 读取画像
        profile_context = self._load_profile_context(student_id)

        # Stage 2: RAG 预检索
        yield {"event": "resource_progress", "stage": "rag_retrieve",
               "data": "🔍 正在检索相关知识库..."}
        shared_context, sources = "", []
        try:
            from core.tools import tool_registry
            _result = await tool_registry.execute("rag_retrieve", query=topic, top_k=8, temp_file_id=temp_file_id)
            if isinstance(_result, (list, tuple)) and len(_result) == 2:
                shared_context, sources = _result
            elif isinstance(_result, dict) and "0" in _result and "1" in _result:
                shared_context, sources = _result["0"], _result["1"]
            else:
                shared_context, sources = str(_result) if _result else "", []
            if sources:
                yield {"event": "resource_progress",
                       "data": f"✅ 已加载 {len(sources)} 份参考资料"}
        except Exception as _e:
            logger.warning(f"[ResourceCapability] RAG 检索跳过: {_e}")

        # Stage 3: 逐个生成资源
        for rtype in types:
            # 视频类型 → 快速通道（跳过 LLM，直接搜索+封面）
            if rtype == "video":
                async for event in self._generate_videos_fast(
                    topic, course, student_id,
                ):
                    yield event
                continue

            agent = self.agents.get(rtype)
            if not agent:
                yield {"type": rtype, "event": "error", "message": f"未知类型: {rtype}"}
                continue

            yield {"type": rtype, "event": "start", "stage": "generate_resource",
                   "data": f"正在生成{RESOURCE_LABELS.get(rtype, rtype)}..."}

            full_content = ""
            try:
                async for chunk in agent.process(
                    topic, course=course, student_id=student_id,
                    user_demand=user_demand, additional_info=additional_info,
                    temp_file_id=temp_file_id, shared_rag_context=shared_context,
                    sources=sources, profile_context=profile_context,
                    ui_language=kwargs.get("language", "") or state.get("language", ""),
                ):
                    if chunk:
                        full_content += chunk
                        yield {"type": rtype, "event": "chunk", "data": chunk}
            except Exception as e:
                logger.exception(f"[ResourceCapability] {rtype} 异常")
                yield {"type": rtype, "event": "error", "message": f"生成失败: {str(e)[:100]}"}
                continue

            # Stage 4: 后处理
            end_event = {"type": rtype, "event": "end", "stage": "post_process",
                        "content": full_content}

            # 思维导图 → 自动渲染 PNG
            if rtype == "mindmap" and full_content:
                mermaid_tool = get_tool("mermaid_render")
                if mermaid_tool:
                    render_result = await mermaid_tool(full_content, student_id)
                    if render_result.get("image_url"):
                        end_event["image_url"] = render_result["image_url"]
                    if render_result.get("raw_mermaid"):
                        end_event["raw_mermaid"] = render_result["raw_mermaid"]

            # 安全检查
            safety_tool = get_tool("content_check")
            if safety_tool:
                safety = await safety_tool(full_content)
                end_event["safe"] = safety.get("safe", True)

            yield end_event

        yield {"event": "complete", "stage": "complete",
               "data": f"✅ 已生成 {len([t for t in types if t in self.agents])} 类学习资源"}
