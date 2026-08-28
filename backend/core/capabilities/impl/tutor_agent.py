"""
智能辅导 Agent
通过多模态方式解答学生疑问，支持联网搜索获取最新信息
"""
import logging
from typing import AsyncGenerator, Optional

from core.capabilities.impl.base_agent import BaseAgent
from core.models.schemas import StudentProfile
from core.models.profile import profile_manager
from services.rag import kb_client
from core.tools import tool_registry
from core.tools.search_tools import format_search_results
from core.utils.anti_hallucination import ANTI_HALLUCINATION_SYSTEM_PROMPT
from core.utils.content_filter import SAFETY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

TUTOR_SYSTEM_PROMPT = """你是彩迹熊AI学习助手，是具备完整思考与对话能力的智能学习辅助工具。

## 核心工作规则
1. 严格区分「画像采集」和「正常学习服务」两个阶段，禁止无限制循环提问。
2. 永远承接用户当前输入内容回复，禁止无视用户回答、重复抛出同一个问题。
3. 用户已回答过的画像问题，永久不再二次询问；用户明确提出学习需求时，优先响应学习需求，画像采集自动后置。

## 一、学习画像采集（仅信息缺失时触发）
- 仅当用户的学习画像信息不完整时，才逐步提问收集，每次只提1个问题。
- 采集维度包括：学习节奏偏好（慢速细学/快速速成）、薄弱知识点、学习目标。
- 用户回答后立即记录该信息，自动进入下一项未收集的维度；全部收集完成后，自动退出采集模式。
- 禁止重复询问同一问题，禁止在用户已答复后反复确认。

## 二、正常学习服务模式（默认主模式）
- 用户提出明确学习需求（如指定知识点、要学习资料、刷题、代码调试、答疑等），直接完整输出对应内容，不再穿插画像提问。
- 支持多轮上下文对话，记住历史对话信息，可承接上一轮内容进行补充、修改、讲解。
- 输出学习内容时结构清晰，可使用标题、列表、代码块，语言贴合学生理解水平。

## 硬性禁令
- 禁止输出完全重复的语句，禁止循环触发同一句提问。
- 禁止机械套用固定话术模板，自主思考生成自然回复。
- 禁止强行打断用户学习需求、跳回画像采集流程。

## 补充格式要求（前端渲染与上下文依赖，必须遵守）
- 提示词中的【学生画像】【对话历史】【参考资料】【网络搜索结果】等区块只是背景参考，**禁止照搬原文**，用自己的话回答。
- 回答直接以正文开头，严禁输出"助手：""AI："等角色标签。
- **出选择题时每个选项必须独占一行**（A. B. C. D. 各占一行），禁止挤在一行。

正确格式：
1. 下列哪个是正确的？
A. 选项一
B. 选项二
C. 选项三
D. 选项四

## 输出格式要求（生成学习内容时最高优先级，必须严格遵循）
禁止输出 Markdown 语法符号（#、##、```、---、**、>）。生成学习内容时按「概念解释 → 关键词强化 → 核心要素表格 → 注意事项」的结构组织：

一、概念解释：先用一段话讲清知识点本质，重点词汇自然强调。

二、关键词强化：以「✅ 关键词强化：」开头，列出最关键的 3~5 个术语/要点。

三、核心要素表格：知识点有明确要素时（如变量三要素 = 名称/值/类型），用表格列出「要素」与「说明」两列。

四、注意事项：以「⚠️ 注意：」开头，列出易错点、常见误区。

层级编号规则：一级用「一、」，二级用「1.1」，三级用「(1)」，纯中文数字编号。代码片段直接展示代码内容，前后不加反引号。
"""


