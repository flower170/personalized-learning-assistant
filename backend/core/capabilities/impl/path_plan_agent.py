"""
路径规划智能体 (PathPlanAgent)
全新开发：结合学生画像 + 已有学习资源，生成个性化分阶段学习路径
"""
import json
import logging
from typing import Optional, AsyncGenerator

from core.capabilities.impl.base_agent import BaseAgent
from core.models.profile import profile_manager
from core.models.learning_path_data import save_path, split_daily_tasks

logger = logging.getLogger(__name__)

PATH_PLAN_SYSTEM_PROMPT = """你是一个专业的学习路径规划师。根据学生画像和已有资源，生成分阶段、可执行的个性化学习路径。

## 输入信息
- 学生画像：年级专业、知识基础(已掌握/薄弱/未接触)、学习风格、目标属性
- 学习主题：当前要学习的知识点/技能
- 已有资源：该主题下已生成的学习资料列表（讲解、导图、练习、阅读、代码）
- 总学习周期

## 输出要求
严格 JSON 格式（不包含其他文字）：
{
  "path_name": "路径名称",
  "overall_goal": "总体目标描述",
  "stages": [
    {
      "stage": 1,
      "title": "阶段标题",
      "description": "阶段说明",
      "estimated_days": 5,
      "daily_tasks": ["任务1", "任务2"],
      "focus_points": ["重点1", "重点2"],
      "suggested_resources": {
        "lecture": "推荐关联的讲解文档主题",
        "exercise": "推荐练习方向",
        "reading": "推荐阅读方向"
      },
      "expected_outcome": "预期掌握目标"
    }
  ]
}

## 规划原则
1. 循序渐进：从基础到进阶，每阶段有知识衔接
2. 个性适配：已掌握跳过、薄弱点加重、匹配学习风格
3. 目标对齐：服务于学生整体学习目标
4. 阶段数量：3-8个阶段
5. 资源关联：每个阶段尽量匹配已生成资源
"""


