"""
技能差距分析 Agent (SkillGapAgent)

对比「学生画像技能」与「目标岗位 JD 市场需求」，输出雷达图双系列数据。

流程：
1. _search_jd()：DuckDuckGo 搜 "{role} 招聘 技能要求" / "{role} JD 岗位要求"
   （尽力而为，失败返回空 → 用 LLM 常识兜底）
2. _extract_market_skills()：LLM 从 JD 文本抽高频技能词 [{name, market_score, keywords[], evidence}]
3. _score_student_skill()：画像 mastered→7~9 / weak→3~5 / untouched→0~2
4. 返回 dimensions（name / skill_score / market_score / description）供雷达图双系列

模型：glm-4.7-flash，降级 glm-4.5-flash
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from core.capabilities.impl.base_agent import BaseAgent
from core.models.profile import profile_manager

logger = logging.getLogger(__name__)

JD_SYSTEM_PROMPT = """你是招聘市场技能分析师。从岗位描述文本中提取高频技能要求，评估市场需求度。

只输出 JSON 数组，不要多余文字：
[
  {"name": "技能名（如 Java / Spring Boot / MySQL）",
   "market_score": 0~10（出现频次×重要性综合，越高越抢手）,
   "keywords": ["同义关键词（如 Java SE / JDK）"],
   "evidence": "从哪句 JD 看出来的（一句话）"}
]

