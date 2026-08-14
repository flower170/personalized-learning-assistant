"""
对话式画像构建智能体 (ProfileChatAgent)
采用定位式分步对话模式自动采集学生信息，生成 ≥6 维度动态学生画像。
全部对话上下文走 Redis 缓存，支持会话持久、重启不丢失。

异常容错:
  - 所有 Redis 操作带 try-except 保护，失败不阻断流程
  - 所有字典取值使用 .get() 兜底
  - JSON 解析带多层容错
  - dims_done 非列表保护
  - 批量 Redis 写入减少 IO 往返
"""
import asyncio
import json
import logging
import os
import re
from typing import Optional

from core.capabilities.impl.base_agent import BaseAgent
from core.models.schemas import (
    StudentProfile, RadarScores,
    ProfileChatProgress,
)
from core.models.profile import (
    profile_manager, PROFILE_EXTRACTION_SYSTEM_PROMPT,
    _UNSUPPORTED_LEGACY_UPDATE_PROMPT,
)
from services.cache import (
    profile_chat_cache as cache,
    STAGE_BASE_INFO, STAGE_ACADEMIC, STAGE_DIMENSION, STAGE_COMPLETED,
    STANDARD_DIMS as DIMS_LIST,
)
from core.models.spark_client import SparkAPIError

logger = logging.getLogger(__name__)

# 对话轮：glm-4-flash 非推理快模型；spark-x2-flash 在该账号 401，会静默降级到弱模型 spark-lite
DEFAULT_MODEL = "glm-4-flash"
# 抽取/完成轮：长输出 + 关推理防 token 溢出（见记忆 a3-profile-chat-extraction）
EXTRACT_MODEL = "glm-4.5-flash"
DEFAULT_TEMPERATURE = 0.7

# 画像维度顺序（用于兜底提问与重复检测）
DIM_ORDER = [
    "learning_goals", "goal_attribute", "knowledge_base",
    "cognitive_style", "preferred_pace", "error_prone_areas",
    "interests", "daily_available_hours",
]
DIM_CN = {
    "learning_goals": "学习目标", "goal_attribute": "目标属性",
    "knowledge_base": "知识基础", "cognitive_style": "认知风格",
    "preferred_pace": "学习节奏", "error_prone_areas": "易错短板",
    "interests": "兴趣方向", "daily_available_hours": "每日时长",
}
# 检测到模型重复追问已收集维度时，替换用的确定性兜底问题
FALLBACK_QUESTIONS = {
    "learning_goals": "你目前最想达成的短期学习目标是什么？那长期目标呢？",
    "goal_attribute": "你学这些主要是为了应试、就业、考研，还是自己感兴趣呢？",
    "knowledge_base": "这些知识里，哪些你已经掌握了，哪些还比较薄弱，哪些完全没接触过呢？",
    "cognitive_style": "你平时更喜欢通过看视频、听讲、看书做笔记，还是动手实操来学习呢？",
    "preferred_pace": "你学习的时候更倾向于慢速细学还是快速速成呢？",
    "error_prone_areas": "你在学习过程中，有没有哪些地方经常出错、容易卡住的？",
    "interests": "你平时对哪些领域或方向比较感兴趣呢？",
    "daily_available_hours": "你每天大概能投入多少时间学习呢？",
}

# ======================== 系统提示词 ========================

SYSTEM_PROMPT = """你是一位温和耐心的学情老师，正在用聊天的方式了解一名学生的学习情况，帮他梳理出清晰的学习画像。你不是问卷系统，也不是考官——语气要像班主任私下关心学生那样自然、温和。

## 最高准则（永不违反）
1. 输出必须是纯自然语言、面向学生、绝对不含 JSON / 大括号 / 代码块 / 结构化字段名
2. 每次输出严格遵守：一句话自然回应 + 一个单一问题（不允许一次问多个）
3. 绝对禁止出现"你："、"助手："等角色前缀，直接说话
4. 不编造学生没说过的信息，信息不足只追问当前维度一次

## 要采集的六大维度（一条一条来，别跳来跳去）
1. 学习目标：短期目标 + 长期目标（如想做成什么）
2. 目标属性：学这些是为了 应试 / 就业 / 考研 / 自学兴趣
3. 知识基础：哪些已经掌握、哪些还薄弱、哪些完全没接触
4. 认知风格：更喜欢 看视频/图（视觉）、听讲（听觉）、读书写笔记（读写）、还是动手实操（动觉）
5. 兴趣方向：喜欢什么领域 / 想做什么方向的应用
6. 易错短板：哪些地方老出错、容易卡住
（还可以顺带了解：学习节奏是慢速细学还是快速速成、每天能投入多少时间）

## 信息采集的"指南针"——完备率驱动（Backend 已给出）
Backend 会给你 8 个维度的当前完备率（0% ~ 100%）：
 knowledge_base 知识基础(cognitive_style 认知风格, preferred_pace 节奏, error_prone_areas 易错, interests 兴趣, learning_goals 目标, goal_attribute 目标属性, daily_available_hours 每日时长)
以及一个 overall 总完备率。
你的决策顺序（硬性）：
  a) 如果 overall < 100%：永远先补 完备率最低 的那个维度；有并列时，顺序为 learning_goals → goal_attribute → knowledge_base → cognitive_style → preferred_pace → error_prone_areas → interests → daily_available_hours
  b) 如果 overall == 100% 并且对话已经完整：输出固定一句话"✅ 你的个性化画像已构建完成！"，然后不再追问

## 采集节奏（软指引，最终仍以完备率为准）
先聊聊学习目标（短期+长期），再自然过渡到学习进度 / 已掌握 / 薄弱点，然后把剩下的维度一个个补齐。收尾时（overall=100% 或 asked_count >= 12）仅输出"✅ 你的个性化画像已构建完成！"

## 语言与风格
- 像聊家常一样自然，用温和、关心的语气，偶尔共情（"听起来数组确实容易卡住不少人"）。不要审问、不要连珠炮式提问、不要像做问卷。
- 问题要贴合学生专业/年级。举例：对"大二计科"不要问"你的植物学进展怎样"，而要问"目前面向对象、数据结构、计网这些核心课，学得怎么样了？"
- 学生回答太短/太模糊时，可以顺着他的话追问一次；超过一次就跳过，后续有机会再补。
- 【禁止模板化，最高优先级】绝对禁止以"很好""不错""好的""明白了""了解"等客套词开头；不要每轮都复述学生原话；不要用同一句式开头。开头要直接回应学生刚说的内容（"「增删改查」这一块算是把 SQL 最常用的一层拿下了"），或自然承接（"那你平时做数据分析，最想处理的是什么场景？"）。同样的话术在一段对话里不要出现第二次。
"""



