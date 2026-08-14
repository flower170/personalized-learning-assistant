"""
学习路径规划智能体 (LearningPathAgent)
基于画像+时间约束，生成个性化带每日任务的学习路径
"""
import json
import logging
import uuid
from typing import Optional, AsyncGenerator

from core.capabilities.impl.base_agent import BaseAgent
from core.models.profile import profile_manager
from core.models.schemas import LearningNode, LearningPath
from core.models.learning_path_data import split_daily_tasks

logger = logging.getLogger(__name__)

LEARNING_PATH_SYSTEM_PROMPT = """你是一个专业的学习路径规划顾问。根据学生画像和时间约束，生成**个性化、可执行**的学习路径。

## 输入信息
- 学生画像：年级专业、知识基础、学习目标、学习偏好、困难难点、兴趣方向
- 学习主题：当前学习的知识点
- 整体目标：学生的总体学习目标
- 总学习周期：总天数
- 每日时长：每天可用学习时间

## 输出要求
严格 JSON 格式（不包含其他文字）：

```json
{
  "path_name": "路径名称",
  "steps": [
    {
      "step": 1,
      "title": "步骤标题",
      "description": "详细说明",
      "resource_types": ["lecture", "exercise"],
      "estimated_days": 5,
      "reason": "根据画像推荐的原因"
    }
  ]
}
```

## 规划原则
1. **循序渐进**：从基础到进阶，每步之间要有知识衔接
2. **个性适配**：根据知识基础调整起点，已掌握跳过、薄弱点加重
3. **分层拆分**：将总周期分配到各步骤，每步 `estimated_days` 总和不超过总天数
4. **每日时长适配**：步骤内容量应与每日可用时长匹配
5. **目标对齐**：步骤服务于整体学习目标
6. **难点攻坚**：针对困难难点分配更多天数
7. **步骤数量**：3-10 步
"""


class LearningPathAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="LearningPathAgent",
            model_name="spark-4.0-ultra",
            system_prompt=LEARNING_PATH_SYSTEM_PROMPT,
            temperature=0.4,
        )

    async def generate_path(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",
        user_demand: str = "",
        goal: str = "",
        total_days: int = 30,
        daily_minutes: int = 60,
        learning_mode: str = "balanced",
    ) -> dict:
        """生成个性化学习路径（含每日任务拆分）"""
        profile = profile_manager.get_profile(student_id)
        profile_context = self._build_profile_context(profile)

        prompt_parts = [f"请为「{topic}」规划学习路径。"]
        if course: prompt_parts.append(f"课程：{course}")
        if goal: prompt_parts.append(f"学习目标：{goal}")
        prompt_parts.append(f"总周期：{total_days}天，每日{ daily_minutes}分钟")
        prompt_parts.append(f"学习模式：{learning_mode}（balanced=均衡/intensive=紧凑/relaxed=宽松）")
        if profile_context: prompt_parts.append(f"学生画像：\n{profile_context}")
        if user_demand: prompt_parts.append(f"特殊需求：{user_demand}")

        if total_days <= 14:
            prompt_parts.append(f"\n注意：总周期较短({total_days}天)，步骤数量控制在3-5步，每步内容紧凑。")
        elif total_days >= 60:
            prompt_parts.append(f"\n注意：总周期较长({total_days}天)，步骤可细分到6-10步，每步适当扩展内容深度。")

        prompt_parts.append(f"\n各步骤的estimated_days总和必须等于{total_days}天。")
        prompt_parts.append("\n严格按照 JSON 格式输出。")

        user_prompt = "\n\n".join(prompt_parts)
        logger.info(f"[LearningPathAgent] 生成: topic={topic}, days={total_days}, daily={daily_minutes}min")

        try:
            response = await self.generate(user_prompt)
            path_data = self._parse_response(response)
            if path_data and "steps" in path_data:
                # 构建节点
                nodes = []
                for s in path_data["steps"]:
                    days = max(1, s.get("estimated_days", 1) or 1)
                    rt = s.get("resource_types", ["lecture"])
                    nodes.append({
                        "node_id": f"step_{s.get('step', len(nodes)+1):02d}_{uuid.uuid4().hex[:4]}",
                        "title": s.get("title", ""),
                        "description": s.get("description", ""),
                        "resource_type": rt[0] if rt else "lecture",
                        "estimated_days": days,
                        "resource_types": rt,
                        "reason": s.get("reason", ""),
                    })

                # 拆分每日任务
                nodes = split_daily_tasks(nodes, total_days, daily_minutes)

                result = {
                    "student_id": student_id,
                    "path_name": path_data.get("path_name", f"{topic}学习路径"),
                    "goal": goal,
                    "total_duration_days": total_days,
                    "daily_minutes": daily_minutes,
                    "learning_mode": learning_mode,
                    "topic": topic,
                    "course": course,
                    "nodes": nodes,
                    "created_at": __import__("datetime").datetime.now().isoformat(),
                    "updated_at": __import__("datetime").datetime.now().isoformat(),
                    "version": 1,
                }
                logger.info(f"[LearningPathAgent] 成功: {len(nodes)}步, {total_days}天")
                return result
            else:
                logger.warning(f"[LearningPathAgent] 解析失败")
                return self._default_path(student_id, topic, course, goal, total_days, daily_minutes)
        except Exception as e:
            logger.exception(f"[LearningPathAgent] 异常")
            return self._default_path(student_id, topic, course, goal, total_days, daily_minutes)

    @staticmethod
    def _build_profile_context(profile) -> str:
        parts = []
        mastered = profile.knowledge_base.get("mastered", [])
        weak = profile.knowledge_base.get("weak", [])
        interests = profile.interests or []
        goals = profile.learning_goals or {}
        if mastered: parts.append(f"已掌握: {', '.join(mastered[:5])}")
        if weak: parts.append(f"薄弱: {', '.join(weak[:3])}")
        if interests: parts.append(f"兴趣: {', '.join(interests[:3])}")
        if goals.get("short_term"): parts.append(f"短期目标: {goals['short_term']}")
        if goals.get("long_term"): parts.append(f"长期目标: {goals['long_term']}")
        if profile.preferred_pace and profile.preferred_pace != "适中": parts.append(f"节奏: {profile.preferred_pace}")
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
            if start != -1 and end != -1: return json.loads(text[start:end + 1])
        except: pass
        return None

    @staticmethod
    def _default_path(student_id, topic, course, goal, total_days, daily_minutes) -> dict:
        nodes = []
        step_titles = ["概念入门", "原理学习", "实践练习", "综合项目"]
        per = max(1, total_days // len(step_titles))
        for i, title in enumerate(step_titles):
            days = per if i < len(step_titles) - 1 else total_days - per * (len(step_titles) - 1)
            nodes.append({
                "node_id": f"step_{i+1:02d}_{uuid.uuid4().hex[:4]}",
                "title": title,
                "description": f"学习{topic}的{title}部分",
                "resource_type": ["lecture", "exercise", "code", "reading"][i],
                "estimated_days": days,
                "resource_types": [["lecture","mindmap"], ["lecture","exercise"], ["exercise","code"], ["code","reading"]][i],
                "reason": "默认路径，建议调整",
            })
        nodes = split_daily_tasks(nodes, total_days, daily_minutes)
        return {
            "student_id": student_id,
            "path_name": f"{course or topic}学习路径",
            "goal": goal, "total_duration_days": total_days, "daily_minutes": daily_minutes,
            "learning_mode": "balanced", "topic": topic, "course": course,
            "nodes": nodes,
            "created_at": __import__("datetime").datetime.now().isoformat(),
            "updated_at": __import__("datetime").datetime.now().isoformat(),
            "version": 1,
        }

    async def process(self, topic: str, **kwargs):
        return await self.generate_path(
            topic, kwargs.get("course", ""), kwargs.get("student_id", "anonymous"),
            kwargs.get("user_demand", ""), kwargs.get("goal", ""),
            int(kwargs.get("total_days", 30)), int(kwargs.get("daily_minutes", 60)),
            kwargs.get("learning_mode", "balanced"),
        )

learning_path_agent = LearningPathAgent()
