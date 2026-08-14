"""
A3 LangGraph 状态机编排引擎

核心编排逻辑：
1. intent_router_node     — 意图识别（LLM 分类 / 前端显式指定）
2. mode_conflict_node     — 业务模式冲突检测
3. capability_dispatch    — 按意图分发到对应 Capability
4. profile_node           — 画像构建
5. resource_node          — 资源生成
6. plan_node              — 路径规划
7. tutor_node             — 智能辅导
8. result_aggregator      — 结果聚合

替换旧的 app/langgraph_orch/ 目录，提供统一入口。
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Literal, Optional

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from core.protocol import AgentState, create_initial_state
from core import get_capability

# 意图路由智能体
from core.capabilities.impl.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ======================== 意图分类提示词 ========================

INTENT_ROUTER_PROMPT = """你是一个智能学习助手的意图识别引擎。分析用户输入，判断属于以下哪一类意图：

## 意图分类

### 类别A: profile（画像相关）
当用户涉及以下内容时：
- 开启/更新/查看/修改个人学习画像、学情档案、知识水平评估
- 描述自己的学习情况、专业、年级、学习目标、薄弱点
- 关键词：画像、学情、档案、我的情况、了解我、个人信息、学习目标

### 类别B: resource（资源生成）
**仅当用户明确要求生成具体学习资料时**：
- 生成/获取学习资料、课件、讲解文档
- 出练习题、考试题、模拟题
- 推荐阅读材料、拓展读物、代码案例
- 关键词：生成、出题、创建、制作、编写、推荐、给我一份

### 类别C: plan（路径规划）
当用户涉及学习计划、路线、方案时：
- 制定学习计划、学习路线、备考方案
- 询问学习顺序、阶段安排
- 关键词：路线、路径、计划、规划、方案、安排、顺序、阶段、备考

### 类别D: tutor（学习提问/答疑）
当用户**询问具体知识点、概念、技术问题**时：
- 问"什么是X""X怎么用""X是什么""X的原理"
- "帮我讲解一下X""我想学X""X和Y的区别"
- "X的时间复杂度""X和Y有什么区别""解释一下X的原理"
- **承接上文的知识点追问**："那它的时间复杂度呢""那它们有什么区别""这个怎么用""继续讲一下"
- 要求解释概念、术语、技术
- 关键词：什么是、怎么用、是什么、如何、为什么、讲解、学习、了解、概念、原理、复杂度、区别、原理

### 类别E: unknown（无法判断）
当用户输入不明确、打招呼、闲聊时

## ⚠️ 重要判断规则（必须遵守）
- "什么是函数" → tutor（学习提问）
- "生成函数学习资料" → resource（资源生成）
- "我想学习函数" → tutor（学习提问）
- "帮我出几道函数题" → resource（资源生成）
- "讲解一下函数" → tutor（学习提问）
- "给我一份函数教程" → resource（资源生成）
- "帮我生成所有学习资料" → resource（资源生成）
- "那它的时间复杂度是多少"（承接上文刚讲过"数组"）→ tutor（学习提问）
- **只要在追问上一个知识点（用"它""这个""那"指代前面讲过的概念），一律 → tutor**
- **知识点/概念/原理/复杂度/区别 的提问一律 → tutor，绝不归为 profile**
- **profile 只用于**：用户要求构建/完善/更新自己的学习画像，或描述自己的学习情况/专业/年级/学习目标/薄弱点