class TutorAgent(BaseAgent):
    """
    智能辅导 Agent
    模型: spark-x2-flash（Agent模型，对话体验最流畅）
    功能: 即时答疑、多模态解答、个性化辅导
    """

    def __init__(self):
        super().__init__(
            name="TutorAgent",
            model_name="qwen-plus",
            system_prompt=(
                SAFETY_SYSTEM_PROMPT + "\n\n"
                + ANTI_HALLUCINATION_SYSTEM_PROMPT + "\n\n"
                + TUTOR_SYSTEM_PROMPT
            ),
            temperature=0.7,
        )

    def _build_tutor_context(self, profile: StudentProfile) -> str:
        """构建学生画像上下文"""
        mastered = profile.knowledge_base.get("mastered", [])
        weak = profile.knowledge_base.get("weak", [])
        style = profile.cognitive_style or "未确定"
        pace = profile.preferred_pace or "适中"

        context = f"【学生画像】\n- 认知风格：{style}\n- 学习节奏：{pace}\n"
        if mastered:
            context += f"- 已掌握：{', '.join(mastered[:5])}\n"
        if weak:
            context += f"- 薄弱点：{', '.join(weak[:3])}\n"
        context += "\n请根据以上画像调整回答方式。"
        return context

    async def answer(
        self,
        question: str,
        student_id: str = "anonymous",
        conversation_history: Optional[list[dict]] = None,
        language: str = "",
        context_summary: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        流式答疑，支持联网搜索获取最新信息

        :param question: 学生问题
        :param student_id: 学生ID
        :param conversation_history: 对话历史（最近 N 轮）
        :param language: 语言偏好（zh-CN, en-US, ja-JP 等）
        :param context_summary: 早期对话 LLM 摘要
        """
        # 1. 获取画像
        profile = profile_manager.get_profile(student_id)
        tutor_context = self._build_tutor_context(profile)

        # 2. RAG 检索相关知识
        context = ""
        try:
            retrieved_context, sources = await kb_client.rag_retrieve(question)
            if retrieved_context:
                context = f"\n参考资料：\n{retrieved_context}\n"
        except Exception as e:
            logger.warning(f"知识库检索失败: {e}")

        # 3. 联网搜索（针对需要最新信息的问题）
        search_context = ""
        search_used = False
        if self._needs_web_search(question):
            try:
                search_func = tool_registry.get("duckduckgo_search")
                if search_func:
                    search_results = await search_func(query=question, max_results=5)
                    if search_results:
                        search_context = f"\n\n网络搜索结果：\n{format_search_results(search_results)}\n"
                        search_used = True
                        logger.info(f"[智能辅导] 已为问题 '{question[:30]}...' 获取搜索结果")
            except Exception as e:
                logger.warning(f"联网搜索失败: {e}")

        # 4. 构建用户 prompt
        lang_hint = self._get_language_hint(language)
        prompt_parts = [
            f"学生问题：{question}",
            f"语言要求：{lang_hint}",
            tutor_context,
        ]
        if context:
            prompt_parts.append(context)
        if search_context:
            prompt_parts.append(search_context)
        if context_summary:
            prompt_parts.append(f"[早期对话总结]\n{context_summary}")
        if conversation_history:
            # 用「提问/解答」等描述性说法代替"学生：/助手："对话标签，避免模型模仿标签格式在回答前加"助手回答："
            history_text = "\n".join(
                f"{'学生提问' if m['role'] == 'user' else '老师解答'}：{m['content']}"
                for m in conversation_history[-6:]  # 最近6轮
            )
            prompt_parts.append(f"对话历史：\n{history_text}")

        prompt = "\n\n".join(prompt_parts)

        # 5. 流式生成回答
        if search_used:
            yield "[联网搜索] 正在获取最新信息..."

        async for chunk in self.generate_stream(prompt):
            yield chunk

    def _needs_web_search(self, question: str) -> bool:
        """
        判断问题是否需要联网搜索

        :param question: 学生问题
        :return: 是否需要搜索
        """
        search_keywords = [
            "最新", "最新消息", "最新进展", "最新动态", "最新发布",
            "2024", "2025", "2026", "今年", "现在",
            "怎么样", "好不好", "如何评价",
            "价格", "多少钱", "行情",
            "新闻", "报道", "事件",
            "趋势", "发展", "未来",
            "对比", "区别", "差异",
            "更新", "升级", "新版本",
        ]
        question_lower = question.lower()
        return any(keyword in question_lower for keyword in search_keywords)

    @staticmethod
    def _get_language_hint(language: str) -> str:
        """根据语言代码生成语言提示"""
        lang_map = {
            "zh-CN": "请使用简体中文回复",
            "en-US": "请使用英语回复 (Please respond in English)",
        }
        return lang_map.get(language, "请使用中文回复")

    async def process(self, question: str, student_id: str = "anonymous", **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.answer(
            question, student_id,
            kwargs.get("conversation_history"),
            kwargs.get("language", ""),
            kwargs.get("context_summary", ""),
        ):
            yield chunk


# 全局实例
tutor_agent = TutorAgent()
