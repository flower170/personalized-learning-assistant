"""
交互式联网学习路径规划 Agent (WebPathPlanAgent)

与 PathPlanAgent（一次性生成）不同，本 Agent 按用户要求做三阶段交互：

Stage 1 start_conversation(student_id, topic)
    读画像 → 判断已有哪些信息 → 联网搜市场需求 + 练习资源
    → 信息不足则返回 need_info + questions 清单
Stage 2 provide_info(student_id, answers)
    合并用户补充 → 若仍缺关键信息继续问 → 信息足够进入 Stage 3
Stage 3 generate_draft → confirm_path
    generate_draft 出草案（不落库）；confirm_path 确认才 save_path()
    用户不满意可给 feedback → 带修改意见重新生成草案

设计要点：
- 画像起步：profile_manager.get_profile() 的 mastered/weak/interests/goals 等
- 联网补充：DuckDuckGo 搜市场岗位需求 + 练习资源（尽力而为，失败用 LLM 兜底）
- 宏观 + 微观：stages（阶段）+ nodes（节点）；日计划由用户在每个节点下自己记录每天学了什么+打钩
- 草案用 draft 文件暂存（data/path_drafts/{student_id}.json），确认前不动学习路径存储
- 模型：glm-4.7-flash，降级 glm-4.5-flash（BaseAgent.fallback_model）
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.capabilities.impl.base_agent import BaseAgent
from core.capabilities.impl.standard_templates import attach_stage_resources, build_standard_plan
from core.models.profile import profile_manager
from core.models.learning_path_data import save_path

logger = logging.getLogger(__name__)

DRAFT_DIR = Path(__file__).parent.parent.parent / "data" / "path_drafts"

# 关键信息维度：只问要学的科目（其余用画像或合理默认，不打扰用户）
REQUIRED_INFO = [
    "subject",         # 具体科目 / 方向（如「SQL」「Python数据分析」「统计学」）
]

# 编程/CS 类科目关键词——只有这类科目才挂官方 OJ 练习卡。
# LeetCode/牛客/洛谷/AcWing/PTA 全是编程题库，物理/化学/英语等科目挂这些卡会闹笑话
# （用户原话：「牛客网怎么会有物理题？」）。非编程科目一律不挂卡。
PROGRAMMING_SUBJECT_KEYWORDS = (
    "sql", "数据库", "mysql", "postgresql", "sqlite",
    "python", "java", "c++", "c语言", "csharp", "c#", "golang", "go语言", "rust", "scala", "kotlin",
    "javascript", "typescript", "nodejs", "前端", "后端", "全栈", "vue", "react", "html", "css",
    "数据结构", "算法", "编程", "代码", "开发", "软件", "计算机", "操作系统", "网络", "爬虫",
    "人工智能", "机器学习", "深度学习", "数据挖掘", "数据分析", "数据科学", "大数据", "数据",
    "pandas", "numpy", "数据可视化", "matplotlib", "echarts", "django", "flask", "spring",
    "android", "ios", "小程序", "linux", "docker", "git", "leetcode", "刷题", "oj",
    "测试", "安全", "自动化",
)

INFO_LABELS = {
    "subject": "你想具体学哪个科目？例如：SQL、Python数据分析（pandas）、Excel 数据分析、统计学、数据可视化、机器学习… 也可以直接写你要学的科目。",
    "daily_hours": "你打算每天花多少时间学这个？例如「1小时」「30分钟」。告诉我后我会按你的时间安排每天的任务量。",
    "foundation": "你目前的基础是哪种？①零基础，从没学过 ②入门，学过一点但不熟练 ③进阶，已经掌握基础 ④已会大部分，只查漏补缺",
}

# 具体科目识别关键词：命中即认为「这就是个科目」，不再问「范围比较大」。
# 顺序大致按「更具体在前」，避免 postgresql 被 sql 抢先匹配成 sql。
CONCRETE_SUBJECT_KEYWORDS = (
    "postgresql", "mysql", "sqlite", "sql", "数据库",
    "pandas", "numpy", "excel", "matplotlib", "echarts", "power bi",
    "python", "java", "c++", "c语言", "csharp", "c#", "golang", "go语言", "rust", "scala", "kotlin",
    "javascript", "typescript", "nodejs", "vue", "react", "html", "css",
    "前端", "后端", "全栈", "数据结构", "算法", "操作系统", "计算机网络", "网络", "爬虫",
    "测试", "安全", "linux", "docker", "git", "小程序", "android", "ios",
    "机器学习", "深度学习", "数据分析", "数据可视化", "数据挖掘", "数据科学", "统计学",
    "大数据", "物理", "化学", "生物", "数学", "英语", "语文",
)

# 宽泛/动词性词语：topic 里含这些词且没有命中具体科目 → 不算具体科目
BROAD_TOPIC_WORDS = (
    "分析", "开发", "入门", "学习", "课程", "方向", "领域", "技术", "知识",
    "方面", "怎么", "如何", "帮我", "规划", "路径", "路线", "想学", "要学",
    "练习", "资料", "工作", "求职", "就业", "准备", "考", "开始",
    "提升", "提高", "掌握", "成为", "自己", "增强", "进阶", "学会", "了解", "基础",
)

WEB_PATH_SYSTEM_PROMPT = """你是联网学习路径规划师。围绕用户所选的具体科目，结合学生画像和市场需求，生成「宏观阶段」学习路径（每日计划由系统按阶段自动拆分，无需你输出）。

## 输入
- 所选科目：用户具体要学的科目（如「SQL」「Python数据分析」「统计学」）
- 学生画像：已掌握/薄弱/兴趣/目标/每日时长
- 市场需求：相关技能的热度线索（若有；缺失则按通用常识补）
- 练习资源：官方 OJ / 练习平台推荐
- 主题：大的方向（如「数据分析」）

## 输出（严格 JSON，只输出宏观阶段，不要多余文字，不要输出 nodes）
{
  "path_name": "路径名称",
  "overall_goal": "总体目标",
  "market_demand": "市场需求摘要（一两句）",
  "stages": [
    {
      "stage": 1, "title": "阶段标题（用具体技能命名）", "description": "阶段说明",
      "estimated_days": 14, "focus_points": ["重点技能", "重点技能"],
      "expected_outcome": "阶段结束后掌握什么"
    }
  ]
}