## 输出格式
仅输出JSON，不要其他文字：
{"intent": "profile/resource/plan/tutor/unknown", "confidence": 0.95, "reason": "简要判断理由"}
"""


# ====================================================================
#  意图路由节点
# ====================================================================


class IntentRouter(BaseAgent):
    """意图识别路由智能体"""

    def __init__(self):
        super().__init__(
            name="IntentRouter",
            model_name="spark-4.0-ultra",
            system_prompt=INTENT_ROUTER_PROMPT,
            temperature=0.1,
        )

    async def classify(self, user_message: str, history: str = "") -> dict:
        prompt = f"[用户输入]\n{user_message}\n"
        if history:
            prompt += f"[对话历史摘要]\n{history}\n"
        prompt += "\n请分析意图，输出JSON。"
        try:
            response = await self.generate(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"[IntentRouter] 意图识别失败: {e}")
            return {"intent": "unknown", "confidence": 0.0, "reason": f"识别异常: {e}"}

    async def process(self, message: str, **kwargs) -> dict:
        return await self.classify(message)

    @staticmethod
    def _parse_response(text: str) -> dict:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(text[start:end + 1])
                return {
                    "intent": data.get("intent", "unknown"),
                    "confidence": float(data.get("confidence", 0)),
                    "reason": data.get("reason", ""),
                }
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return {"intent": "unknown", "confidence": 0.0, "reason": "解析失败"}


# ====================================================================
#  关键词快速匹配（在 LLM 分类之前优先判断）
# ====================================================================

VIDEO_KEYWORDS = [
    "视频推荐", "推荐视频", "视频教程", "学习视频", "教学视频",
    "视频讲解", "给我视频", "找视频", "搜视频", "相关视频",
    "video", "b站", "bilibili", "B站",
    "哔哩哔哩", "哔站",
]

# 视频意图复合匹配：同时包含 "推荐"+"视频" 或 "视频"+"学习" 等组合
VIDEO_COMBO_PATTERNS = [
    (["推荐", "视频"],),
    (["找", "视频"],),
    (["搜索", "视频"],),
    (["看", "视频"],),
]


RESOURCE_KEYWORDS = [
    "出题", "出几道", "练习题", "考题", "生成题目",
    "思维导图", "生成资料", "学习资料", "给我一份", "帮我生成",
    "创建", "制作", "编写一份", "生成文档", "写一个教程",
    "推荐", "给我推荐", "帮我找",
    "生成", "课件", "文档",
]


def _keyword_prematch(user_msg: str) -> dict | None:
    """关键词优先匹配，返回意图信息或 None"""
    msg_lower = user_msg.lower().strip()

    # 1. 精确关键词匹配
    for kw in VIDEO_KEYWORDS:
        if kw in msg_lower:
            return {
                "intent": "resource",
                "confidence": 0.98,
                "intent_reason": f"关键词匹配: 视频推荐 ({kw})",
                "resource_video_first": True,
            }

    # 2. 组合匹配：同时包含多个关键词
    for patterns in VIDEO_COMBO_PATTERNS:
        if all(p in msg_lower for p in patterns[0]):
            return {
                "intent": "resource",
                "confidence": 0.95,
                "intent_reason": f"组合匹配: 视频推荐 ({patterns[0]})",
                "resource_video_first": True,
            }

    # 3. 包含"视频"且上下文是推荐/搜索意图
    if "视频" in msg_lower:
        recommend_words = ["推荐", "给我", "帮我", "推荐一些", "找一些", "搜索", "有什么"]
        for w in recommend_words:
            if w in msg_lower:
                return {
                    "intent": "resource",
                    "confidence": 0.93,
                    "intent_reason": f"意图匹配: 视频推荐 (视频+{w})",
                    "resource_video_first": True,
                }

    # 4. 纯资源关键词
    for kw in RESOURCE_KEYWORDS:
        if kw in msg_lower:
            return {
                "intent": "resource",
                "confidence": 0.95,
                "intent_reason": f"关键词匹配: 资源生成 ({kw})",
            }

    return None


_intent_router = IntentRouter()


async def intent_router_node(state: AgentState) -> dict:
    """LangGraph 意图识别节点"""
    user_msg = state.get("user_message", "")
    explicit_type = state.get("explicit_type", "")

    # 前端显式指定
    if explicit_type in ("profile", "resource", "plan", "tutor"):
        logger.info(f"[意图路由] 前端显式指定: {explicit_type}")
        return {
            "intent": explicit_type,
            "confidence": 1.0,
            "intent_reason": f"前端显式指定: {explicit_type}",
        }

    # 关键词快速匹配（优先于 LLM）
    kw_result = _keyword_prematch(user_msg)
    if kw_result:
        logger.info(f"[意图路由] 关键词匹配: '{user_msg[:30]}...' → {kw_result['intent']}")
        return kw_result

    # LLM 识别（注入混合对话记忆：摘要 + 最近轮）
    _hist_parts = []
    _summary = state.get("context_summary", "")
    _recent = state.get("context_history") or []
    if _summary:
        _hist_parts.append(f"[早期对话总结]\n{_summary}")
    if _recent:
        _hist_parts.append("[最近对话]\n" + "\n".join(
            f"{'学生' if m.get('role') == 'user' else '助手'}: {m.get('content', '')}"
            for m in _recent))
    result = await _intent_router.classify(user_msg, history="\n\n".join(_hist_parts))
    logger.info(f"[意图路由] '{user_msg[:30]}...' → {result['intent']} (conf={result['confidence']:.2f})")
    return {
        "intent": result["intent"],
        "confidence": result["confidence"],
        "intent_reason": result["reason"],
    }


def intent_condition(state: AgentState) -> Literal["profile", "resource", "plan", "tutor", "unknown"]:
    """条件边：根据意图分流"""
    intent = state.get("intent", "unknown")
    # tutor 也映射到 chat 分支
    if intent == "tutor":
        return "tutor"
    return intent


# ====================================================================
#  业务模式冲突检测
# ====================================================================


async def mode_conflict_node(state: AgentState) -> dict:
    """检测业务模式冲突"""
    from services.cache import cache_service

    user_id = state.get("user_id", "")
    requested_mode = state.get("intent", "")
    current_mode = cache_service.get_biz_mode(user_id)
    explicit = state.get("explicit_type", "")

    if explicit or not current_mode:
        if requested_mode:
            cache_service.set_biz_mode(user_id, requested_mode)
        return {"current_biz_mode": requested_mode, "switch_confirmed": True}

    if current_mode == requested_mode:
        return {"current_biz_mode": current_mode, "switch_confirmed": True}

    return {
        "switch_requested": True,
        "switch_confirmed": False,
        "sse_buffer": [f"当前正在【{current_mode}】模式，切换到【{requested_mode}】将结束当前会话。是否确认切换？"],
    }


# ====================================================================
#  Capability 执行节点
# ====================================================================


async def profile_node(state: AgentState) -> dict:
    """画像构建节点"""
    cap = get_capability("profile")
    if not cap:
        return {"profile_reply": "画像能力不可用", "error": "profile capability not found"}

    student_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    message = state.get("user_message", "")
    language = state.get("language", "")

    if session_id:
        reply, completed, profile, radar = await cap.chat(student_id, session_id, message, language=language)
        return {
            "profile_reply": reply,
            "profile_completed": completed,
            "profile_data": profile.model_dump() if profile else None,
        }

    sid, first_q = await cap.init_chat(student_id=student_id, language=language)
    return {
        "session_id": sid,
        "profile_question": first_q,
        "profile_reply": first_q,
    }


# ======================== 资源类型识别智能体 ========================

RESOURCE_TYPE_DETECT_PROMPT = """你是一个学习资料类型识别助手。分析用户输入，判断他们想要哪种类型的学习资料。