class PathPlanAgent(BaseAgent):
    """学习路径规划智能体（含资源匹配）"""

    def __init__(self):
        super().__init__(
            name="PathPlanAgent",
            model_name="spark-4.0-ultra",
            system_prompt=PATH_PLAN_SYSTEM_PROMPT,
            temperature=0.4,
        )

    async def generate_plan(
        self,
        student_id: str,
        topic: str,
        course: str = "",
        goal: str = "",
        total_days: int = 30,
        daily_minutes: int = 60,
        existing_resources: Optional[dict] = None,
        user_demand: str = "",
        language: str = "",
    ) -> dict:
        """生成个性化学习路径"""
        profile = profile_manager.get_profile(student_id)
        profile_ctx = self._build_profile_context(profile) if profile else ""

        # 已有资源摘要
        resources_summary = ""
        if existing_resources:
            parts = []
            for rtype, content in existing_resources.items():
                if content:
                    parts.append(f"- {rtype}: {content[:100]}...")
            resources_summary = "\n".join(parts)

        lang_hint = self._get_language_hint(language)
        prompt_parts = [f"请为「{topic}」规划分阶段学习路径。", f"语言要求：{lang_hint}"]
        if course: prompt_parts.append(f"课程：{course}")
        if goal: prompt_parts.append(f"学习目标：{goal}")
        prompt_parts.append(f"总周期：{total_days}天，每日{daily_minutes}分钟")
        if profile_ctx: prompt_parts.append(f"学生画像：\n{profile_ctx}")
        if resources_summary: prompt_parts.append(f"已有资源：\n{resources_summary}")
        if user_demand: prompt_parts.append(f"特殊需求：{user_demand}")

        prompt = "\n\n".join(prompt_parts)
        logger.info(f"[PathPlanAgent] 规划: topic={topic}, days={total_days}")

        try:
            response = await self.generate(prompt, max_tokens=8192)
            plan = self._parse_response(response)
            if plan and "stages" in plan:
                return self._build_plan_result(student_id, topic, course, goal,
                                                total_days, daily_minutes, plan)
        except Exception as e:
            logger.exception(f"[PathPlanAgent] 规划异常")

        return self._default_plan(student_id, topic, course, goal, total_days, daily_minutes)

    @staticmethod
    def _build_profile_context(profile) -> str:
        parts = []
        kb = profile.knowledge_base or {}
        if kb.get("mastered"): parts.append(f"已掌握: {', '.join(kb['mastered'][:5])}")
        if kb.get("weak"): parts.append(f"薄弱: {', '.join(kb['weak'][:3])}")
        if profile.interests: parts.append(f"兴趣: {', '.join(profile.interests[:3])}")
        if profile.learning_goals:
            g = profile.learning_goals
            if g.get("short_term"): parts.append(f"短期目标: {g['short_term']}")
            if g.get("long_term"): parts.append(f"长期目标: {g['long_term']}")
        if profile.preferred_pace: parts.append(f"节奏: {profile.preferred_pace}")
        if profile.cognitive_style: parts.append(f"风格: {profile.cognitive_style}")
        if profile.error_prone_areas: parts.append(f"易错: {', '.join(profile.error_prone_areas[:3])}")
        return "\n".join(parts)

    @staticmethod
    def _parse_response(text: str) -> Optional[dict]:
        text = text.strip()
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text: text = text.split("```")[1].split("```")[0].strip()
        try:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
        except: pass
        return None

    @staticmethod
    def _get_language_hint(language: str) -> str:
        """根据语言代码生成语言提示"""
        lang_map = {
            "zh-CN": "请使用简体中文回复",
            "en-US": "请使用英语回复 (Please respond in English)",
        }
        return lang_map.get(language, "请使用中文回复")

    def _build_plan_result(self, student_id, topic, course, goal,
                            total_days, daily_minutes, plan) -> dict:
        stages = []
        for s in plan.get("stages", []):
            days = max(1, s.get("estimated_days", 1))
            stages.append({
                "stage": s.get("stage", len(stages) + 1),
                "title": s.get("title", ""),
                "description": s.get("description", ""),
                "estimated_days": days,
                "daily_tasks": s.get("daily_tasks", []),
                "focus_points": s.get("focus_points", []),
                "suggested_resources": s.get("suggested_resources", {}),
                "expected_outcome": s.get("expected_outcome", ""),
            })
        nodes = split_daily_tasks(
            [{"node_id": f"step_{s['stage']:02d}", "title": s["title"],
              "description": s["description"], "estimated_days": s["estimated_days"],
              "resource_types": ["lecture", "exercise"],
              "reason": s.get("expected_outcome", "")} for s in stages],
            total_days, daily_minutes
        )
        result = {
            "student_id": student_id,
            "path_name": plan.get("path_name", f"{topic}学习路径"),
            "goal": goal, "topic": topic, "course": course,
            "total_duration_days": total_days,
            "daily_minutes": daily_minutes,
            "stages": stages,
            "nodes": nodes,
            "version": 1,
        }
        save_path(student_id, result)
        return result

    @staticmethod
    def _default_plan(student_id, topic, course, goal, total_days, daily_minutes) -> dict:
        return {
            "student_id": student_id, "topic": topic, "course": course,
            "goal": goal, "total_duration_days": total_days,
            "daily_minutes": daily_minutes, "version": 1,
            "path_name": f"{course or topic}学习路径",
            "stages": [
                {"stage": 1, "title": "基础入门", "description": f"学习{topic}基础知识",
                 "estimated_days": max(3, total_days // 4),
                 "daily_tasks": [f"学习{topic}基础概念"], "focus_points": ["核心概念"],
                 "suggested_resources": {}, "expected_outcome": "掌握基础"},
            ],
            "nodes": [],
        }

    async def process(self, topic: str, **kwargs) -> dict:
        """实现基类抽象方法"""
        return await self.generate_plan(
            student_id=kwargs.get("student_id", "anonymous"),
            topic=topic,
            course=kwargs.get("course", ""),
            goal=kwargs.get("goal", ""),
            total_days=int(kwargs.get("total_days", 30)),
            daily_minutes=int(kwargs.get("daily_minutes", 60)),
            user_demand=kwargs.get("user_demand", ""),
        )


path_plan_agent = PathPlanAgent()