class ProfileChatAgent(BaseAgent):
    """对话式画像智能体 — Redis 持久化上下文"""

    def __init__(self):
        super().__init__(
            name="ProfileChatAgent",
            model_name=DEFAULT_MODEL,
            system_prompt=SYSTEM_PROMPT,
            temperature=DEFAULT_TEMPERATURE,
        )

    # ======================== Redis 安全操作辅助 ========================

    @staticmethod
    def _safe_read_context(student_id: str, session_id: str) -> dict:
        """安全读取 Redis 上下文，异常时返回空字典"""
        try:
            return cache.get_full_context(student_id, session_id)
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 读取上下文失败: student={student_id}, session={session_id}, err={e}")
            return {"base_info": {}, "chat_history": [], "collect_progress": {}, "temp_profile_draft": {}}

    @staticmethod
    def _safe_list(val, default=None):
        """确保值是列表类型"""
        if default is None:
            default = []
        if isinstance(val, list):
            return val
        if isinstance(val, (tuple, set)):
            return list(val)
        return default

    @staticmethod
    def _fill_base_info(profile: StudentProfile, base_info: dict, student_id: str) -> bool:
        """
        强制从 Redis base_info 回填四个基础字段。
        逻辑优先级：base_info 字段 > 入参 student_id 兜底
        返回是否发生了变更。
        """
        if not isinstance(profile, StudentProfile):
            return False
        if not isinstance(base_info, dict):
            base_info = {}
        changed = False

        fill_map = {
            "student_id": base_info.get("student_id") or student_id,
            "name": base_info.get("name", ""),
            "grade": base_info.get("grade", ""),
            "major": base_info.get("major", ""),
        }

        for field, val in fill_map.items():
            # 修复：显式检查 None，支持空字符串覆盖
            if val is not None:
                new_val = str(val) if val else ""
                current = getattr(profile, field, None)
                current_str = str(current) if current is not None else ""
                if current_str != new_val:
                    setattr(profile, field, new_val)
                    logger.info(f"[ProfileChatAgent] _fill_base_info: {field} 从 '{current_str}' 更新为 '{new_val}'")
                    changed = True

        return changed

    # ======================== 初始化会话 ========================

    async def init_chat(self, student_id: str, name: str = "",
                         grade: str = "", major: str = "", language: str = "") -> tuple[str, str]:
        """
        初始化画像对话会话。
        返回 (session_id, first_question)
        """
        # 确保基础信息不为空
        safe_name = name or "同学"
        safe_grade = grade or "大一"
        safe_major = major or "学生"

        base_info = {
            "student_id": student_id,
            "name": safe_name,
            "grade": safe_grade,
            "major": safe_major,
        }
        try:
            session_id = cache.init_chat_session(student_id, base_info)
        except Exception as e:
            logger.error(f"[ProfileChatAgent] Redis init_chat_session 失败: {e}")
            # 使用 UUID 作为兜底 session_id
            import uuid
            session_id = uuid.uuid4().hex[:12]

        # 初始化时将基础信息写入画像文件（直接设置，不依赖条件判断）
        try:
            profile = profile_manager.get_profile(student_id)
            profile.student_id = student_id
            profile.name = safe_name
            profile.grade = safe_grade
            profile.major = safe_major
            profile.source = "chat"
            profile.version += 1
            profile_manager.save_profile(profile)
            logger.info(f"[ProfileChatAgent] 初始画像已保存: student_id={student_id}, name={safe_name}")
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 初始画像保存失败: {e}")

        # 生成首轮提问
        context = self._safe_read_context(student_id, session_id)
        prompt = self._build_first_prompt(base_info, context, language)
        try:
            first_question = await self.generate(prompt)
            first_question = self._clean_response(first_question)
        except Exception as e:
            logger.exception(f"[ProfileChatAgent] 首轮提问生成失败")
            first_question = f"你好！你是{grade or ''}{major or ''}专业的学生对吗？很高兴为你构建学习画像。请先说说你的学习目标是什么？"

        # 批量写入 Redis（一次性更新所有字段）
        try:
            history = [{"role": "assistant", "content": first_question}]
            progress = {"stage": STAGE_ACADEMIC, "current_dim": None,
                        "dims_done": [], "asked_count": 1}
            cache.batch_update_session(student_id, session_id, {
                "chat_history": json.dumps(history, ensure_ascii=False),
                "collect_progress": json.dumps(progress, ensure_ascii=False),
            })
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 首轮 Redis 批量写入失败: {e}")

        logger.info(f"[ProfileChatAgent] 会话初始化: student={student_id}, session={session_id}")
        logger.info(f"[DEBUG] init_chat 完成: student_id={student_id}, name={safe_name}")
        return session_id, first_question

    def _build_first_prompt(self, base_info: dict, context: dict, language: str = "") -> str:
        """构建首轮提问 Prompt"""
        grade = base_info.get("grade", "")
        major = base_info.get("major", "")
        name = base_info.get("name", "")

        lang_hint = self._get_language_hint(language)
        greeting = f"学生姓名: {name}" if name else ""
        return (
            f"[系统指令] 你是画像构建助手。\n"
            f"[语言要求] {lang_hint}\n"
            f"[当前阶段] 阶段1-基础信息定位（已完成）→ 阶段2-核心学情问询（开始）\n"
            f"[已有信息] 学号={base_info.get('student_id')}，年级={grade}，专业={major}。{greeting}\n"
            f"[指令] 根据该专业的培养体系，用1句话打招呼并询问学生的短期+长期学习目标。"
            f" 不要说「你：」前缀。贴合{grade}{major}的背景来问。"
        )

    # ======================== 对话交互 ========================

    async def chat(self, student_id: str, session_id: str,
                    user_message: str, language: str = "") -> tuple[str, bool, Optional[StudentProfile], Optional[RadarScores]]:
        """
        对话交互。
        返回 (reply, is_completed, profile, radar_scores)
        """
        if not user_message or not user_message.strip():
            return "请说点什么吧～", False, None, None

        user_message = user_message.strip()

        # ---- 0. 调试日志：当前画像状态 ----
        try:
            debug_profile = profile_manager.get_profile(student_id)
            logger.info(f"[DEBUG] 当前画像: student_id={debug_profile.student_id}, name={debug_profile.name}")
        except Exception:
            pass

        # ---- 1. 从 Redis 读取完整上下文（安全读取）----
        context = self._safe_read_context(student_id, session_id)
        progress = context.get("collect_progress", {})
        chat_history = context.get("chat_history", [])
        if not isinstance(chat_history, list):
            chat_history = []
        stage = progress.get("stage", STAGE_ACADEMIC)
        asked_count = progress.get("asked_count", 0)

        # ---- 保存旧状态 + 维护 consecutive_valid_replies ----
        prev_stage = stage
        prev_asked = int(asked_count) if isinstance(asked_count, (int, float)) else 0
        cv = context.get("consecutive_valid_replies") or 0
        if not isinstance(cv, (int, float)):
            cv = 0
        cv = int(cv)
        if len(str(user_message).strip()) > 4:
            cv += 1
        context["consecutive_valid_replies"] = cv
        new_context = context

        # 安全获取 dims_done（修复：非列表脏数据保护）
        dims_done = self._safe_list(progress.get("dims_done"))

        # ---- 2. 构建 Prompt 生成下一轮回复 ----
        prompt = self._build_chat_prompt(context, user_message, language)
        raw_full_response = ""
        try:
            raw_full_response = await self.generate(prompt)
            reply = self._clean_response(raw_full_response)
        except Exception as e:
            logger.exception(f"[ProfileChatAgent] 对话生成失败")
            reply = "好的，我了解了。能再详细说说你的学习情况吗？"
            raw_full_response = reply

        # ---- 2.5 二次 JSON 泄漏拦截 ----
        if reply.startswith("{") and ("student_id" in reply or "knowledge_base" in reply):
            logger.warning(f"[ProfileChatAgent] 检测到 JSON 泄露已被拦截: {reply[:80]}")
            reply = "好的，我了解了。能再详细说说你的学习情况吗？"

        # ---- 2.6 维度采集追踪 + 重复提问兜底 ----
        # units：已收集的维度单元列表（形如 "preferred_pace.main"、"learning_goals.short"）
        units = self._normalize_units(dims_done)
        ask_dim, ask_unit = self._classify_dim(reply)
        u_text = str(user_message).strip()
        user_answered = len(u_text) >= 2 or u_text.isdigit()

        # 学生本轮有实质回答 → 把对应维度单元标记为已收集
        if user_answered and ask_dim:
            if ask_unit == "both":
                for k in ("learning_goals.short", "learning_goals.long"):
                    if k not in units:
                        units.append(k)
            elif ask_unit == "any":
                if "learning_goals.any" not in units:
                    units.append("learning_goals.any")
            elif ask_unit is not None:
                unit_key = f"{ask_dim}.{ask_unit}"
                if unit_key not in units:
                    units.append(unit_key)

        # 模型重复追问"上一轮已收集"的维度 → 用确定性问题替换，防止原地打转
        prev_units = self._normalize_units(dims_done)
        if ask_dim and ask_unit not in ("any", "both", None) and self._dim_done(ask_dim, prev_units):
            next_dim = self._next_dim_to_ask(units)
            if next_dim:
                logger.warning(f"[ProfileChatAgent] 模型重复追问已收集维度 {ask_dim}.{ask_unit}，"
                               f"替换为确定性问题（{DIM_CN.get(next_dim, next_dim)}）")
                reply = FALLBACK_QUESTIONS[next_dim]

        # ---- 3. 判断完成状态 ----
        is_completed = "已构建完成" in reply
        # 8 个维度全部收集完整 → 直接生成画像
        if not is_completed and all(self._dim_done(d, units) for d in DIM_ORDER):
            logger.info(f"[ProfileChatAgent] 8 维度全部收集完成，生成画像")
            is_completed = True
            reply = "✅ 你的个性化画像已构建完成！"
        # 轮数足够多时强制完成（兜底）
        if not is_completed and asked_count >= 12:
            logger.info(f"[ProfileChatAgent] 轮数达到{asked_count}，强制完成画像")
            is_completed = True
            reply = "✅ 你的个性化画像已构建完成！"

        # ---- 4. 提取/生成完整画像（从 raw_full_response 提取，与 reply 隔离）----
        profile = None
        radar_scores = None
        base_info = context.get("base_info", {})

        if is_completed:
            try:
                # 从大模型原始输出提取 JSON，不影响前端展示用的 reply
                extracted = self._try_extract_json(raw_full_response)
                if extracted:
                    profile = self._save_extracted_profile(student_id, extracted, base_info)
                else:
                    try:
                        # context 的 chat_history 滞后一轮，需补上本轮学生答案后再抽取，
                        # 否则最后一轮的 interests/困难等信息会丢
                        extract_context = dict(context)
                        extract_history = list(chat_history) if isinstance(chat_history, list) else []
                        extract_history.append({"role": "user", "content": user_message})
                        if raw_full_response:
                            extract_history.append({"role": "assistant", "content": raw_full_response})
                        extract_context["chat_history"] = extract_history
                        final_profile = await self._generate_final_profile(student_id, session_id, extract_context)
                        if final_profile:
                            profile = final_profile
                    except Exception as e:
                        logger.exception(f"[ProfileChatAgent] 最终画像生成失败")
                        profile = profile_manager.get_profile(student_id)

                if profile:
                    # 强制回填（直接设置，不依赖条件）
                    profile.student_id = student_id
                    profile.name = base_info.get("name") or profile.name or "同学"
                    profile.grade = base_info.get("grade") or profile.grade or "大一"
                    profile.major = base_info.get("major") or profile.major or "学生"
                    profile_manager.save_profile(profile)
                    radar_scores = profile_manager.extract_radar_scores(student_id)
                # 前端展示的 reply 强制设为纯文本
                reply = "✅ 你的个性化画像已构建完成！"
            except Exception as e:
                logger.exception(f"[ProfileChatAgent] 画像完成处理异常")
                is_completed = False

        # ---- 5. 批量写入 Redis（收集所有变更，一次 IO）----
        new_asked_count = int(asked_count) + 1  # 在 try 外定义，防止 NameError
        new_stage = STAGE_COMPLETED if is_completed else (
            STAGE_ACADEMIC if new_asked_count <= 4 else STAGE_DIMENSION
        )
        # 构建新的完整聊天历史（提到 try 外，后台抽取任务也要复用最新历史）
        new_history = list(chat_history) if isinstance(chat_history, list) else []
        new_history.append({"role": "user", "content": user_message})
        new_history.append({"role": "assistant", "content": reply})

        try:
            updates = {
                "chat_history": json.dumps(new_history, ensure_ascii=False),
                "collect_progress": json.dumps({
                    "stage": new_stage,
                    "current_dim": progress.get("current_dim"),
                    "dims_done": units,
                    "asked_count": new_asked_count,
                }, ensure_ascii=False),
            }
            try:
                cache.batch_update_session(student_id, session_id, updates)
            except Exception as e:
                logger.error(f"[ProfileChatAgent] Redis 批量写入失败: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"[ProfileChatAgent] 序列化聊天历史失败: {e}")

        
        # ---- 触发增量抽取（后台任务，不 await）----
        try:
            should_extract = self._should_trigger_extract(
                context=new_context,
                prev_stage=prev_stage,
                new_stage=new_stage,
                prev_asked=prev_asked,
                new_asked=new_asked_count,
                last_valid_replies=cv,
            )
            if should_extract:
                import asyncio as _asyncio
                _sid = student_id
                _sesid = session_id
                _ctx = dict(new_context) if isinstance(new_context, dict) else {}
                # 后台抽取同样要看到最新一轮（new_context 的 chat_history 滞后一轮）
                _ctx["chat_history"] = list(new_history) if isinstance(new_history, list) else new_history
                task = _asyncio.create_task(self._run_extract_task(_sid, _sesid, _ctx))
                logger.info(f"[ProfileChatAgent] 后台触发增量抽取任务（student={_sid}, asked={new_asked_count}, valid={cv})")
        except Exception as _trigger_err:
            logger.warning(f"[ProfileChatAgent] 触发抽取逻辑异常: {_trigger_err}")

        logger.info(f"[ProfileChatAgent] chat回复: student={student_id}, "
                     f"stage={stage}, asked={new_asked_count}, completed={is_completed}")
        return reply, is_completed, profile, radar_scores

    def _build_chat_prompt(self, context: dict, user_message: str, language: str = "") -> str:
        """构建对话 Prompt"""
        base_info = context.get("base_info", {})
        progress = context.get("collect_progress", {})
        chat_history = context.get("chat_history", [])
        if not isinstance(chat_history, list):
            chat_history = []
        stage = progress.get("stage", STAGE_ACADEMIC)
        asked_count = progress.get("asked_count", 0)
        # 已收集的维度单元（供完备率跳过 & 提示模型勿重复追问）
        units = self._normalize_units(progress.get("dims_done"))
        collected_cn = [DIM_CN[d] for d in DIM_ORDER if self._dim_done(d, units)]
        collected_hint = "、".join(collected_cn) if collected_cn else "（暂无）"
        # =========== 新增：当前画像快照 + 完备率 反推补维度指示 ===========
        profile_snapshot_text = ""
        next_dim_suggest = ""
        overall = 0.0
        bottom_dim = ""
        try:
            # 优先从 cache 中上下文读 temp_profile_draft；否则 fallback 到 profile_manager
            current_profile = context.get("temp_profile_draft") or {}
            if not current_profile:
                sid = base_info.get("student_id", "") or context.get("student_id", "")
                if sid:
                    p = profile_manager.get_profile(sid)
                    current_profile = p.model_dump() if p else {}
            if isinstance(current_profile, dict):
                completeness = current_profile.get("completeness") or {}
                if isinstance(completeness, dict):
                    overall = completeness.get("overall", 0.0) or 0.0
                    # 找最低的维度（跳过已收集的，避免模型重复追问）
                    min_val = 1.1
                    for d in DIM_ORDER:
                        if self._dim_done(d, units):
                            continue
                        v = completeness.get(d, 0.0) or 0.0
                        if v < min_val:
                            min_val = v
                            bottom_dim = d
                    # 维度中文映射
                    dim_cn = {
                        "knowledge_base": "知识基础（已掌握/薄弱/未接触）",
                        "cognitive_style": "认知学习风格（视觉/听觉/读写/动觉）",
                        "preferred_pace": "学习节奏偏好（慢速/适中/快速）",
                        "error_prone_areas": "高频易错短板（常错题型/思维误区）",
                        "interests": "个人兴趣与应用方向",
                        "learning_goals": "学习目标（短期+长期）",
                        "goal_attribute": "目标属性（应试/就业/考研/自学兴趣）",
                        "daily_available_hours": "每日可投入学习时长（小时）",
                    }
                    next_dim_suggest = dim_cn.get(bottom_dim, "") or ""

                # 构建快照文本（只给对话 Agent 看，不给学生看）
                kb = (current_profile.get("knowledge_base") or {}) if isinstance(current_profile.get("knowledge_base"), dict) else {}
                mastered_cnt = len(kb.get("mastered", [])) if isinstance(kb.get("mastered"), list) else 0
                weak_cnt = len(kb.get("weak", [])) if isinstance(kb.get("weak"), list) else 0
                untouched_cnt = len(kb.get("untouched", [])) if isinstance(kb.get("untouched"), list) else 0
                interests = current_profile.get("interests", []) if isinstance(current_profile.get("interests"), list) else []
                eps = current_profile.get("error_prone_areas", []) if isinstance(current_profile.get("error_prone_areas"), list) else []
                cs = current_profile.get("cognitive_style", "") or ""
                pace = current_profile.get("preferred_pace", "") or ""
                ga = current_profile.get("goal_attribute", "") or ""
                goals = current_profile.get("learning_goals") or {}
                goals_st = goals.get("short_term", "") if isinstance(goals, dict) else ""
                goals_lt = goals.get("long_term", "") if isinstance(goals, dict) else ""
                hours = current_profile.get("daily_available_hours", 0) or 0.0

                snap_lines = []
                snap_lines.append(f"knowledge_base 已掌握{mastered_cnt}个 / 薄弱{weak_cnt}个 / 未接触{untouched_cnt}个")
                if cs: snap_lines.append(f"cognitive_style = {cs}")
                if pace: snap_lines.append(f"preferred_pace = {pace}")
                if eps: snap_lines.append(f"error_prone_areas({len(eps)}) = {', '.join(eps[:3])}")
                if interests: snap_lines.append(f"interests({len(interests)}) = {', '.join(interests[:3])}")
                if goals_st or goals_lt: snap_lines.append(f"learning_goals: 短期={goals_st[:30]} | 长期={goals_lt[:30]}")
                if ga: snap_lines.append(f"goal_attribute = {ga}")
                if hours: snap_lines.append(f"daily_available_hours = {hours}")
                profile_snapshot_text = "\n".join(snap_lines) if snap_lines else "（当前尚无画像数据，从0开始构建）"
        except Exception as e:
            logger.warning(f"[ProfileChatAgent] 构建画像快照失败: {e}")
            profile_snapshot_text = "（快照读取失败，按默认流程推进）"
            bottom_dim = ""
            overall = 0.0

        dims_done = self._safe_list(progress.get("dims_done"))

        # 取最近 12 条记录作为上下文
        recent = chat_history[-12:] if len(chat_history) > 12 else chat_history
        history_lines = []
        for m in recent:
            role = m.get("role", "user") if isinstance(m, dict) else "user"
            content = m.get("content", "") if isinstance(m, dict) else str(m)
            prefix = "学生" if role == "user" else "助手"
            history_lines.append(f"{prefix}: {content}")
        history_text = "\n".join(history_lines)

        grade = base_info.get("grade", "")
        major = base_info.get("major", "")

        lang_hint = self._get_language_hint(language)
        stage_hint = "阶段2-核心学情问询" if asked_count <= 4 else ("阶段4-会话收尾" if asked_count >= 10 else "阶段3-补齐6维度")
        dim_hint = self._next_dim_hint(asked_count, dims_done)

        return (
            f"[系统指令] 你是画像构建助手。每次只说1句话+1个问题。\n"
            f"[语言要求] {lang_hint}\n"
            f"[当前阶段] {stage_hint}\n"
            f"[学生背景] {grade}{major}\n"
            f"[采集进度] 已提问{asked_count}次\n"
            f"[维度提示] {dim_hint}\n"
            f"[已收集维度（绝对不要再重复追问，改问还没收集的维度）] {collected_hint}\n"
                                f"[当前画像快照（仅供对话 Agent 判断，不要输出给学生！）]\n{profile_snapshot_text}\n"
                f"[画像完备率 overall={int(round(overall*100))}%，当前最缺维度={next_dim_suggest}]\n"
                f"[决策依据] 若 overall < 100%，请优先追问【最缺维度】的信息；一次一句+一个问题。\n"
            f"[对话历史]\n{history_text}\n"
            f"[学生最新回复] {user_message}\n"
            f"[指令] 用1句话回复学生，然后问下一维度的问题。"
            f" 禁止以「很好/不错/好的/明白了」等固定客套词开头，开头要直接回应学生上一句内容或自然承接，句式不要重复上一轮。"
            f" 严禁重复追问【已收集维度】里出现的维度；学生已回答过的内容不要换着花样再问，直接推进到下一个未收集维度。"
            f" 如果所有信息已收集完毕，只输出「✅ 你的个性化画像已构建完成！」禁止输出JSON、大括号、代码块。"
        )

    def _next_dim_hint(self, asked_count: int, dims_done: list) -> str:
        """根据进度提示下一维度"""
        if asked_count <= 1:
            return "询问学习目标（短期+长期）"
        elif asked_count <= 2:
            return "询问当前学习进度、学到的阶段"
        elif asked_count <= 3:
            return "询问已掌握的知识点"
        elif asked_count <= 4:
            return "询问知识薄弱内容"
        else:
            units = self._normalize_units(dims_done)
            remaining = [d for d in DIM_ORDER if not self._dim_done(d, units)]
            if remaining and asked_count <= 10:
                return f"补齐剩余维度: {', '.join(DIM_CN.get(d, d) for d in remaining[:2])}"
            return "信息已基本齐备，准备生成最终画像，仅输出「✅ 你的个性化画像已构建完成！」"

    @staticmethod
    def _normalize_units(dims_done) -> list:
        """把 progress['dims_done'] 清洗成合法的维度单元列表（形如 'preferred_pace.main'）"""
        if not isinstance(dims_done, list):
            return []
        return [x for x in dims_done if isinstance(x, str) and "." in x]

    @staticmethod
    def _dim_done(dim: str, units: list) -> bool:
        """判断某维度是否已完整收集。learning_goals 需要短期+长期都答过，其余一个 main 即可。"""
        if dim == "learning_goals":
            return ("learning_goals.any" in units
                    or ("learning_goals.short" in units and "learning_goals.long" in units))
        return f"{dim}.main" in units

    def _next_dim_to_ask(self, units: list) -> Optional[str]:
        """按固定顺序返回第一个还没收集完整的维度，全部齐则返回 None"""
        for d in DIM_ORDER:
            if not self._dim_done(d, units):
                return d
        return None

    @staticmethod
    def _classify_dim(text: str):
        """识别提问文本在采集哪个维度。返回 (dim, unit)。
        unit：learning_goals 为 short/long/both/any，其余维度为 main。识别不出返回 (None, None)。
        """
        if not isinstance(text, str) or not text:
            return None, None
        if "短期" in text and "长期" in text:
            return "learning_goals", "both"
        if "短期" in text:
            return "learning_goals", "short"
        if "长期" in text:
            return "learning_goals", "long"
        if any(k in text for k in ("应试", "就业", "考研", "考证", "自学", "找工作", "为什么学", "目标属性")):
            return "goal_attribute", "main"
        if any(k in text for k in ("学习目标", "目标", "想做成", "想要达到")):
            return "learning_goals", "any"
        if any(k in text for k in ("视觉", "听觉", "读写", "动觉", "动手", "实操", "学习方式", "方式理解", "看视频")):
            return "cognitive_style", "main"
        if any(k in text for k in ("节奏", "慢速", "速成", "快速掌握", "细学")):
            return "preferred_pace", "main"
        if any(k in text for k in ("困难", "难", "易错", "卡住", "出错", "薄弱", "错题", "短板")):
            return "error_prone_areas", "main"
        if any(k in text for k in ("兴趣", "喜欢", "领域", "感兴趣", "爱好", "应用方向")):
            return "interests", "main"
        if any(k in text for k in ("每天", "投入", "时间", "小时", "时长")):
            return "daily_available_hours", "main"
        if any(k in text for k in ("掌握", "学过", "基础", "知识", "熟练", "会哪些", "进度", "学习情况", "会")):
            return "knowledge_base", "main"
        return None, None

    def _get_language_hint(self, language: str) -> str:
        """根据语言代码生成语言提示"""
        lang_map = {
            "zh-CN": "请使用简体中文回复",
            "en-US": "请使用英语回复 (Please respond in English)",
        }
        return lang_map.get(language, "请使用中文回复")

    async def _run_extract_task(self, student_id, session_id, context):
        """
        后台异步增量抽取画像任务。
        按 Prompt 2 做抽取 + 保存（不阻塞主对话）。
        """
        try:
            if not isinstance(context, dict):
                context = {}
            chat_history = context.get("chat_history", [])
            if not isinstance(chat_history, list):
                chat_history = []
            base_info = context.get("base_info", {})
            if not isinstance(base_info, dict):
                base_info = {}
            
            # 读取旧画像
            old_profile_dict = {}
            try:
                draft = context.get("temp_profile_draft") or {}
                if draft and isinstance(draft, dict):
                    old_profile_dict = draft
                else:
                    p = profile_manager.get_profile(student_id)
                    old_profile_dict = p.model_dump() if p else {}
            except Exception:
                old_profile_dict = {}
            
            # 构造带 turn 前缀的完整对话（turn 从 1 开始）
            conv_lines = []
            turn_idx = 1
            for m in chat_history:
                if isinstance(m, dict):
                    role = m.get("role", "user")
                    content = m.get("content", "")
                else:
                    role = "user"
                    content = str(m)
                prefix = "学生" if role == "user" else "助手"
                conv_lines.append(f"turn {turn_idx}: {prefix}: {content}")
                turn_idx += 1
            conv_text = "\n".join(conv_lines)
            
            try:
                old_profile_json = json.dumps(old_profile_dict, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                old_profile_json = "{}"
            
            try:
                base_info_str = json.dumps(base_info, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                base_info_str = "{}"
            
            prompt = (
                f"{PROFILE_EXTRACTION_SYSTEM_PROMPT}\n\n"
                f"[上一版画像（旧画像）]\n{old_profile_json}\n\n"
                f"[完整对话记录（turn 从 1 开始编号）]\n{conv_text}\n\n"
                f"[基础信息]\n{base_info_str}\n\n"
                f"强制性要求：输出 JSON 的 profile 段必须包含 student_id、name、grade、major 四个字段，从以上[基础信息]获取。"
            )
            
            try:
                response = await self.generate(prompt, model=EXTRACT_MODEL, thinking={"type": "disabled"}, max_tokens=8192)
            except Exception as e:
                logger.warning(f"[ProfileChatAgent] 增量抽取调用大模型失败: {e}")
                return
            
            parsed = self._try_extract_json(response)
            if not parsed or not isinstance(parsed, dict):
                logger.warning(f"[ProfileChatAgent] 增量抽取结果解析失败")
                return
            
            profile_data = parsed.get("profile") or {}
            if not isinstance(profile_data, dict):
                profile_data = {}
            
            profile = profile_manager.get_profile(student_id)
            # 填充基础信息
            profile.student_id = base_info.get("student_id") or student_id
            profile.name = base_info.get("name") or profile.name or ""
            profile.grade = base_info.get("grade") or profile.grade or ""
            profile.major = base_info.get("major") or profile.major or ""
            # 填充画像维度
            for field in ["knowledge_base", "cognitive_style", "preferred_pace",
                "error_prone_areas", "interests", "learning_goals",
                "goal_attribute", "daily_available_hours",
                "confidence", "completeness", "evidence"]:
                val = profile_data.get(field)
                if val is not None:
                    try:
                        setattr(profile, field, val)
                    except Exception:
                        pass
            
            # 显式赋给嵌套的 confidence/completeness/evidence（如果 parsed 中直接提供）
            if isinstance(parsed.get("confidence"), dict):
                try:
                    profile.confidence = parsed["confidence"]
                except Exception:
                    pass
            if isinstance(parsed.get("completeness"), dict):
                try:
                    profile.completeness = parsed["completeness"]
                except Exception:
                    pass
            if isinstance(parsed.get("evidence"), dict):
                try:
                    profile.evidence = parsed["evidence"]
                except Exception:
                    pass
            
            profile.version += 1
            from datetime import datetime
            profile.updated_at = datetime.now().isoformat()
            profile.source = "chat"
            try:
                profile_manager.save_profile(profile)
            except Exception as e:
                logger.warning(f"[ProfileChatAgent] 增量抽取后保存失败: {e}")
            
            # 回填到 context 的 temp_profile_draft（供后续轮次使用）
            try:
                dumped = profile.model_dump()
                context["temp_profile_draft"] = dumped
                # 尝试写回 Redis cache
                try:
                    cache.save_full_context(student_id, session_id, context)
                except Exception:
                    pass
            except Exception:
                pass
            
            logger.info(f"[ProfileChatAgent] 增量抽取任务完成: student={student_id}")
        except Exception as e:
            logger.exception(f"[ProfileChatAgent] 增量抽取任务异常")

    def _should_trigger_extract(self, context: dict, prev_stage: str, new_stage: str,
        prev_asked: int, new_asked: int, last_valid_replies: int) -> bool:
        """
        判断是否触发增量抽取任务。
        策略：
         - 若 A3_EXTRACT_STRATEGY=light（环境变量），每轮都抽取；
         - 否则走省钱方案：
             a) stage 切换；
             b) last_valid_replies 为 3 的倍数且 > 0；
             c) new_asked 刚好越过 12（收尾抽取一次）。
        """
        try:
            strategy = (os.environ.get("A3_EXTRACT_STRATEGY") or "").strip().lower()
            if strategy == "light":
                return True
            # 省钱方案
            if prev_stage and new_stage and (prev_stage != new_stage):
                return True
            if last_valid_replies > 0 and last_valid_replies % 3 == 0:
                return True
            if prev_asked < 12 <= new_asked:
                return True
            return False
        except Exception:
            return False


    def _save_extracted_profile(self, student_id: str, data: dict,
                                  base_info: Optional[dict] = None) -> StudentProfile:
        """保存提取的画像到 ProfileManager，强制回填基础字段"""
        if not isinstance(data, dict):
            logger.warning(f"[ProfileChatAgent] 保存画像数据格式异常: {type(data)}")
            return profile_manager.get_profile(student_id)
        profile = profile_manager.get_profile(student_id)
        # data 可能是完整抽取结构 {"profile": {...}, "confidence": {...}, ...}，
        # 也可能是直接就是 profile 段。必须解包 parsed["profile"]，否则维度数据全丢
        profile_data = data.get("profile") if isinstance(data.get("profile"), dict) else data
        profile_manager.update_profile(profile, profile_data)
        # 顶层可选的 confidence/completeness/evidence 一并写入
        for field in ("confidence", "completeness", "evidence"):
            val = data.get(field)
            if isinstance(val, dict) and val:
                try:
                    setattr(profile, field, val)
                except Exception:
                    pass
        # 强制从 base_info 回填
        bi = base_info or {}
        profile.student_id = bi.get("student_id") or student_id
        profile.name = bi.get("name") or profile.name or "同学"
        profile.grade = bi.get("grade") or profile.grade or "大一"
        profile.major = bi.get("major") or profile.major or "学生"
        profile.source = "chat"
        profile.version += 1
        try:
            profile_manager.save_profile(profile)
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 保存画像文件失败: {e}")
        return profile

    async def _generate_final_profile(self, student_id: str, session_id: str,
                                       context: dict) -> Optional[StudentProfile]:
        """调用大模型生成完整结构化画像，全异常捕获"""
        if not isinstance(context, dict):
            context = {}
        chat_history = context.get("chat_history", [])
        if not isinstance(chat_history, list):
            chat_history = []
        base_info = context.get("base_info", {})
        if not isinstance(base_info, dict):
            base_info = {}

        conv_lines = []
        for m in chat_history[-20:]:
            role = m.get("role", "user") if isinstance(m, dict) else "user"
            content = m.get("content", "") if isinstance(m, dict) else str(m)
            prefix = "学生" if role == "user" else "助手"
            conv_lines.append(f"{prefix}: {content}")
        conv_text = "\n".join(conv_lines)

        try:
            base_info_str = json.dumps(base_info, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            base_info_str = "{}"

        prompt = (
            f"{PROFILE_EXTRACTION_SYSTEM_PROMPT}\n\n"
            f"[基础信息]\n{base_info_str}\n\n"
            f"[完整对话记录]\n{conv_text}\n\n"
            f"请根据以上全部对话内容，提取学生的完整画像，输出严格JSON格式。\n"
            f"强制性要求：JSON必须包含 student_id、name、grade、major 四个字段，从以上[基础信息]获取，缺失视为提取不合格。"
        )

        try:
            response = await self.generate(
                prompt, model=EXTRACT_MODEL,
                thinking={"type": "disabled"}, max_tokens=8192,
            )
            parsed = self._try_extract_json(response)
            if parsed:
                profile = self._save_extracted_profile(student_id, parsed, base_info)
                # 二次强制回填（防御性兜底）
                self._fill_base_info(profile, base_info, student_id)
                profile_manager.save_profile(profile)
                return profile
            else:
                logger.warning(f"[ProfileChatAgent] 最终画像生成解析失败")
                return None
        except SparkAPIError as e:
            logger.error(f"[ProfileChatAgent] 大模型 API 异常: {e}")
            return None
        except Exception as e:
            logger.exception(f"[ProfileChatAgent] 最终画像生成未知异常")
            return None

    # ======================== 工具方法 ========================

    def get_progress(self, student_id: str, session_id: str) -> ProfileChatProgress:
        """获取当前采集进度"""
        context = self._safe_read_context(student_id, session_id)
        progress = context.get("collect_progress", {})
        stage = progress.get("stage", STAGE_ACADEMIC)
        current_dim = progress.get("current_dim")
        dims_done = self._safe_list(progress.get("dims_done"))
        asked_count = progress.get("asked_count", 0)

        total = len(DIM_ORDER)  # 8
        units = self._normalize_units(dims_done)
        done_count = sum(1 for d in DIM_ORDER if self._dim_done(d, units))
        pct = min(100, round(done_count / total * 100)) if total > 0 else 0

        return ProfileChatProgress(
            stage=stage if isinstance(stage, str) else STAGE_ACADEMIC,
            current_dim=current_dim,
            dims_done=dims_done,
            total_dims=total,
            progress_percent=pct,
            asked_count=asked_count if isinstance(asked_count, (int, float)) else 0,
        )

    def get_session_id(self, student_id: str) -> Optional[str]:
        """获取学生当前活跃会话ID"""
        try:
            return cache.init_chat_session(student_id, {"student_id": student_id})
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 获取会话ID失败: {e}")
            return None

    def reset_session(self, student_id: str):
        """重置学生会话和画像"""
        import uuid
        try:
            session_id = cache._find_active_session(student_id)
            if session_id:
                cache.end_chat_session(student_id, session_id, archive=False)
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 重置会话失败: {e}")
        try:
            profile_manager.reset_profile(student_id)
        except Exception as e:
            logger.error(f"[ProfileChatAgent] 重置画像失败: {e}")

    async def process(self, *args, **kwargs):
        """实现基类抽象方法"""
        action = kwargs.get("action", "chat")
        if action == "init":
            return await self.init_chat(
                kwargs.get("student_id", ""),
                kwargs.get("name", ""),
                kwargs.get("grade", ""),
                kwargs.get("major", ""),
            )
        elif action == "chat":
            return await self.chat(
                kwargs.get("student_id", ""),
                kwargs.get("session_id", ""),
                kwargs.get("message", ""),
            )
        return None, None

    @staticmethod
    def _clean_response(text: str) -> str:
        """清洗回复内容（去除前缀 + 过滤 JSON 泄漏）"""
        if not isinstance(text, str):
            return ""
        text = text.strip()

        # 去除常见前缀
        prefixes = ["你：", "你:", "系统：", "系统:", "助手：", "助手:", "Assistant:", "AI:"]
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # 如果文本以 { 开头且包含 "student_id" 或 "knowledge_base"，认为是 JSON，返回默认话术
        if text.startswith("{") and any(key in text for key in ["student_id", "knowledge_base", "profile"]):
            logger.warning(f"[ProfileChatAgent] 检测到 JSON 输出被过滤: {text[:100]}")
            return "好的，我了解了。能再详细说说你的学习情况吗？"

        # 如果包含 ```json 代码块，移除
        if "```json" in text:
            text = text.split("```json")[0].strip()
        if "```" in text:
            parts = text.split("```")
            text = "".join(parts[::2]).strip()

        return text

    @staticmethod
    def _try_extract_json(text: str):
        """从大模型输出中稳健提取 JSON 对象（容忍 ```json 围栏、前后缀文本、多余换行）

        返回解析后的 dict，失败返回 None。
        """
        if not isinstance(text, str) or not text.strip():
            return None
        t = text.strip()
        # 1) 优先取 ```json ... ``` 代码围栏内的内容
        fences = re.findall(r"```(?:json)?\s*([\s\S]*?)```", t)
        if fences:
            t = fences[0].strip()
        # 2) 兜底：从第一对平衡大括号开始截取最外层 JSON
        start = t.find("{")
        if start == -1:
            return None
        depth = 0
        end = -1
        for i in range(start, len(t)):
            if t[i] == "{":
                depth += 1
            elif t[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            end = t.rfind("}")
        if end == -1:
            return None
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError:
            return None


# 全局实例
profile_chat_agent = ProfileChatAgent()