可选的资料类型（每个用户一次只能选择一种）：
- lecture: 课程讲解文档 / 教程 / 课件
- mindmap: 知识点思维导图 / 知识结构图
- exercise: 练习题 / 考试题 / 测试题
- reading: 拓展阅读材料 / 推荐书籍
- code: 代码实操案例 / 编程示例
- video: 视频教程 / 教学视频

## 判断规则
- "出题""做题""练习题""试卷"等 → exercise
- "视频""看视频""b站""教程视频"等 → video
- "教程""讲解""文档""课件""教案"等 → lecture
- "思维导图""脑图""知识结构""知识点梳理"等 → mindmap
- "代码""编程例子""实操""实战案例"等 → code
- "阅读""书籍""文章""拓展""延伸"等 → reading
- 如果用户说"所有资料""全部"或没有明确指定 → is_clear=false，问用户想要哪种
- 如果用户说了多种类型 → 也是 is_clear=false，引导用户选择一种
- 如果用户表示感谢、告别、闲聊（"谢谢""好的""明白了""再见"等）→ is_clear=false，question 为自然回应并保持开放："不客气！还需要我帮你生成其他学习资料吗？😊"
- 如果用户说"不用了""不需要""算了"等拒绝 → is_clear=false，question 为："好的，没问题！想学习的时候随时找我～"

