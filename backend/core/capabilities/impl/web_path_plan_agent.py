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
- 宏观 + 微观：stages（阶段）+ nodes（日计划，split_daily_tasks 拆分）
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
from core.models.profile import profile_manager
from core.models.learning_path_data import save_path, split_daily_tasks

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

    fallback_model = "glm-4.5-flash"

    def __init__(self):
        super().__init__(
            name="WebPathPlanAgent",
            model_name="glm-4.7-flash",
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
    def _missing_info(collected: dict) -> list[str]:
        """只问一个：具体科目。其余信息（时长/周期/基础）用画像或合理默认。"""
        if not (collected.get("subject") or collected.get("role") or collected.get("target")):
            return ["subject"]
        return []

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

    async def start_conversation(self, student_id: str, topic: str) -> dict:
        """Stage 1：画像起步 + 识别科目。

        优先级（用户反馈「sql 不就是一个科目吗，别问范围比较大」）：
        ① topic 本身就是具体科目（命中关键词）→ 不再问，直接联网出草案；
        ② 画像里有方向（目标/兴趣/薄弱点能抠出科目）→ 提取出来让用户确认（confirm_subject）；
        ③ 都推不出 → 才问开放问题「想具体学哪个科目？」。
        联网搜索只在要出草案时才做（缺科目时先问，Stage2 拿到科目后按科目重搜）。"""
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

        subject, concrete = self._derive_subject(topic, ctx)
        if concrete:
            # ① topic 本身是具体科目 → 直接联网出草案（不再问）
            collected["subject"] = subject
            collected["long_term_goal"] = collected.get("long_term_goal") or subject
            target = (ctx.get("long_term_goal") or ctx.get("short_term_goal")
                      or ctx.get("goal_attribute") or subject)
            web = await self._search_market_and_resources(topic, target)
            collected["market"] = web.get("market", [])
            collected["resources"] = web.get("resources", [])
            return await self.generate_draft(student_id, topic, collected)

        if subject:
            # ② 画像里有方向 → 提取出来让用户确认，而不是开放提问
            return {
                "stage": 1,
                "need_info": True,
                "confirm_subject": subject,
                "questions": [self._subject_confirm_label(topic, subject, ctx)],
                "missing_keys": ["subject"],
                "collected": collected,
                "topic": topic,
            }

        # ③ 完全推不出科目 → 问开放问题
        return {
            "stage": 1,
            "need_info": True,
            "questions": [INFO_LABELS["subject"]],
            "missing_keys": ["subject"],
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
        return await self.generate_draft(student_id, topic, collected)

    # ==================== Stage 3：草案 → 确认 → 存储 ====================

    async def generate_draft(self, student_id: str, topic: str, collected: dict) -> dict:
        """生成路径草案（暂存 draft 文件，不落学习路径存储）"""
        daily_hours = self._parse_hours(
            collected.get("daily_hours") or collected.get("profile", {}).get("daily_hours"))
        daily_minutes = int(daily_hours * 60)
        subject = (collected.get("subject") or collected.get("role") or collected.get("target")
                   or collected.get("long_term_goal") or "该科目")
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
            "不要用「基础入门」「综合提升」这类泛标题。每个阶段的 focus_points 写该技能下的重点知识点，"
            "expected_outcome 写清阶段结束能独立做什么。"
        )

        ctx_lines = []
        if profile.get("mastered"): ctx_lines.append(f"已掌握: {', '.join(profile['mastered'][:6])}")
        if profile.get("weak"): ctx_lines.append(f"薄弱: {', '.join(profile['weak'][:4])}")
        if profile.get("interests"): ctx_lines.append(f"兴趣: {', '.join(profile['interests'][:4])}")
        if profile.get("cognitive_style"): ctx_lines.append(f"风格: {profile['cognitive_style']}")
        if profile.get("preferred_pace"): ctx_lines.append(f"节奏: {profile['preferred_pace']}")
        if ctx_lines:
            parts.append("学生画像：\n" + "\n".join(ctx_lines))

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
            # 带修改意见 → 重新生成草案
            topic = draft.get("topic", "")
            collected = draft.get("collected", {})
            collected["feedback"] = feedback.strip()
            logger.info(f"[WebPathPlan] 用户要求修改: {feedback.strip()}")
            new_draft = await self.generate_draft(student_id, topic, collected)
            # 把 feedback 带进新草案说明
            new_draft["path"]["revision_reason"] = feedback.strip()
            self._save_draft(student_id, new_draft["path"])
            return {
                "ok": True, "revised": True,
                "draft_id": new_draft["draft_id"],
                "path": new_draft["path"],
                "message": "已根据你的修改意见重新生成，请再次确认。",
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

        硬性截止：整个生成（含重试/降级）最多 70s。每次调用都用 asyncio.wait_for 包住，
        超时即取消并截断 → 返回空走 _default_plan 确定性兜底。
        加上联网 6s，请求最坏 ~78s，保证不会拖到前端 120s 超时。"""
        import asyncio
        last_err = None
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 70.0

        def _remain() -> float:
            return deadline - loop.time()

        async def _call_with_timeout(factory, label: str):
            """在剩余预算内调用异步工厂；预算耗尽直接抛 TimeoutError"""
            remain = _remain()
            if remain <= 0:
                raise asyncio.TimeoutError()
            return await asyncio.wait_for(factory(), timeout=remain)

        for attempt in range(2):
            try:
                resp = await _call_with_timeout(
                    lambda: self.generate(prompt, max_tokens=8192), "主模型")
                if resp:
                    return resp
                last_err = RuntimeError("模型返回为空")
            except asyncio.TimeoutError:
                last_err = RuntimeError("模型响应超时")
                break
            except Exception as e:
                last_err = e
                if "429" in str(e) or "1305" in str(e):
                    wait = min(1.5 * (attempt + 1), max(0.0, _remain() - 1.0))
                    if wait <= 0:
                        break
                    logger.warning(f"[WebPathPlan] 模型限流(429)，{wait:.1f}s 后重试 ({attempt + 1}/2)")
                    await asyncio.sleep(wait)
                    continue
                break

        # 降级模型兜底（预算还剩才试）
        if _remain() > 2.0:
            try:
                messages = self.build_messages(prompt)
                resp = await _call_with_timeout(
                    lambda: self._fallback_client().chat(messages, temperature=self.temperature),
                    "降级模型")
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
        """把 '60'/'60天'/'2个月' 等解析为天数"""
        import re
        if not cycle:
            return 60
        s = str(cycle)
        m = re.search(r"(\d+)\s*个月", s)
        if m:
            return int(m.group(1)) * 30
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
                })
        else:
            nodes = [{"node_id": f"step_{s['stage']:02d}", "title": s["title"],
                      "description": s["description"], "estimated_days": s["estimated_days"],
                      "resource_types": ["lecture", "exercise", "oj"],
                      "reason": s.get("expected_outcome", "")} for s in stages]

        nodes = split_daily_tasks(nodes, total_days, daily_minutes)
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

    # 常见科目的兜底阶段（LLM 失败/超时时用，避免「基础入门/综合提升」泛标题）
    SUBJECT_STAGE_MAP: dict[str, list[dict]] = {
        "sql": [
            {"title": "数据库基础与建表", "points": ["SQL 语法", "CREATE/INSERT", "数据类型"]},
            {"title": "单表查询与过滤", "points": ["SELECT", "WHERE", "ORDER BY/LIMIT"]},
            {"title": "多表连接查询", "points": ["JOIN", "LEFT/RIGHT JOIN", "关联条件"]},
            {"title": "分组聚合", "points": ["GROUP BY", "HAVING", "聚合函数"]},
            {"title": "窗口函数与高级查询", "points": ["ROW_NUMBER", "LAG/LEAD", "CTE"]},
            {"title": "综合实战", "points": ["业务查询", "性能优化", "索引"]},
        ],
        "python数据分析": [
            {"title": "pandas 基础", "points": ["DataFrame", "Series", "读写数据"]},
            {"title": "数据清洗", "points": ["缺失值", "重复值", "类型转换"]},
            {"title": "分组聚合", "points": ["groupby", "agg", "merge/join"]},
            {"title": "数据可视化", "points": ["Matplotlib", "Seaborn", "图表解读"]},
            {"title": "综合实战", "points": ["分析报告", "真实数据集", "结论输出"]},
        ],
        "excel": [
            {"title": "Excel 基础操作", "points": ["公式", "引用", "常用函数"]},
            {"title": "函数与透视表", "points": ["VLOOKUP", "IF/SUMIFS", "数据透视"]},
            {"title": "数据清洗", "points": ["分列", "去重", "文本函数"]},
            {"title": "图表可视化", "points": ["图表类型", "条件格式", "仪表盘"]},
            {"title": "综合实战", "points": ["业务报表", "自动化", "宏"]},
        ],
        "统计学": [
            {"title": "描述性统计", "points": ["均值/中位数", "方差/标准差", "分布形态"]},
            {"title": "概率论基础", "points": ["随机变量", "常见分布", "大数定律"]},
            {"title": "推断统计", "points": ["抽样分布", "假设检验", "置信区间"]},
            {"title": "回归分析", "points": ["线性回归", "相关系数", "残差分析"]},
            {"title": "综合实战", "points": ["统计分析报告", "工具应用", "结论解读"]},
        ],
        "机器学习": [
            {"title": "Python 与 NumPy 基础", "points": ["Python 语法", "NumPy", "数据准备"]},
            {"title": "线性回归", "points": ["最小二乘", "梯度下降", "评估指标"]},
            {"title": "分类算法", "points": ["逻辑回归", "决策树", "KNN"]},
            {"title": "模型评估与调优", "points": ["交叉验证", "过拟合", "超参数"]},
            {"title": "综合实战", "points": ["完整项目", "特征工程", "结果汇报"]},
        ],
        "数据可视化": [
            {"title": "可视化工具基础", "points": ["ECharts/Matplotlib", "图表语法", "数据准备"]},
            {"title": "图表设计", "points": ["图表类型", "配色", "信息层级"]},
            {"title": "交互式可视化", "points": ["联动", "钻取", "动态更新"]},
            {"title": "综合实战", "points": ["数据看板", "业务可视化", "汇报"]},
        ],
        # 常见非编程科目（不挂 OJ 卡，但兜底阶段也要技能化，别给泛标题）
        "物理": [
            {"title": "实验原理与装置认知", "points": ["牛顿第二定律", "气垫导轨", "光电门"]},
            {"title": "力学基础", "points": ["运动学", "受力分析", "牛顿定律应用"]},
            {"title": "能量与动量", "points": ["功与能", "动能定理", "动量守恒"]},
            {"title": "实验设计与数据处理", "points": ["控制变量法", "误差分析", "数据拟合"]},
            {"title": "综合实战", "points": ["实验报告", "真题演练", "知识体系"]},
        ],
        "化学": [
            {"title": "化学基础与实验安全", "points": ["元素与化合物", "实验器材", "安全规范"]},
            {"title": "化学反应原理", "points": ["化学平衡", "酸碱反应", "氧化还原"]},
            {"title": "物质结构与性质", "points": ["原子结构", "化学键", "周期律"]},
            {"title": "综合实战", "points": ["实验设计", "计算题", "知识体系"]},
        ],
        "数学": [
            {"title": "基础概念与计算", "points": ["代数运算", "函数基础", "方程"]},
            {"title": "几何与三角", "points": ["平面几何", "三角函数", "解析几何"]},
            {"title": "微积分初步", "points": ["极限", "导数", "积分"]},
            {"title": "综合实战", "points": ["综合题型", "应用建模", "真题演练"]},
        ],
        "英语": [
            {"title": "词汇与语法", "points": ["核心词汇", "语法体系", "长难句"]},
            {"title": "听力与口语", "points": ["精听", "发音", "日常会话"]},
            {"title": "阅读与写作", "points": ["精读", "写作结构", "表达技巧"]},
            {"title": "综合实战", "points": ["真题", "模拟测试", "查漏补缺"]},
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
            # 未知科目 → 通用兜底（阶段标题仍带科目前缀）
            titles = [
                {"title": f"{s} · 基础入门", "points": ["核心概念", "基础工具"]},
                {"title": f"{s} · 核心技能", "points": ["核心技能", "练习"]},
                {"title": f"{s} · 综合实战", "points": ["综合", "实战"]},
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