要求：
- 技能 5~8 个，覆盖技术栈/框架/工具/软技能
- market_score 拉开梯度，最高给 9~10，最低 2~3
- 全部简体中文"""


class SkillGapAgent(BaseAgent):
    fallback_model = "qwen-turbo"

    def __init__(self):
        super().__init__(
            name="SkillGapAgent",
            model_name="qwen-plus",
            system_prompt=JD_SYSTEM_PROMPT,
            temperature=0.3,
        )

    # ==================== 搜索 ====================

    async def _search_jd(self, role: str, max_results: int = 6) -> list[dict]:
        """搜目标岗位 JD 文本（尽力而为）"""
        async def _one(query: str):
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    rows = list(ddgs.text(query, max_results=max_results, region="cn-zh", backend="bing"))
                    return [{"title": r.get("title", ""), "url": r.get("href", ""),
                             "snippet": r.get("body", "")} for r in rows]
            except Exception:
                return []

        async def _search():
            queries = [f"{role} 招聘 技能要求", f"{role} JD 岗位职责 任职要求"]
            out = []
            for q in queries:
                out.extend(await _one(q))
                if len(out) >= 6:
                    break
            return out[:6]

        try:
            return await asyncio.wait_for(_search(), timeout=15.0)
        except Exception as e:
            logger.warning(f"[SkillGap] JD 搜索失败，用 LLM 兜底: {e}")
            return []

    # ==================== 市场技能抽取 ====================

    async def _extract_market_skills(self, role: str, jd_text: str) -> list[dict]:
        """LLM 从 JD 文本抽高频技能"""
        try:
            user = f"目标岗位：{role}\n\n岗位描述文本：\n{jd_text[:3000]}"
            resp = await self.generate(user)
            text = resp.strip()
            if "[" in text and "]" in text:
                text = text[text.index("["): text.rindex("]") + 1]
            data = json.loads(text)
            if not isinstance(data, list):
                return []
            return [{
                "name": str(d.get("name", "")),
                "market_score": float(d.get("market_score", 5)),
                "keywords": d.get("keywords", []) or [],
                "evidence": str(d.get("evidence", "")),
            } for d in data if d.get("name")]
        except Exception as e:
            logger.warning(f"[SkillGap] 技能抽取失败，用默认技能: {e}")
            return self._default_market_skills(role)

    def _default_market_skills(self, role: str) -> list[dict]:
        """LLM 失败时的常识兜底（后端岗位示例，可被后续对话覆盖）"""
        common = [
            {"name": "Java", "market_score": 9, "keywords": ["Java SE", "JDK"], "evidence": "后端主流语言"},
            {"name": "Spring Boot", "market_score": 9, "keywords": ["Spring", "Spring Cloud"], "evidence": "企业级框架标配"},
            {"name": "MySQL", "market_score": 8, "keywords": ["数据库", "SQL"], "evidence": "存储核心"},
            {"name": "Redis", "market_score": 7, "keywords": ["缓存"], "evidence": "高并发缓存"},
            {"name": "算法与数据结构", "market_score": 8, "keywords": ["算法", "数据结构"], "evidence": "笔试面试核心"},
            {"name": "Linux", "market_score": 6, "keywords": ["Linux", "服务器"], "evidence": "部署运维基础"},
        ]
        return [dict(s) for s in common]

    # ==================== 画像技能评分 ====================

    def _score_student_skill(self, profile, skill: dict) -> tuple[float, str]:
        """根据画像对某项技能打分 0~10，返回 (分数, 解读)"""
        name = skill.get("name", "")
        keywords = [name] + list(skill.get("keywords", []) or [])

        def _hit(items: list) -> bool:
            return any(any(k.lower() in str(i).lower() for k in keywords if k) for i in items or [])

        mastered = profile.knowledge_base.get("mastered", []) or []
        weak = profile.knowledge_base.get("weak", []) or []
        untouched = profile.knowledge_base.get("untouched", []) or []
        interests = profile.interests or []

        if _hit(mastered):
            return 8.0, f"画像显示你已掌握「{name}」，有较好基础"
        if _hit(weak):
            return 4.0, f"画像显示「{name}」是你的薄弱点，需要重点补"
        if _hit(untouched):
            return 2.0, f"画像显示你还未接触「{name}」，从零开始"
        if _hit(interests):
            return 5.0, f"画像显示你对「{name}」方向感兴趣，建议作为切入点"
        return 1.0, f"画像暂未体现「{name}」，市场需求高，建议优先补齐"

    # ==================== 主入口 ====================

    async def analyze(self, student_id: str, role: str = "后端开发工程师",
                      language: str = "zh-CN", top_k: int = 6) -> dict:
        """技能 vs 市场需求差距分析"""
        profile = profile_manager.get_profile(student_id)
        jd_results = await self._search_jd(role)

        jd_text = "\n".join(
            f"- {r.get('title', '')} {r.get('snippet', '')}" for r in jd_results)
        skills = await self._extract_market_skills(role, jd_text)
        if not skills:
            skills = self._default_market_skills(role)

        dimensions = []
        for s in skills[:top_k]:
            score, desc = self._score_student_skill(profile, s)
            gap = max(0, round(s["market_score"] - score, 1))
            dimensions.append({
                "name": s["name"],
                "skill_score": score,
                "market_score": round(min(10, s["market_score"]), 1),
                "gap": gap,
                "description": f"{desc}；市场要求 {s['market_score']:.0f}/10，你目前 {score:.0f}/10"
                + (f"，差距 {gap:.0f} 分" if gap > 0 else "，基本达标"),
            })

        dimensions.sort(key=lambda d: d["gap"], reverse=True)
        return {
            "ok": True,
            "role": role,
            "student_id": student_id,
            "source": "search" if jd_results else "model",
            "market_summary": f"「{role}」岗位核心要求："
                              + "、".join(d["name"] for d in dimensions[:5]),
            "dimensions": dimensions,
            "top_priority": [d["name"] for d in dimensions[:3]],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    async def process(self, *args, **kwargs):
        return await self.analyze(
            student_id=kwargs.get("student_id", "anonymous"),
            role=kwargs.get("role", "后端开发工程师"),
            language=kwargs.get("language", "zh-CN"),
            top_k=int(kwargs.get("top_k", 6)),
        )


skill_gap_agent = SkillGapAgent()

__all__ = ["SkillGapAgent", "skill_gap_agent"]