## 输出格式
如果类型明确：
{"type": "lecture", "topic": "SQL", "is_clear": true}

如果不明确，需要引导：
{"is_clear": false, "question": "你想看关于Python的哪种资料呢？我可以帮你生成课程讲解、练习题、或代码案例。"}

## 主题（topic）确定规则
- 优先从用户当前消息中提取具体主题（如"SQL""线性代数""Python列表""冒泡排序"）。
- 如果用户消息没有明确主题（例如"给我几道练习题""帮我出几道题"只说要练习题、没说要学什么），则从提供的【对话历史】中最近一次讨论的知识点确定主题。
- 若都确定不了 → topic 返回空字符串 ""。

## 重要提示
- question 要自然友好，像老师在和学生对话
- question 中列出用户可能感兴趣的 2-3 种类型即可，不要全列
- 根据用户的消息内容个性化问题
"""


class ResourceTypeDetectAgent(BaseAgent):
    """资源类型识别智能体"""

    def __init__(self):
        super().__init__(
            name="ResourceTypeDetect",
            model_name="spark-4.0-ultra",
            system_prompt=RESOURCE_TYPE_DETECT_PROMPT,
            temperature=0.2,
        )

    async def detect(self, user_message: str, history: str = "") -> dict:
        prompt = f"用户输入：{user_message}\n"
        if history:
            prompt += f"\n【对话历史】\n{history}\n"
        prompt += "\n请判断用户想要哪种学习资料，并确定主题（topic）。"
        try:
            response = await self.generate(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"[资源类型识别] 识别失败: {e}")
            return {"is_clear": False, "question": "好的，你想了解哪方面的内容呢？"}

    async def process(self, message: str, **kwargs) -> dict:
        return await self.detect(message, kwargs.get("history", ""))

    @staticmethod
    def _parse_response(text: str) -> dict:
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        try:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
        except Exception:
            pass
        return {"is_clear": False, "question": "好的，你想了解哪方面的内容呢？"}


_resource_type_detector = ResourceTypeDetectAgent()


async def resource_node(state: AgentState) -> dict:
    """资源生成节点 — 使用智能体识别用户想要的资源类型"""
    topic = state.get("resource_topic") or state.get("user_message", "")
    video_first = state.get("resource_video_first", False)

    if video_first:
        return {
            "resource_topic": topic,
            "resource_types": ["video"],
            "resource_detected": True,
            "current_biz_mode": "resource",
        }

    # 如果已有明确指定的资源类型，直接使用
    existing_types = state.get("resource_types", [])
    if existing_types:
        # 已经确定了类型，继续执行
        return {
            "resource_topic": topic,
            "resource_types": existing_types,
            "resource_detected": True,
            "current_biz_mode": "resource",
        }

    # 使用 LLM 识别用户想要的资源类型（注入混合对话记忆：早期摘要 + 最近 N 轮，用于推导缺失的主题）
    _hist_parts = []
    _summary = state.get("context_summary", "")
    _recent = state.get("context_history") or []
    if _summary:
        _hist_parts.append(f"[早期对话总结]\n{_summary}")
    if _recent:
        _hist_parts.append("[最近对话]\n" + "\n".join(
            f"{'学生' if m.get('role') == 'user' else '助手'}: {m.get('content', '')}"
            for m in _recent[-6:]
        ))
    _hist = "\n\n".join(_hist_parts)
    result = await _resource_type_detector.detect(state.get("user_message", ""), history=_hist)

    if result.get("is_clear") and result.get("type"):
        rtype = result["type"]
        # 主题：优先用识别结果（可能来自对话历史），否则退回原始 topic
        rtopic = (result.get("topic") or "").strip() or topic
        logger.info(f"[资源类型识别] 明确识别: {rtype}, 主题: {rtopic}")
        return {
            "resource_topic": rtopic,
            "resource_types": [rtype],
            "resource_detected": True,
            "current_biz_mode": "resource",
        }
    else:
        question = result.get("question", f"好的！你想了解「{topic}」的哪方面内容呢？")
        logger.info(f"[资源类型识别] 不明确，发起询问")
        return {
            "resource_topic": topic,
            "resource_clarification_msg": question,
            "current_biz_mode": "resource",
        }


async def resource_exec_node(state: AgentState) -> dict:
    """资源实际执行节点 — 同步模式跳过执行，只记录类型"""
    # 同步模式下不执行完整的资源生成（太慢），交由 SSE 端点处理
    topic = state.get("resource_topic", "")
    types = state.get("resource_types", [])
    logger.info(f"[同步模式] 跳过资源执行: topic={topic}, types={types}")
    return {
        "resource_results": {t: "" for t in types},
        "resource_skip_sync": True,
    }


async def plan_node(state: AgentState) -> dict:
    """路径规划节点"""
    cap = get_capability("plan")
    if not cap:
        return {"plan_result": {"error": "plan capability not found"}}

    topic = state.get("plan_topic") or state.get("user_message", "")
    student_id = state.get("user_id", "")
    language = state.get("language", "")
    try:
        plan = await cap.generate_plan(
            student_id=student_id,
            topic=topic,
            course=state.get("resource_course", ""),
            goal=state.get("plan_goal", ""),
            total_days=state.get("plan_total_days", 30),
            daily_minutes=state.get("plan_daily_minutes", 60),
            language=language,
        )
        return {"plan_result": plan, "current_biz_mode": "plan"}
    except Exception as e:
        logger.exception(f"[规划节点] 异常")
        return {"plan_result": {"error": str(e)}}


async def tutor_node(state: AgentState) -> dict:
    """智能辅导节点"""
    question = state.get("tutor_question") or state.get("user_message", "")
    student_id = state.get("user_id", "")
    language = state.get("language", "")

    from core.capabilities.impl.tutor_agent import tutor_agent
    try:
        # 非流式收集（注入混合对话记忆）
        content_parts = []
        async for chunk in tutor_agent.answer(
            question, student_id,
            conversation_history=state.get("context_history") or None,
            language=language,
            context_summary=state.get("context_summary", ""),
        ):
            content_parts.append(chunk)
        return {
            "tutor_reply": "".join(content_parts),
            "current_biz_mode": "tutor",
        }
    except Exception as e:
        logger.exception(f"[辅导节点] 异常")
        return {"tutor_reply": f"解答失败: {str(e)[:100]}"}


async def unknown_handler_node(state: AgentState) -> dict:
    """未知意图处理"""
    return {"sse_buffer": ["好的，请告诉我你需要什么帮助"]}


async def result_aggregator_node(state: AgentState) -> dict:
    """结果聚合节点"""
    intent = state.get("intent", "unknown")
    if intent == "profile":
        reply = state.get("profile_reply", "画像对话已开始")
        return {"sse_buffer": [reply]}
    if intent == "resource":
        # ✅ 优先处理引导询问（类型不明确时）
        clarification = state.get("resource_clarification_msg")
        if clarification:
            return {"sse_buffer": [clarification]}

        topic = state.get("resource_topic", "")
        types = state.get("resource_types", [])
        if state.get("resource_skip_sync"):
            # 快速响应：告知前端通过 SSE 流式生成
            type_labels = ", ".join(types) if types else "学习资料"
            return {"sse_buffer": [f"✅ 正在为你生成{type_labels}，请稍候..."]}
        results = state.get("resource_results", {})
        return {"sse_buffer": [f"✅ 已生成 {len(results)} 类学习资源"]}
    if intent == "plan":
        plan = state.get("plan_result", {}) or {}
        stages = plan.get("stages", [])
        return {"sse_buffer": [f"✅ 已规划 {len(stages)} 个学习阶段"]}
    if intent == "tutor":
        reply = state.get("tutor_reply", "")
        return {"sse_buffer": [reply[:100] + "..."] if len(reply) > 100 else {"sse_buffer": [reply]}}
    return {"sse_buffer": ["好的，请告诉我你需要什么帮助"]}


# ====================================================================
#  构建 LangGraph
# ====================================================================


def build_graph() -> StateGraph:
    """构建 LangGraph StateGraph 编排引擎"""
    workflow = StateGraph(AgentState)

    # 注册节点
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("mode_conflict", mode_conflict_node)
    workflow.add_node("profile", profile_node)
    workflow.add_node("resource_gather", resource_node)
    workflow.add_node("resource_exec", resource_exec_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("tutor", tutor_node)
    workflow.add_node("result_aggregator", result_aggregator_node)
    workflow.add_node("unknown_handler", unknown_handler_node)

    # 入口 → 意图路由
    workflow.set_entry_point("intent_router")

    # 条件边：意图分流
    workflow.add_conditional_edges(
        "intent_router",
        intent_condition,
        {
            "profile": "profile",
            "resource": "resource_gather",
            "plan": "plan",
            "tutor": "tutor",
            "unknown": "unknown_handler",
        },
    )

    # 资源生成节点链（条件边：需要引导则跳过执行，直达聚合）
    def resource_gather_route(state: AgentState) -> str:
        if state.get("resource_clarification_msg"):
            return "result_aggregator"
        return "resource_exec"

    workflow.add_conditional_edges(
        "resource_gather",
        resource_gather_route,
        {
            "result_aggregator": "result_aggregator",
            "resource_exec": "resource_exec",
        },
    )

    # 汇聚到结果聚合
    workflow.add_edge("profile", "result_aggregator")
    workflow.add_edge("resource_exec", "result_aggregator")
    workflow.add_edge("plan", "result_aggregator")
    workflow.add_edge("tutor", "result_aggregator")
    workflow.add_edge("unknown_handler", "result_aggregator")
    workflow.add_edge("result_aggregator", END)

    # 编译（带内存检查点）
    graph = workflow.compile(checkpointer=MemorySaver())
    logger.info("[LangGraph] 编排引擎构建完成")
    return graph


# 全局图实例
orchestration_graph = build_graph()


# ====================================================================
#  对外统一调用接口
# ====================================================================


async def run_orchestrator(
    user_id: str,
    message: str,
    session_id: str = "",
    explicit_type: str = "",
    language: str = "",
    context_summary: str = "",
    context_history: Optional[list] = None,
) -> dict:
    """执行 LangGraph 编排（统一入口）"""
    initial = create_initial_state(
        user_id, message, session_id, explicit_type, language,
        context_summary, context_history,
    )
    config = {"configurable": {"thread_id": session_id or user_id}}
    try:
        result = await orchestration_graph.ainvoke(initial, config)
        return result
    except Exception as e:
        logger.exception(f"[编排] 执行异常")
        return {"intent": "unknown", "error": str(e), "sse_buffer": [f"处理出错: {str(e)[:100]}"]}


async def run_capability_stream(
    capability_name: str,
    **kwargs: Any,
) -> AsyncGenerator[dict, None]:
    """流式执行指定能力，产出 SSE 事件"""
    cap = get_capability(capability_name)
    if not cap:
        yield {"event": "error", "message": f"未知能力: {capability_name}"}
        return

    # 构建临时 state
    state = create_initial_state(
        user_id=kwargs.get("student_id", "anonymous"),
        user_message=kwargs.get("message", kwargs.get("topic", "")),
        session_id=kwargs.get("session_id", ""),
        explicit_type=capability_name,
        language=kwargs.get("language", ""),
    )

    async for event in cap.execute(state, **kwargs):
        yield event


__all__ = [
    "build_graph", "orchestration_graph",
    "run_orchestrator", "run_capability_stream",
    "intent_router_node", "intent_condition",
]
