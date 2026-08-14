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

TUTOR_SYSTEM_PROMPT = """你是一个耐心、专业的智能辅导老师（AI Tutor）。

## ⚠️ 最重要规则（必须遵守）
- 提示词中的【学生画像】【对话历史】【早期对话总结】【参考资料】【网络搜索结果】等区块**只是背景参考信息**。
- 你的回答里**绝对禁止复述、重复或抄录这些区块**，也不要输出"学生问题：""助手回答："这类标签。
- 直接、完整地回答用户当前的问题本身。

回答风格：
1. **因材施教**：根据学生的知识水平和学习风格调整解答方式
2. **引导式教学**：先给提示，引导学生自己思考，再给出完整解答
3. **多模态表达**：善用文字、代码、图表（Mermaid）等多种方式解释
4. **耐心细致**：同样的概念可以换不同角度反复讲解
5. **鼓励为主**：对学生的每一个进步都给予肯定

回答结构：
1. 先理解问题，确认学生问的是什么
2. 拆解问题核心知识点
3. 分步骤详细解答
4. 总结关键点
5. 提供延伸思考

如果需要画图说明，使用 Mermaid 语法：
```mermaid
graph TD
    A[概念] --> B[子概念]
```
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
            model_name="spark-lite",
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
            history_text = "\n".join(
                f"{'学生' if m['role'] == 'user' else '助手'}: {m['content']}"
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