## 规划原则
1. 循序渐进、个性适配：画像已掌握的跳过、薄弱点加重
2. 贴合市场需求：优先排市场热度高的技能点
3. 阶段 3~8 个，estimated_days 之和为总周期（30~120 天）
4. 练习资源建议官方 OJ（LeetCode/牛客/洛谷/AcWing/PTA）
5. 全部用简体中文"""


class WebPathPlanAgent(BaseAgent):
    """交互式联网学习路径规划 Agent（三阶段状态机）"""

    fallback_model = "qwen-turbo"

    def __init__(self):
        super().__init__(
            name="WebPathPlanAgent",
            model_name="qwen-plus",
            system_prompt=WEB_PATH_SYSTEM_PROMPT,
            temperature=0.4,
        )

    # ==================== 画像读取 ====================

    def _load_profile_ctx(self, student_id: str) -> dict:
        """读取画像并转成结构化上下文；失败返回空 dict"""
        try:
            profile = profile_manager.get_profile(student_id)
        except Exception as e:
            logger.warning(f"[WebPathPlan] 画像读取失败 {student_id}: {e}")
            return {}
        kb = profile.knowledge_base or {}
        goals = profile.learning_goals or {}
        return {
            "mastered": kb.get("mastered", []) or [],
            "weak": kb.get("weak", []) or [],
            "untouched": kb.get("untouched", []) or [],
            "interests": profile.interests or [],
            "cognitive_style": profile.cognitive_style or "",
            "preferred_pace": profile.preferred_pace or "",
            "error_prone": profile.error_prone_areas or [],
            "short_term_goal": goals.get("short_term", "") or "",
            "long_term_goal": goals.get("long_term", "") or "",
            "goal_attribute": profile.goal_attribute or "",
            "daily_hours": profile.daily_available_hours or 0,
        }

    @staticmethod
    def _derive_foundation(ctx: dict) -> str:
        """按画像知识基础推导基础水平：""（画像无数据，需问）| 零基础 | 入门 | 进阶。"""
        mastered = ctx.get("mastered") or []
        weak = ctx.get("weak") or []
        untouched = ctx.get("untouched") or []
        total = len(mastered) + len(weak) + len(untouched)
        if total == 0:
            return ""
        if len(mastered) >= 3 and len(mastered) >= total * 0.5:
            return "进阶"
        if len(mastered) >= 1:
            return "入门"
        return "零基础"

    @staticmethod
    def _missing_info(collected: dict) -> list[str]:
        """补问清单：科目未知 / 每天时间没定 / 基础水平推不出（画像无知识数据）。
        优先画像（subject/daily_hours/foundation 都从画像带），画像不足才问用户——
        即「先画像搜集、再用户自定义填」。"""
        missing = []
        if not (collected.get("subject") or collected.get("role") or collected.get("target")):
            missing.append("subject")
        daily_hours = collected.get("daily_hours") or collected.get("profile", {}).get("daily_hours")
        if not daily_hours:
            missing.append("daily_hours")
        profile = collected.get("profile", {}) or {}
        mastered = profile.get("mastered") or collected.get("mastered") or []
        weak = profile.get("weak") or collected.get("weak") or []
        untouched = profile.get("untouched") or collected.get("untouched") or []
        has_kb = bool(mastered or weak or untouched)
        if not collected.get("foundation") and not has_kb:
            missing.append("foundation")
        return missing

    # ==================== 联网搜索 ====================

    async def _search_market_and_resources(self, topic: str, target: str = "") -> dict:
        """联网搜市场需求 + 练习资源。搜索不可靠，失败返回空 dict（LLM 兜底）。

        ddgs.text() 是阻塞调用，必须在独立线程里跑（asyncio.to_thread），
        否则会卡死整个事件循环，wait_for 的定时根本打断不了阻塞调用（历史踩坑）。
        """
        import asyncio

        def _one_sync(query: str):
            from ddgs import DDGS
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=5, region="cn-zh", backend="bing"))
                return [{"title": r.get("title", ""), "url": r.get("href", ""),
                         "snippet": r.get("body", "")[:120]} for r in rows]

        async def _one(query: str):
            try:
                rows = await asyncio.wait_for(asyncio.to_thread(_one_sync, query), timeout=5.0)
                return rows or []
            except Exception:
                return []

        async def _search():
            queries = []
            if target:
                queries += [
                    f"{target} 学习路线 知识点",
                    f"{topic} {target} 刷题 练习",
                ]
            queries += [f"{topic} 学习路线 练题平台", f"{topic} 入门到进阶 学习路径"]
            market, resources = [], []
            for q in queries[:4]:
                rows = await _one(q)
                if len(market) < 3:
                    market.extend(rows[:3])
                else:
                    resources.extend(rows[:3])
            return {"market": market[:4], "resources": resources[:4]}

        # 联网在当前网络基本不可达（每次都撞满超时），整体压到 6s，失败交给 LLM 兜底
        try:
            return await asyncio.wait_for(_search(), timeout=6.0)
        except Exception as e:
            logger.warning(f"[WebPathPlan] 联网搜索失败，用 LLM 兜底: {e}")
            return {"market": [], "resources": []}

    # ==================== Stage 1 / 2：信息采集 ====================

    async def start_conversation(self, student_id: str, topic: str,
                                 daily_hours: Optional[float] = None,
                                 cycle: Optional[str] = None) -> dict:
        """Stage 1：画像起步 + 识别科目 + 时间/基础采集。

        优先级（用户诉求「先画像搜集、再用户自定义填」）：
        ① topic 本身是具体科目 + 画像信息充足 → 直接联网出草案；
        ② topic 是具体科目，但每天时间/基础水平画像里没有 → 补问这几个再出草案；
        ③ 画像里有方向（目标/兴趣/薄弱点能抠出科目）→ confirm_subject 确认（时间/基础若缺，确认后 Stage2 补问）；
        ④ 都推不出 → 科目 + 每天时间 + 基础一次问齐。

        弹窗发起时带 daily_hours/cycle（前端已问）；打字发起没带 → 走 _missing_info 补问。
        联网搜索只在要出草案时才做。"""
        ctx = self._load_profile_ctx(student_id)
        ctx["topic"] = topic

        collected = {
            "topic": topic,
            "profile": {k: ctx[k] for k in
                        ("mastered", "weak", "interests", "cognitive_style",
                         "preferred_pace", "daily_hours", "long_term_goal",
                         "short_term_goal", "goal_attribute")},
            "market": [],
            "resources": [],
        }
        if daily_hours:
            collected["daily_hours"] = daily_hours
        if cycle:
            collected["cycle"] = cycle
        # 基础定位：画像能推则静默带上，推不出（画像无知识数据）交给 _missing_info 问用户
        foundation = self._derive_foundation(ctx)
        if foundation:
            collected["foundation"] = foundation

        subject, concrete = self._derive_subject(topic, ctx)
        if concrete:
            # ①/② topic 本身是具体科目
            collected["subject"] = subject
            collected["long_term_goal"] = collected.get("long_term_goal") or subject
            missing = self._missing_info(collected)
            if missing:
                return self._need_info(topic, collected, missing)
            target = (ctx.get("long_term_goal") or ctx.get("short_term_goal")
                      or ctx.get("goal_attribute") or subject)
            web = await self._search_market_and_resources(topic, target)
            collected["market"] = web.get("market", [])
            collected["resources"] = web.get("resources", [])
            return {
                "stage": 3,
                "need_info": False,
                "ready_to_generate": True,
                "topic": topic,
                "collected": collected,
            }

        if subject:
            # ③ 画像里有方向 → 提取出来让用户确认，而不是开放提问
            return {
                "stage": 1,
                "need_info": True,
                "confirm_subject": subject,
                "questions": [self._subject_confirm_label(topic, subject, ctx)],
                "missing_keys": ["subject"],
                "collected": collected,
                "topic": topic,
            }

        # ④ 完全推不出科目 → 科目 + 每天时间 + 基础一次问齐
        return self._need_info(topic, collected, self._missing_info(collected))

    @staticmethod
    def _need_info(topic: str, collected: dict, missing: list[str]) -> dict:
        """组装 need_info 响应：问题列表按缺失键生成。"""
        return {
            "stage": 1,
            "need_info": True,
            "questions": [INFO_LABELS[m].replace("{topic}", topic) for m in missing],
            "missing_keys": missing,
            "collected": collected,
            "topic": topic,
        }

    # ==================== 科目识别 ====================

    @staticmethod
    def _find_known_subject(text: str) -> str:
        """在文本里找第一个已知具体科目关键词；找不到返回 ''。"""
        low = str(text or "").lower()
        for kw in CONCRETE_SUBJECT_KEYWORDS:
            if kw in low:
                return kw
        return ""

    @staticmethod
    def _looks_concrete_subject(text: str) -> bool:
        """文本短且不含宽泛词 → 可直接当作具体科目（如「离散数学」「统计推断」）。"""
        s = str(text or "").strip().lower()
        if not s:
            return False
        return len(s) <= 12 and not any(w in s for w in BROAD_TOPIC_WORDS)

    @staticmethod
    def _derive_subject(topic, ctx) -> tuple[str, bool]:
        """推导具体科目：(subject, 是否 topic 本身即具体科目)。
        优先级：topic 短且具体 → topic 整体；长 topic 抠已知科目关键词 → 画像目标 → 兴趣 → 薄弱点。"""
        t = str(topic or "").strip()
        # ① topic 短且不含宽泛词 → 整体就是科目（「离散数学」「sql」），避免被抠成「数学」
        if WebPathPlanAgent._looks_concrete_subject(t):
            return t, True
        # ② 长 topic 里抠出已知科目关键词（「帮我规划 SQL 的学习路径」→ sql）
        known = WebPathPlanAgent._find_known_subject(t)
        if known:
            return known, True
        # ③ 画像目标 → ④ 兴趣 → ⑤ 薄弱点
        goal = str(ctx.get("long_term_goal") or ctx.get("short_term_goal") or "")
        known = WebPathPlanAgent._find_known_subject(goal)
        if known:
            return known, False
        for it in (ctx.get("interests") or []):
            known = WebPathPlanAgent._find_known_subject(str(it))
            if known:
                return known, False
        for w_ in (ctx.get("weak") or []):
            known = WebPathPlanAgent._find_known_subject(str(w_))
            if known:
                return known, False
        return "", False

    @staticmethod
    def _subject_confirm_label(topic: str, subject: str, ctx: dict) -> str:
        """画像确认问句：把从画像提取的方向 + 薄弱点摆给用户确认。"""
        parts = [f"根据你的画像，你想学的方向是「{subject}」"]
        weak = ctx.get("weak") or []
        if weak:
            parts.append(f"，画像里你的薄弱点是「{'、'.join(str(x) for x in weak[:3])}」")
        interests = ctx.get("interests") or []
        if interests:
            parts.append(f"，你感兴趣的是「{'、'.join(str(x) for x in interests[:2])}」")
        parts.append("。确认按这个科目开始规划吗？也可以直接告诉我具体想学的科目。")
        return "".join(parts)

    async def provide_info(self, student_id: str, topic: str, answers: dict) -> dict:
        """Stage 2：合并用户补充信息，仍缺则继续问，够了进 Stage 3"""
        collected = answers.get("collected") or self._load_profile_ctx(student_id)
        collected["topic"] = topic

        # 用户答案合并进 collected
        user_ans = answers.get("answers") or {}
        for k, v in user_ans.items():
            collected[k] = v

        # 从答案里推导具体科目
        subject = user_ans.get("subject") or user_ans.get("role") or user_ans.get("target")
        if subject and not collected.get("long_term_goal"):
            collected["long_term_goal"] = subject

        # 拿到科目后，按科目重新联网搜学习资源 + 练习
        if subject:
            web = await self._search_market_and_resources(topic, subject)
            if web.get("market"):
                collected["market"] = web["market"]
            if web.get("resources"):
                collected["resources"] = web["resources"]

        missing = self._missing_info(collected)
        if missing:
            return {
                "stage": 2,
                "need_info": True,
                "questions": [INFO_LABELS[m].replace("{topic}", topic) for m in missing],
                "missing_keys": missing,
                "collected": collected,
                "topic": topic,
            }
        return {
            "stage": 3,
            "need_info": False,
            "ready_to_generate": True,
            "topic": topic,
            "collected": collected,
        }

    # ==================== Stage 3：草案 → 确认 → 存储 ====================

    async def generate_draft(self, student_id: str, topic: str, collected: dict) -> dict:
        """生成路径草案（暂存 draft 文件，不落学习路径存储）"""
        daily_hours = self._parse_hours(
            collected.get("daily_hours") or collected.get("profile", {}).get("daily_hours"))
        daily_minutes = int(daily_hours * 60)
        subject = (collected.get("subject") or collected.get("role") or collected.get("target")
                   or collected.get("long_term_goal") or "")
        if not subject or subject == "该科目":
            subject = self._derive_subject(topic, collected)[0] or subject or "该科目"

        # 标准模板：subject/topic 命中（如「数据分析 90 天」）→ 直接按模板结构生成，
        # 阶段配套资源（视频/练习网站）随 stage.resources 带可点击 URL，保证与用户标准一致。
        template_plan, template_days = build_standard_plan(subject, topic, daily_minutes)
        if template_plan:
            logger.info(f"[WebPathPlan] 命中标准模板: subject={subject}, total_days={template_days}")
            draft = self._build_draft(student_id, topic, collected, template_plan, template_days,
                                      daily_minutes, subject)
            # 统一资源推荐：视频换 B站播放量最高真实视频，编程类阶段挂牛客链接
            draft = await attach_stage_resources(draft, subject)
            self._save_draft(student_id, draft)
            return {
                "stage": 3,
                "need_info": False,
                "draft_id": draft["draft_id"],
                "path": draft,
                "message": f"已按「{draft.get('path_name', '标准')}」标准模板生成路径草案：推荐视频（B站播放量最高）、练习网站均可直接点击进入。请确认或提出修改意见。",
            }

        explicit_cycle = collected.get("cycle") or collected.get("profile", {}).get("cycle")

        prompt = self._build_prompt(topic, collected, daily_minutes, subject, explicit_cycle)
        logger.info(f"[WebPathPlan] 生成草案: student={student_id}, topic={topic}, subject={subject}")

        plan = None
        try:
            resp = await self._generate_plan(prompt)
            logger.info(f"[WebPathPlan] LLM 草案返回 {len(resp) if resp else 0} 字")
            plan = self._parse_response(resp)
            if not plan and resp:
                logger.warning(f"[WebPathPlan] 解析失败，原文前300字: {resp[:300]}")
        except Exception as e:
            logger.exception(f"[WebPathPlan] 草案生成异常")

        if explicit_cycle:
            # 用户/画像给了期望周期 → 用固定周期
            total_days = self._parse_cycle(str(explicit_cycle))
            if not plan or not plan.get("stages"):
                plan = self._default_plan(topic, subject, total_days)
        else:
            # 没问周期 → 由 LLM 按科目学习曲线定阶段时长，汇总为总周期（30~120 天）
            if plan and plan.get("stages"):
                total_days = sum(max(1, s.get("estimated_days", 7)) for s in plan["stages"])
                total_days = max(30, min(120, total_days))
            else:
                total_days = 60
                plan = self._default_plan(topic, subject, total_days)

        draft = self._build_draft(student_id, topic, collected, plan, total_days, daily_minutes, subject)
        # 统一资源推荐：每阶段视频 → B站播放量最高真实视频；编程类阶段 → 牛客网练习链接
        draft = await attach_stage_resources(draft, subject)
        # 每个阶段按重点技能找官方 OJ 练习（无真实命中用平台官方搜索页兜底，链接永远可点）
        draft = await self._attach_stage_cards(draft, subject)
        self._save_draft(student_id, draft)
        return {
            "stage": 3,
            "need_info": False,
            "draft_id": draft["draft_id"],
            "path": draft,
            "message": "这是根据你要学的科目与市场需求生成的路径草案，请确认或提出修改意见。",
        }

    async def generate_draft_stream(self, student_id: str, topic: str, collected: dict, draft_id: str = ""):
        """流式生成路径草案：yield 进度/chunk 事件，最后 yield complete（含 draft）。

        供 /online-path/draft-stream 使用；draft_id 非空表示「按意见重新生成」，完成后把旧草案里
        用户手动加的资源带回新草案，避免改一次意见丢资源。
        """
        daily_hours = self._parse_hours(
            collected.get("daily_hours") or collected.get("profile", {}).get("daily_hours"))
        daily_minutes = int(daily_hours * 60)
        subject = (collected.get("subject") or collected.get("role") or collected.get("target")
                   or collected.get("long_term_goal") or "")
        if not subject or subject == "该科目":
            subject = self._derive_subject(topic, collected)[0] or subject or "该科目"

        yield {"event": "progress", "stage": "generate",
               "message": f"正在为「{subject or topic}」生成学习路径草案…"}

        # 标准模板命中 → 不调 LLM，直接按模板结构生成
        template_plan, template_days = build_standard_plan(subject, topic, daily_minutes)
        if template_plan:
            draft = self._build_draft(student_id, topic, collected, template_plan, template_days,
                                      daily_minutes, subject)
            yield {"event": "progress", "stage": "attach", "message": "正在匹配推荐视频与练习资源…"}
            draft = await attach_stage_resources(draft, subject)
            if draft_id:
                old = self._load_draft(student_id, draft_id)
                if old:
                    self._carry_draft_resources(old.get("nodes", []), draft.get("nodes", []))
            self._save_draft(student_id, draft)
            yield {"event": "complete", "path": draft, "draft_id": draft["draft_id"],
                   "message": "已按标准模板生成路径草案：推荐视频、练习网站均可直接点击进入。请确认或提出修改意见。"}
            return

        explicit_cycle = collected.get("cycle") or collected.get("profile", {}).get("cycle")
        prompt = self._build_prompt(topic, collected, daily_minutes, subject, explicit_cycle)

        # 流式 LLM 生成（BaseAgent.generate_stream 自带主→降级模型切换）
        plan = None
        resp_parts = []
        try:
            async for chunk in self.generate_stream(prompt, max_tokens=8192):
                resp_parts.append(chunk)
                yield {"event": "chunk", "data": chunk}
            resp = "".join(resp_parts)
            logger.info(f"[WebPathPlan] 流式草案返回 {len(resp)} 字")
            plan = self._parse_response(resp)
            if not plan and resp:
                logger.warning(f"[WebPathPlan] 流式解析失败，原文前300字: {resp[:300]}")
        except Exception as e:
            logger.exception(f"[WebPathPlan] 流式草案生成异常")

        if explicit_cycle:
            total_days = self._parse_cycle(str(explicit_cycle))
            if not plan or not plan.get("stages"):
                plan = self._default_plan(topic, subject, total_days)
        else:
            if plan and plan.get("stages"):
                total_days = sum(max(1, s.get("estimated_days", 7)) for s in plan["stages"])
                total_days = max(30, min(120, total_days))
            else:
                total_days = 60
                plan = self._default_plan(topic, subject, total_days)

        yield {"event": "progress", "stage": "attach", "message": "正在匹配练习资源与题库…"}
        draft = self._build_draft(student_id, topic, collected, plan, total_days, daily_minutes, subject)
        draft = await attach_stage_resources(draft, subject)
        draft = await self._attach_stage_cards(draft, subject)
        if draft_id:
            old = self._load_draft(student_id, draft_id)
            if old:
                self._carry_draft_resources(old.get("nodes", []), draft.get("nodes", []))
        self._save_draft(student_id, draft)
        yield {"event": "complete", "path": draft, "draft_id": draft["draft_id"],
               "message": "这是根据你要学的科目与市场需求生成的路径草案，请确认或提出修改意见。"}

    def _build_prompt(self, topic, collected, daily_minutes, subject, explicit_cycle=None) -> str:
        profile = collected.get("profile", {})
        cycle_hint = f"，用户期望周期约{explicit_cycle}" if explicit_cycle else "，总周期由你按该科目的学习曲线合理设定"
        parts = [
            f"请针对科目「{subject}」，为主题「{topic}」规划一条学习路径。",
            f"每日{daily_minutes}分钟{cycle_hint}。",
            f"path_name 命名：{subject}学习路径；overall_goal：系统掌握{subject}，能独立完成相关任务。",
        ]
        parts.append(
            f"科目细化要求：围绕「{subject}」这个科目按学习曲线拆解阶段，每个阶段聚焦一个技能点"
            "（例如 科目「Python数据分析」 → pandas基础 → 数据清洗 → 分组聚合 → 数据可视化 → 综合项目）。"
            "阶段标题直接用具体技能命名（如「pandas 基础」「数据清洗」），"
            "不要用「基础入门」「综合提升」这类泛标题。每个阶段的 focus_points 写 8~12 个详细具体知识点，"
            "细到函数/方法/概念级别（如「pandas: read_excel/read_csv 读入」「dropna/fillna 处理缺失值」"
            "「groupby + agg 聚合统计」「布尔索引与 loc/iloc 切片」「时间序列 resample 重采样」），"
            "不要写「基础入门」「掌握技能」这类泛词。expected_outcome 写清阶段结束能独立做什么。"
        )

        ctx_lines = []
        if profile.get("mastered"): ctx_lines.append(f"已掌握: {', '.join(profile['mastered'][:6])}")
        if profile.get("weak"): ctx_lines.append(f"薄弱: {', '.join(profile['weak'][:4])}")
        if profile.get("interests"): ctx_lines.append(f"兴趣: {', '.join(profile['interests'][:4])}")
        if profile.get("cognitive_style"): ctx_lines.append(f"风格: {profile['cognitive_style']}")
        if profile.get("preferred_pace"): ctx_lines.append(f"节奏: {profile['preferred_pace']}")
        if ctx_lines:
            parts.append("学生画像：\n" + "\n".join(ctx_lines))

        # 画像定位的基础水平 → 注入 LLM，让它按基础调整路径深度（零基础/入门/进阶/已会大部分）
        foundation = collected.get("foundation") or ""
        if foundation:
            profile = collected.get("profile", {}) or {}
            mastered = profile.get("mastered") or collected.get("mastered") or []
            weak = profile.get("weak") or collected.get("weak") or []
            untouched = profile.get("untouched") or collected.get("untouched") or []
            parts.append(
                f"学生基础水平：{foundation}（已掌握{len(mastered)}项 / 薄弱{len(weak)}项 / 未接触{len(untouched)}项）。"
                "请按此基础设计路径：零基础先做概念铺垫再上手练习；入门侧重基础操作与适量练习；"
                "进阶直接聚焦薄弱点与进阶技能；已掌握的内容跳过不排，不要从零讲起。"
            )

        market = collected.get("market", [])
        if market:
            market_text = "\n".join(f"- {m.get('title','')} {m.get('snippet','')[:60]}" for m in market[:4])
            parts.append(f"市场需求线索：\n{market_text}")
        else:
            parts.append("市场需求：无实时数据，请按该领域通用岗位需求合理推断。")

        resources = collected.get("resources", [])
        if resources:
            res_text = "\n".join(f"- {r.get('title','')} ({r.get('url','')})" for r in resources[:4])
            parts.append(f"练习资源线索：\n{res_text}")
        else:
            parts.append("练习资源：建议结合 LeetCode、牛客、洛谷、AcWing、PTA 官方 OJ。")

        parts.append("只输出宏观阶段 stages，每个阶段 estimated_days 合理；每日计划由系统自动拆分，无需输出 nodes。")
        return "\n\n".join(parts)

    async def confirm_path(self, student_id: str, draft_id: str, feedback: str = "") -> dict:
        """用户确认 → 落库；带 feedback → 重新生成草案。"""
        draft = self._load_draft(student_id, draft_id)
        if not draft:
            return {"ok": False, "error": "草案不存在或已过期，请重新发起路径规划"}

        if feedback and feedback.strip():
            # 带修改意见 → 重新生成草案（改为流式：返回 ready_to_generate，前端调 draft-stream）
            topic = draft.get("topic", "")
            collected = draft.get("collected", {})
            collected["feedback"] = feedback.strip()
            logger.info(f"[WebPathPlan] 用户要求修改: {feedback.strip()}")
            return {
                "ok": True, "revised": True,
                "ready_to_generate": True,
                "topic": topic,
                "collected": collected,
                "draft_id": draft_id,
            }

        # 确认 → 持久化。草案文件保留，供用户后续再提修改意见（feedback）重新生成。
        path = draft.get("path", draft)
        path.update({
            "student_id": student_id,
            "status": "approved",
            "approved_at": datetime.now().isoformat(timespec="seconds"),
            "data_source": {"market": "search|model", "practice": "search|model"},
        })
        save_path(student_id, path)
        return {"ok": True, "revised": False, "path": path,
                "message": "✅ 学习路径已确认并保存！你可以在「我的练习」页查看。"}

    # ==================== LLM 调用（带重试/降级） ====================

    async def _generate_plan(self, prompt: str) -> str:
        """草案生成：主模型限流(429/1305)稍等重试，其他错误/多次失败降级到 fallback_model。

        硬性截止：整个生成（含重试/降级）最多 40s；单次主模型调用上限 25s、降级模型 15s，
        超时即取消并截断 → 返回空走 _default_plan 确定性兜底（确定性兜底不需要 LLM）。
        平台持续过载（主模型两次 429/1305）→ 跳过降级直接兜底，不白等，总时长最坏 ~50s。
        """
        import asyncio
        last_err = None
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 40.0
        MAIN_CALL_CAP = 25.0
        FALLBACK_CALL_CAP = 15.0

        def _remain() -> float:
            return deadline - loop.time()

        async def _call_with_timeout(factory, label: str, cap: float | None = None):
            """在剩余预算内调用异步工厂（可选单次上限）；预算耗尽直接抛 TimeoutError"""
            remain = _remain()
            if remain <= 0:
                raise asyncio.TimeoutError()
            timeout = min(remain, cap) if cap else remain
            return await asyncio.wait_for(factory(), timeout=timeout)

        overloaded = False  # 平台过载（429/1305）→ 降级模型同平台大概率也过载
        for attempt in range(2):
            try:
                resp = await _call_with_timeout(
                    lambda: self.generate(prompt, max_tokens=8192), "主模型", cap=MAIN_CALL_CAP)
                if resp:
                    return resp
                last_err = RuntimeError("模型返回为空")
            except asyncio.TimeoutError:
                last_err = RuntimeError("模型响应超时")
                break
            except Exception as e:
                last_err = e
                if "429" in str(e) or "1305" in str(e):
                    overloaded = True
                    wait = min(1.5 * (attempt + 1), max(0.0, _remain() - 1.0))
                    if wait <= 0:
                        break
                    logger.warning(f"[WebPathPlan] 模型限流(429)，{wait:.1f}s 后重试 ({attempt + 1}/2)")
                    await asyncio.sleep(wait)
                    continue
                break

        if overloaded:
            logger.warning("[WebPathPlan] 主模型持续过载(429/1305)，跳过降级模型直接走确定性兜底")
            return ""

        # 降级模型兜底（预算还剩才试）
        if _remain() > 2.0:
            try:
                messages = self.build_messages(prompt)
                resp = await _call_with_timeout(
                    lambda: self._fallback_client().chat(messages, temperature=self.temperature),
                    "降级模型", cap=FALLBACK_CALL_CAP)
                if resp:
                    return resp
                last_err = RuntimeError("降级模型返回为空")
            except asyncio.TimeoutError:
                last_err = RuntimeError("降级模型响应超时")
            except Exception as e:
                last_err = e

        logger.error(f"[WebPathPlan] 草案生成失败，走默认兜底: {last_err}")
        return ""

    # ==================== 草案落盘 ====================

    def _save_draft(self, student_id: str, draft: dict):
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        (DRAFT_DIR / f"{student_id}.json").write_text(
            json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_draft(self, student_id: str, draft_id: str) -> Optional[dict]:
        p = DRAFT_DIR / f"{student_id}.json"
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if data.get("draft_id") == draft_id else None

    def _delete_draft(self, student_id: str, draft_id: str):
        p = DRAFT_DIR / f"{student_id}.json"
        if p.exists():
            p.unlink()

    def add_draft_resource(self, student_id: str, draft_id: str, node_id: str,
                           title: str, url: str, platform: str = "") -> Optional[dict]:
        """给草案的某个节点挂一条学习资源（用户在向导里根据规划添加）。
        返回更新后的 draft dict；草案不存在 / 节点不存在返回 None。"""
        draft = self._load_draft(student_id, draft_id)
        if not draft:
            return None
        for node in draft.get("nodes", []):
            if node.get("node_id") != node_id:
                continue
            resources = node.setdefault("resources", [])
            if not any(r.get("title") == title and r.get("url") == url for r in resources):
                resources.append({
                    "rid": f"res_{uuid.uuid4().hex[:12]}",
                    "node_id": node_id,
                    "title": title, "url": url,
                    "platform": platform or "",
                    "watched": False, "watch_note": "",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                })
            self._save_draft(student_id, draft)
            return draft
        return None

    # ==================== 工具方法 ====================

    @staticmethod
    def _parse_hours(value, default: float = 2.0) -> float:
        """把用户自然语言时间回答转成小时：'2'→2, '2小时'→2, '1.5h'→1.5, '30分钟'→0.5。
        解析失败回退默认 2 小时。"""
        if value is None:
            return default
        s = str(value).strip().lower()
        try:
            return float(s)
        except ValueError:
            pass
        nums = re.findall(r"(\d+(?:\.\d+)?)", s)
        if not nums:
            return default
        num = float(nums[0])
        if any(w in s for w in ("分钟", "min")):
            return round(num / 60, 2)
        return num

    @staticmethod
    def _parse_cycle(cycle: str) -> int:
        """把 '60'/'60天'/'2周'/'1个月' 等解析为天数"""
        import re
        if not cycle:
            return 60
        s = str(cycle)
        m = re.search(r"(\d+)\s*个月", s)
        if m:
            return int(m.group(1)) * 30
        m = re.search(r"(\d+)\s*周", s)
        if m:
            return int(m.group(1)) * 7
        m = re.search(r"(\d+)", s)
        return int(m.group(1)) if m else 60

    @staticmethod
    def _is_programming_subject(subject) -> bool:
        """科目是否编程/CS 类——决定要不要挂官方 OJ 练习卡。空值按历史行为默认挂卡。"""
        if not subject:
            return True
        low = str(subject).lower()
        return any(k in low for k in PROGRAMMING_SUBJECT_KEYWORDS)

    @staticmethod
    def _parse_response(text: str) -> Optional[dict]:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        start = text.find("{")
        if start != -1:
            end = text.rfind("}")
            if end != -1:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    pass
            # 容错：LLM 输出偶尔被截断 → 从末尾往前找最后一个能完整解析的 "}"
            for end in range(end - 1 if end != -1 else len(text) - 1, start, -1):
                if text[end] != "}":
                    continue
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    continue
        return None

    def _build_draft(self, student_id, topic, collected, plan, total_days, daily_minutes, subject) -> dict:
        """把 LLM 输出整理成标准路径结构（stages 宏观 + nodes 微观日计划）"""
        stages = []
        for i, s in enumerate(plan.get("stages", []), 1):
            days = max(1, s.get("estimated_days", 1))
            stages.append({
                "stage": i,
                "title": s.get("title", f"阶段{i}"),
                "description": s.get("description", ""),
                "estimated_days": days,
                "focus_points": s.get("focus_points", []) or [],
                "expected_outcome": s.get("expected_outcome", ""),
                # 阶段配套资源（标准模板带的视频/练习网站/数据集，均可点击直达）
                "resources": s.get("resources", []) or [],
                # 通用兜底阶段标记：不挂 OJ 卡（避免错配链接）
                "_fallback": bool(s.get("_fallback")),
            })

        # nodes：LLM 给的节点或按阶段拆分
        raw_nodes = plan.get("nodes", [])
        if raw_nodes:
            nodes = []
            for n in raw_nodes:
                nodes.append({
                    "node_id": n.get("node_id") or f"step_{len(nodes) + 1:02d}",
                    "title": n.get("title", ""),
                    "description": n.get("description", ""),
                    "estimated_days": max(1, n.get("estimated_days", 1)),
                    "resource_types": n.get("resource_types", ["lecture", "exercise"]),
                    "reason": n.get("reason", ""),
                    "resources": n.get("resources", []) or [],   # 节点学习资源（用户添加/确认落库）
                    "daily_logs": [],   # 日计划：用户自己记录每天学了什么+打钩（不再 AI 预拆日任务）
                })
        else:
            nodes = [{"node_id": f"step_{s['stage']:02d}", "title": s["title"],
                      "description": s["description"], "estimated_days": s["estimated_days"],
                      "resource_types": ["lecture", "exercise", "oj"],
                      "reason": s.get("expected_outcome", ""),
                      "resources": [], "daily_logs": []} for s in stages]
        feedback = collected.get("feedback")
        draft = {
            "draft_id": f"draft_{uuid.uuid4().hex[:8]}",
            "student_id": student_id,
            "topic": topic,
            "collected": collected,
            "path_name": plan.get("path_name", f"{subject}学习路径"),
            "overall_goal": plan.get("overall_goal", f"系统掌握{subject}"),
            "goal": f"系统掌握{subject}",
            "market_demand": plan.get("market_demand", ""),
            "total_duration_days": total_days,
            "daily_minutes": daily_minutes,
            "stages": stages,
            "nodes": nodes,
            "status": "draft",
            "version": 1,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if feedback:
            draft["revision_reason"] = feedback
        return draft

    @staticmethod
    def _carry_draft_resources(old_nodes: list, new_nodes: list):
        """把旧草案节点上用户手动加的 resources 复制到新草案对应节点。
        按 node_id 精确匹配，node_id 变了（重新生成）则按索引兜底。
        新节点已有资源时做合并去重，避免重复。"""
        if not old_nodes or not new_nodes:
            return
        old_map = {}
        for i, n in enumerate(old_nodes):
            res = n.get("resources") or []
            if res:
                key = n.get("node_id") or f"idx_{i}"
                old_map[key] = res
        if not old_map:
            return
        for i, n in enumerate(new_nodes):
            key = n.get("node_id") or f"idx_{i}"
            old = old_map.get(key) or old_map.get(f"idx_{i}")
            if not old:
                continue
            existing = n.get("resources") or []
            n["resources"] = existing + [r for r in old if r not in existing]

    # 常见科目的兜底阶段（LLM 失败/超时时用，避免「基础入门/综合提升」泛标题）
    # 每阶段 points 写 8~11 个详细知识点（细到函数/方法/概念），与模板一致
    SUBJECT_STAGE_MAP: dict[str, list[dict]] = {
        "sql": [
            {"title": "数据库基础与建表", "points": [
                "数据库与表的概念", "主键/外键/唯一约束", "CREATE TABLE 建表",
                "INSERT/UPDATE/DELETE", "数据类型 INT/VARCHAR/DECIMAL",
                "NOT NULL/DEFAULT 默认值", "ALTER TABLE 改表结构", "DROP/TRUNCATE",
                "DISTINCT 去重", "LIKE/IN/BETWEEN 条件", "日期函数 NOW/DATE_FORMAT"]},
            {"title": "单表查询与过滤", "points": [
                "SELECT 基础列/别名", "WHERE 比较与逻辑运算", "ORDER BY 排序",
                "LIMIT 分页", "IN/NOT IN", "LIKE 通配符 %/_",
                "IS NULL / IS NOT NULL", "CASE WHEN 条件分支",
                "字符串 CONCAT/SUBSTR/REPLACE", "数值 ROUND/ABS"]},
            {"title": "多表连接查询", "points": [
                "INNER JOIN 内连接", "LEFT JOIN 左连接", "RIGHT JOIN 右连接",
                "FULL/OUTER JOIN 全连接", "USING / ON 关联条件",
                "多表连接顺序与效率", "自连接", "UNION/UNION ALL",
                "去重聚合前的连接陷阱", "连接与子查询选择"]},
            {"title": "分组聚合", "points": [
                "GROUP BY 分组", "聚合函数 COUNT/SUM/AVG", "MIN/MAX",
                "HAVING 过滤分组", "GROUP BY + WHERE 顺序", "多列分组",
                "聚合去重 COUNT(DISTINCT)", "GROUP_CONCAT", "ROLLUP 小计",
                "聚合结果与 JOIN 结合"]},
            {"title": "窗口函数与高级查询", "points": [
                "ROW_NUMBER 排名", "RANK/DENSE_RANK", "LAG/LEAD 前后行",
                "SUM OVER 累计", "PARTITION BY 分组窗口", "CTE WITH 子句",
                "子查询标量/行/表", "EXISTS / NOT EXISTS", "索引概念与执行计划",
                "SQL 优化：避免全表扫描"]},
            {"title": "综合实战", "points": [
                "业务指标口径定义", "留存/转化率 SQL", "排行榜与 TopN",
                "同比/环比计算", "多表业务分析题", "索引设计与慢查询排查",
                "牛客 SQL 题库刷题", "真题综合查询练习", "SQL 与数据分析报告结合"]},
        ],
        "python数据分析": [
            {"title": "pandas 基础", "points": [
                "Series/DataFrame 结构", "pd.read_csv/read_excel 读入",
                "df.head/df.info/df.describe", "行列索引与取值",
                "loc/iloc 切片选择", "布尔索引过滤", "新增/删除列",
                "rename/reindex 改索引", "to_csv/to_excel 导出", "dtype 类型与 astype"]},
            {"title": "数据清洗", "points": [
                "isnull/notnull 缺失检测", "dropna 删除缺失", "fillna 填充缺失",
                "duplicated 重复检测", "drop_duplicates 去重", "str 文本方法",
                "类型转换 astype/to_datetime", "异常值 3σ/IQR 处理",
                "apply/applymap 逐行处理", "自定义清洗函数"]},
            {"title": "分组聚合", "points": [
                "groupby 分组", "agg 多指标聚合", "merge 按列合并",
                "concat 纵向拼接", "join 按索引合并", "pivot/pivot_table 透视",
                "melt 长表转换", "分组内排序 sort_values", "apply 分组后自定义计算",
                "聚合结果重置索引 reset_index"]},
            {"title": "数据可视化", "points": [
                "Matplotlib 基础绘图", "plt.plot/scatter/bar/hist", "Seaborn 统计图",
                "箱线图/热力图", "设置标题/坐标轴/图例", "多子图 subplots",
                "中文乱码处理", "图表配色与风格", "图保存 savefig",
                "ECharts 交互式图表入门"]},
            {"title": "综合实战", "points": [
                "分析目标拆解", "真实数据集探索", "完整 EDA 流程",
                "业务问题 → 指标 → 分析", "图表讲故事的排版",
                "分析报告结论输出", "PPT/文档沉淀", "常见数据题思路总结",
                "简历项目复盘"]},
        ],
        "excel": [
            {"title": "Excel 基础操作", "points": [
                "单元格引用 相对/绝对", "公式基础 =+−*/", "自动填充与序列",
                "工作表管理", "条件格式基础", "数据验证下拉",
                "冻结窗格/排序", "选择性粘贴", "查找替换与定位", "视图与打印设置"]},
            {"title": "函数与透视表", "points": [
                "VLOOKUP 精确/模糊匹配", "IF/IFS 条件判断", "SUMIFS/COUNTIFS",
                "SUM/AVERAGE/MAX/MIN", "LEFT/RIGHT/MID 文本截取",
                "数据透视表创建", "透视表行/列/值字段", "透视表筛选与切片器",
                "透视表分组统计", "计算字段"]},
            {"title": "数据清洗", "points": [
                "分列（分隔符/固定宽度）", "删除重复值", "TRIM 去空格",
                "TEXT 格式转换", "REPLACE/SUBSTITUTE", "CONCATENATE/& 拼接",
                "日期与时间函数", "错误值处理 IFERROR", "查找定位异常值",
                "Power Query 入门"]},
            {"title": "图表可视化", "points": [
                "柱状图/折线图/饼图", "复合图表", "趋势线与误差线",
                "条件格式数据条/色阶", "迷你图 Sparkline", "仪表盘布局",
                "图表联动与动态区域", "KPI 指标卡", "配色与信息层级", "数据故事化呈现"]},
            {"title": "综合实战", "points": [
                "业务报表模板搭建", "自动化：录制宏入门", "VBA 基础录制回放",
                "数据看板设计", "周报/月报自动化", "多表合并分析",
                "Excel 常见面试题", "真实业务数据演练"]},
        ],
        "统计学": [
            {"title": "描述性统计", "points": [
                "均值/中位数/众数", "方差与标准差", "四分位数与 IQR",
                "分布形态 偏度/峰度", "频率分布表与直方图", "箱线图解读",
                "协方差与相关系数", "标准化 Z-score", "统计量计算工具",
                "数据分布的实际含义"]},
            {"title": "概率论基础", "points": [
                "随机事件与样本空间", "条件概率与独立性", "全概率公式",
                "贝叶斯公式", "随机变量离散/连续", "期望与方差",
                "二项分布/泊松分布", "正态分布与 68-95-99.7", "大数定律",
                "中心极限定理"]},
            {"title": "推断统计", "points": [
                "抽样分布与标准误", "点估计与估计量性质", "置信区间",
                "假设检验步骤", "t 检验：单样本/独立/配对", "卡方检验",
                "p 值与两类错误", "检验功效与样本量", "A/B 测试设计",
                "显著性结果解读"]},
            {"title": "回归分析", "points": [
                "相关系数与显著性检验", "散点图与关系可视化", "一元线性回归",
                "最小二乘估计", "R² 拟合优度", "回归系数检验与置信区间",
                "多元线性回归", "多重共线性与变量选择", "残差诊断",
                "虚拟变量处理分类特征"]},
            {"title": "综合实战", "points": [
                "统计分析报告撰写", "Python/SQL 统计计算", "Excel 统计分析",
                "假设检验实战案例", "回归分析实战", "统计在业务中的落地",
                "真题演练与查漏补缺"]},
        ],
        "机器学习": [
            {"title": "Python 与 NumPy 基础", "points": [
                "Python 语法基础", "NumPy 数组创建", "数组索引与切片",
                "数组运算与广播", "NumPy 统计函数", "数据标准化",
                "数据划分 train_test_split", "Pandas 数据准备", "特征矩阵构建",
                "模型验证流程"]},
            {"title": "线性回归", "points": [
                "线性模型原理", "最小二乘法", "梯度下降", "学习率与收敛",
                "损失函数 MSE", "R² 与评估指标", "sklearn LinearRegression",
                "多项式特征", "正则化 Ridge/Lasso", "过拟合与欠拟合"]},
            {"title": "分类算法", "points": [
                "逻辑回归", "决策树与分裂准则", "KNN 近邻",
                "朴素贝叶斯", "支持向量机概念", "混淆矩阵",
                "精确率/召回率/F1", "ROC/AUC", "sklearn 分类器调用",
                "样本不平衡处理"]},
            {"title": "模型评估与调优", "points": [
                "交叉验证 K-fold", "训练集/验证集/测试集", "过拟合现象与对策",
                "超参数调优 GridSearchCV", "特征选择", "特征重要性",
                "正则化强度调节", "集成学习 Bagging/Boosting", "随机森林",
                "XGBoost/LightGBM 入门"]},
            {"title": "综合实战", "points": [
                "完整项目流程", "数据清洗与特征工程", "基线模型",
                "模型对比与选择", "结果可视化与汇报", "模型部署概念",
                "Kaggle 入门赛", "项目文档与复盘"]},
        ],
        "数据可视化": [
            {"title": "可视化工具基础", "points": [
                "ECharts 基础配置", "Matplotlib 绘图", "Seaborn 统计图",
                "图表数据格式", "渲染容器与初始化", "常见图表类型",
                "坐标轴/图例/标题设置", "数据加载与转换", "工具与库的选择",
                "开发环境搭建"]},
            {"title": "图表设计", "points": [
                "柱状图/折线图/饼图适用场景", "散点图与气泡图", "热力图与地图",
                "配色方案", "信息层级与留白", "标签与注释",
                "数据-墨水比", "视觉引导", "图表的规范性", "误导性图表识别"]},
            {"title": "交互式可视化", "points": [
                "鼠标事件 tooltip 联动", "图例切换显隐", "钻取下钻",
                "数据缩放 dataZoom", "动态更新 setOption", "定时刷新数据",
                "联动多个图表", "组件化封装", "大屏布局",
                "性能优化：数据采样"]},
            {"title": "综合实战", "points": [
                "数据看板设计", "业务指标体系可视化", "Dashboard 布局",
                "实时数据接入", "大屏开发实战", "汇报与演示",
                "作品集整理与复盘"]},
        ],
        # 常见非编程科目（不挂 OJ 卡，但兜底阶段也要技能化，别给泛标题）
        "前端": [
            {"title": "HTML 与 CSS 基础", "points": [
                "HTML 标签语义化", "表单与 input 类型", "CSS 选择器",
                "盒模型 margin/padding", "Flex 弹性布局", "Grid 网格布局",
                "定位 position", "响应式媒体查询", "常见样式属性",
                "CSS 变量与优先级"]},
            {"title": "JavaScript 核心", "points": [
                "变量与数据类型", "函数声明与箭头函数", "数组方法 map/filter/reduce",
                "对象与解构", "模板字符串", "事件绑定与冒泡",
                "DOM 操作 querySelector", "定时器与异步 setTimeout",
                "Promise 与 async/await", "fetch 请求数据"]},
            {"title": "框架与组件（Vue/React）", "points": [
                "Vue 实例与模板语法", "响应式数据 ref/reactive", "指令 v-if/v-for",
                "组件 props/emit", "生命周期钩子", "路由 vue-router",
                "状态管理 Pinia", "Vue CLI/Vite 脚手架", "组件通信方式",
                "插槽与动态组件"]},
            {"title": "工程化与项目实战", "points": [
                "模块化 ES Module", "打包工具 Vite/Webpack", "Git 常用命令",
                "代码规范 ESLint", "接口联调与调试", "部署上线流程",
                "移动端适配", "项目目录结构", "实战页面还原",
                "性能优化：懒加载"]},
            {"title": "综合实战", "points": [
                "完整项目：待办/商城", "组件库使用 Element Plus", "数据请求与渲染",
                "交互细节打磨", "响应式适配多端", "代码 review",
                "简历项目沉淀与复盘"]},
        ],
        "物理": [
            {"title": "实验原理与装置认知", "points": [
                "实验目的与原理", "实验器材认知", "刻度尺/游标卡尺读数",
                "螺旋测微器读数", "误差概念 系统/偶然", "有效数字",
                "秒表读数", "实验步骤书写", "安全操作规范", "实验报告结构"]},
            {"title": "力学基础", "points": [
                "质点与参考系", "位移与路程", "速度与加速度",
                "匀变速直线运动公式", "v-t/s-t 图像分析", "自由落体运动",
                "受力分析步骤", "牛顿第二定律 F=ma", "摩擦力 静/滑动",
                "力的合成与分解"]},
            {"title": "能量与动量", "points": [
                "功 W=Fs", "功率", "动能定理", "重力势能与弹性势能",
                "机械能守恒", "动量 p=mv", "动量守恒定律", "弹性/非弹性碰撞",
                "冲量 I=Ft", "能量转化与守恒"]},
            {"title": "实验设计与数据处理", "points": [
                "控制变量法", "图像法处理数据", "逐差法求加速度",
                "误差分析", "多次测量取平均", "数据拟合直线",
                "实验改进思路", "实验结论表述", "典型实验：验证牛顿第二定律",
                "真题实验题演练"]},
            {"title": "综合实战", "points": [
                "高考真题演练", "实验报告完整撰写", "知识体系梳理",
                "错题整理与复盘", "限时训练"]},
        ],
        "化学": [
            {"title": "化学基础与实验安全", "points": [
                "元素符号与化合价", "化学式书写", "常见仪器用途",
                "实验操作规范", "危险品标识", "溶液配制步骤",
                "分离提纯 过滤/蒸发", "量筒/托盘天平使用", "实验记录",
                "事故应急处理"]},
            {"title": "化学反应原理", "points": [
                "化学方程式配平", "质量守恒定律", "化学平衡移动",
                "勒夏特列原理", "酸碱中和反应", "pH 与指示剂",
                "氧化还原反应", "电子转移", "离子方程式书写",
                "反应速率影响因素"]},
            {"title": "物质结构与性质", "points": [
                "原子结构与核外电子排布", "元素周期律", "化学键 离子/共价",
                "分子式与结构式", "晶体类型概念", "金属活动性顺序",
                "常见物质性质", "气体摩尔体积", "物质的量 n=m/M",
                "浓度计算 c=n/V"]},
            {"title": "综合实战", "points": [
                "化学计算题", "实验设计题", "真题演练",
                "知识框架梳理", "错题复盘"]},
        ],
        "数学": [
            {"title": "基础概念与计算", "points": [
                "集合与运算", "不等式性质", "一元二次方程",
                "绝对值与幂运算", "指数/对数运算", "实数与数轴",
                "因式分解", "分式化简", "基础代数变形", "计算准确率训练"]},
            {"title": "几何与三角", "points": [
                "平面几何定理", "三角形全等/相似", "圆的性质",
                "三角函数定义", "正弦/余弦定理", "弧度制",
                "解析几何：直线方程", "圆锥曲线概念", "几何证明思路",
                "常见辅助线"]},
            {"title": "微积分初步", "points": [
                "函数极限概念", "极限运算法则", "导数定义",
                "求导法则", "常见函数导数", "导数与单调性",
                "极值与最值", "不定积分概念", "定积分入门",
                "微积分应用：变速直线运动"]},
            {"title": "综合实战", "points": [
                "综合题型训练", "应用建模题", "真题演练",
                "答题规范", "错题复盘"]},
        ],
        "英语": [
            {"title": "词汇与语法", "points": [
                "高频核心词汇", "词根词缀记忆法", "名词单复数",
                "动词时态 8 大时态", "被动语态", "非谓语动词",
                "定语从句", "状语从句", "虚拟语气",
                "主谓一致"]},
            {"title": "听力与口语", "points": [
                "精听训练法", "连读与弱读", "音标与发音",
                "日常会话句型", "数字/时间听辨", "听力笔记技巧",
                "影子跟读法", "口语话题模板", "自我介绍", "情景对话练习"]},
            {"title": "阅读与写作", "points": [
                "精读与泛读", "长难句分析", "段落主旨把握",
                "细节题定位", "推断题方法", "写作结构 总分总",
                "议论文模板", "书信/邮件格式", "过渡词使用", "常见写作主题"]},
            {"title": "综合实战", "points": [
                "四六级/高考真题", "限时模拟测试", "作文批改润色",
                "错题与生词本", "查漏补缺"]},
        ],
        "java": [
            {"title": "Java 语法与面向对象", "points": [
                "JDK/IDE 环境搭建", "变量与基本数据类型", "运算符与表达式",
                "if/switch 分支", "for/while 循环", "数组与增强 for",
                "类与对象", "封装/继承/多态", "构造方法与 this/super",
                "static/final 关键字", "访问修饰符"]},
            {"title": "集合与常用类", "points": [
                "ArrayList 与 LinkedList", "HashSet 与去重", "HashMap/HashMap 遍历",
                "Collections 工具类", "泛型 <T>", "String/StringBuilder",
                "String 常用方法", "包装类与自动装箱", "Math/Random 常用类",
                "日期与时间 LocalDateTime"]},
            {"title": "IO、异常与常用工具", "points": [
                "异常体系 try-catch-finally", "自定义异常", "File 类与目录操作",
                "字节流 InputStream/OutputStream", "字符流 Reader/Writer",
                "缓冲流 BufferedReader", "对象流与序列化", "Properties 配置读取",
                "日志输出规范", "单元测试 JUnit 入门"]},
            {"title": "多线程与网络编程", "points": [
                "线程创建 Thread/Runnable", "线程生命周期", "synchronized 同步",
                "锁与 volatile", "线程池 ExecutorService", "Callable/Future",
                "TCP Socket 编程", "HTTP 客户端", "并发安全集合",
                "Lambda 与函数式接口"]},
            {"title": "综合实战", "points": [
                "面向对象综合练习", "集合+IO 小项目", "控制台学生管理系统",
                "牛客 Java 题库刷题", "常见面试题", "代码规范与重构",
                "项目复盘与简历沉淀"]},
        ],
    }

    @staticmethod
    def _default_plan(topic: str, subject: str = "", total_days: int = 60) -> dict:
        s = subject or "该科目"
        low = s.lower()
        titles = None
        for key, stages in WebPathPlanAgent.SUBJECT_STAGE_MAP.items():
            if key in low:
                titles = stages
                break
        if not titles:
            # 未知科目 → 通用兜底（阶段标题仍带科目前缀，知识点给足可练的细项）
            # 带 _fallback 标记：不给这类泛阶段挂 OJ 卡（避免「牛客/LeetCode 错题链接」）
            titles = [
                {"title": f"{s} · 基础入门", "_fallback": True, "points": [
                    "核心概念与术语", "入门工具与软件", "基本操作流程",
                    "常见术语表", "经典入门案例", "学习资源整理"]},
                {"title": f"{s} · 核心技能", "_fallback": True, "points": [
                    "核心方法掌握", "常用技巧与套路", "典型操作练习",
                    "易错点规避", "专项练习若干", "阶段性小结"]},
                {"title": f"{s} · 综合实战", "_fallback": True, "points": [
                    "综合题目演练", "真实场景应用", "常见问题排查",
                    "作品/成果产出", "复盘与查漏补缺", "进阶方向梳理"]},
            ]

        n = len(titles)
        base = max(5, total_days // n)
        stages = []
        for i, t in enumerate(titles):
            days = total_days - base * (n - 1) if i == n - 1 else base
            days = max(3, days)
            stages.append({
                "stage": i + 1,
                "title": t["title"],
                "description": f"系统学习{s}的「{t['title']}」，配练习巩固",
                "estimated_days": days,
                "focus_points": t["points"],
                "expected_outcome": f"掌握{s}·{t['title']}并能独立应用",
                "_fallback": bool(t.get("_fallback")),
            })
        return {
            "path_name": f"{s}学习路径",
            "overall_goal": f"系统掌握{s}",
            "market_demand": "",
            "stages": stages,
            "nodes": [],
        }

    async def _attach_stage_cards(self, draft: dict, subject: str) -> dict:
        """每个阶段按重点技能找官方 OJ 练习卡（无真实命中时用平台官方搜索页兜底，链接永远可点）。

        只有编程/CS 类科目才挂卡——LeetCode/牛客等都是编程题库，非编程科目（物理/化学/英语…）
        挂上去是错题链接，直接跳过（宁可没卡，也不挂牛客物理题）。"""
        if not self._is_programming_subject(subject):
            logger.info(f"[WebPathPlan] 科目「{subject}」非编程类，不挂 OJ 练习卡")
            for stage in draft.get("stages", []):
                stage["practice_cards"] = []
            return draft

        from core.capabilities.impl.practice_search import practice_card_searcher
        for stage in draft.get("stages", []):
            # 通用兜底阶段（_fallback 标记，如「某科目 · 基础入门」泛阶段）：不挂 OJ 卡，
            # 避免把「牛客/LeetCode 错题链接」挂到没有具体知识点的阶段上
            if stage.get("_fallback"):
                stage["practice_cards"] = []
                continue
            kps = stage.get("focus_points") or []
            if not kps:
                stage["practice_cards"] = []
                continue
            cards: list[dict] = []
            for kp in kps[:3]:
                try:
                    got = await practice_card_searcher.structure_cards([], f"{subject} {kp}", [kp], count=2)
                    cards.extend(got or [])
                except Exception as e:
                    logger.warning(f"[WebPathPlan] 阶段练习卡失败 {kp}: {e}")
            # 去重（同平台同链接）
            seen, dedup = set(), []
            for c in cards:
                key = (c.get("platform"), c.get("link"))
                if key in seen:
                    continue
                seen.add(key)
                dedup.append(c)
            stage["practice_cards"] = dedup[:4]
        return draft

    async def process(self, *args, **kwargs):
        """实现基类抽象方法"""
        return await self.generate_draft(
            student_id=kwargs.get("student_id", "anonymous"),
            topic=kwargs.get("topic", ""),
            collected=kwargs.get("collected", {}),
        )


web_path_plan_agent = WebPathPlanAgent()

__all__ = ["WebPathPlanAgent", "web_path_plan_agent", "REQUIRED_INFO", "INFO_LABELS"]
