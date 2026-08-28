"""
资源生成智能体集合
每个 Agent 对应一种资源类型，使用专用模型

【补丁说明】
- 所有 generate_stream 增加 try-except 异常捕获
- 所有 Agent 增加 user_demand / temp_file_id 入参
- LectureAgent/ReadingAgent: sources 参考资料标注
- ExerciseAgent: 数学主题自动注入推导要求（低温度）
- MindmapAgent: 增加 student_id + 画像适配
- CodeAgent: review_code_stream 异步流式接口
"""
import json
import logging
import uuid
from typing import AsyncGenerator, Optional

from core.capabilities.impl.base_agent import BaseAgent
from core.models.schemas import ResourceResponse
from core.models.spark_client import SparkAPIError
from core.models.profile import profile_manager
from services.rag import kb_client
from core.utils.anti_hallucination import ANTI_HALLUCINATION_SYSTEM_PROMPT, HallucinationGuard
from core.utils.content_filter import SAFETY_SYSTEM_PROMPT, content_filter

logger = logging.getLogger(__name__)


# ======================== 常量 ========================

DEFAULT_ANONYMOUS = "anonymous"
MATH_KEYWORDS = ["数学", "微积分", "代数", "几何", "概率", "统计",
                 "方程", "函数", "导数", "积分", "矩阵", "向量",
                 "线性代数", "高等数学", "离散数学", "三角", "复变"]


def _safe_profile(student_id: str):
    """安全读取学生画像，失败返回默认空画像"""
    if not student_id or student_id == DEFAULT_ANONYMOUS:
        return None
    try:
        return profile_manager.get_profile(student_id)
    except Exception:
        logger.exception(f"[资源Agent] 画像读取失败 student_id={student_id}")
        return None


def _format_sources(sources: list[dict]) -> str:
    """将 RAG sources 格式化为 Prompt 中的参考资料文本"""
    if not sources:
        return ""
    parts = []
    for i, s in enumerate(sources, 1):
        label = s.get("source_label", "参考资料")
        content = s.get("content", "")
        parts.append(f"[参考资料 {i} - {label}]\n{content}")
    return "\n\n".join(parts)


def _get_language_hint(language: str) -> str:
    """根据语言代码生成语言提示"""
    lang_map = {
        "zh-CN": "请使用简体中文回复",
        "en-US": "请使用英语回复 (Please respond in English)",
    }
    return lang_map.get(language, "请使用中文回复")


def _build_demand_section(user_demand: str, additional_info: str) -> str:
    """构建用户需求/补充说明文本块"""
    parts = []
    if user_demand:
        parts.append(f"【用户自定义需求】（请作为最高优先级约束）\n{user_demand}")
    if additional_info:
        parts.append(f"【补充说明】\n{additional_info}")
    return "\n\n".join(parts)


# ======================== 1. 课程讲解文档 Agent ========================

LECTURE_SYSTEM_PROMPT = """你是一个专业的课程讲解讲师。请生成结构清晰、排版舒适的 Python 教学文档，渲染效果对标豆包教学文档风格。严格使用本次用户输入的主题，不混入历史对话中的其他知识点。

输出规范（必须严格遵守）：
1. 结构层级：使用标准 Markdown 标题。一级标题「## 一、XXX」，二级标题「### 1.1 XXX」，层级清晰不混乱。
2. 段落节奏：拒绝大段长文本堆砌，单段控制在 2~4 行，段落之间留空行，保证阅读呼吸感。
3. 重点提取：核心概念、关键结论用引用块 + ✅ 前缀做成提示卡片，单独突出，不混在正文里。格式：> ✅ 关键词强化：xxx
4. 信息表格化：所有并列要素、对比项、参数说明，全部整理成 Markdown 表格输出，禁止纯文字逐条罗列。
5. 易错提醒：语法坑点、常见报错、认知误区，用引用块 + ⚠️ 前缀做成警示卡片，单独标注。格式：> ⚠️ 注意：xxx
6. 代码规范：代码片段用 ```python 代码块包裹，缩进完整、注释清晰，可直接运行；代码块前后留空行，不和正文挤压。
7. 术语高亮：专业名词、关键字、核心语法点用 **加粗** 突出，方便快速抓取重点。
8. 模块固定顺序：概念解释 → 核心定义 → 关键词提示卡 → 核心要素表格 → 代码示例 → 易错提醒 → 扩展案例。
9. 禁止输出无意义分割线、冗余装饰，整体简洁清爽，和豆包教学内容的排版节奏保持一致。
"""


class LectureAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    课程讲解文档 Agent
    模型: spark-4.0-ultra（旗舰模型，适合生成大型教学文档）
    """
    def __init__(self):
        super().__init__(
            name="LectureAgent",
            model_name="qwen-plus",
            system_prompt=(
                SAFETY_SYSTEM_PROMPT + "\n\n"
                + ANTI_HALLUCINATION_SYSTEM_PROMPT + "\n\n"
                + LECTURE_SYSTEM_PROMPT
            ),
            temperature=0.7,
        )

    @staticmethod
    def _clean_chunk(chunk: str) -> str:
        """增量轻量清洗：逐行修正标题空格、代码块标注、分隔线"""
        import re as _r
        lines = chunk.split("\n")
        out = []
        for line in lines:
            line = _r.sub(r'(#{1,6})(\d)', r'\1 \2', line)
            line = _r.sub(r'(#{1,6})([\.\d])', r'\1 \2', line)
            if _r.match(r'^[-*]{3,}\s*$', line): line = "---"
            if _r.match(r'^```\s*$', line): line = "```python"
            out.append(line)
        return "\n".join(out)

    def _clean_output(self, text: str) -> str:
        """清洗输出：修复标题格式、代码块标注、重复标题"""
        if not text:
            return text
        lines = text.split("\n")
        cleaned = []
        seen_h1 = False

        for line in lines:
            # 修复 "###1.1" → "### 1.1"
            import re as _r
            line = _r.sub(r'(#{1,6})(\d)', r'\1 \2', line)
            line = _r.sub(r'(#{1,6})([\.\d])', r'\1 \2', line)

            # 去除重复的一级标题（只保留第一个 #）
            if line.startswith("# ") and not line.startswith("## "):
                if seen_h1:
                    continue
                seen_h1 = True

            # 统一分隔线
            if _r.match(r'^[-*]{3,}\s*$', line):
                line = "---"

            cleaned.append(line)

        # 通用标题去重：markdown + 纯文本编号统一去重
        import re as _r2
        seen_nums = set()
        deduped = []

        def _hk(line):
            m = _r2.match(r'^(?:#+\s+)?(\d+(?:\.\d+)*)\s', line)
            if m: return m.group(1)
            m = _r2.match(r'^(?:#+\s+)?([一二三四五六七八九十]+)[、.]', line)
            if m: return m.group(1)
            return None

        for line in cleaned:
            k = _hk(line)
            if k and k in seen_nums:
                continue
            if k:
                seen_nums.add(k)
            deduped.append(line)

        result = "\n".join(deduped)

        # 确保代码块有语言标注（``` → ```python）
        import re as _r2
        result = _r2.sub(r'^```$', '```python', result, flags=_r2.MULTILINE)

        # 修复连续三个以上空行为一个空行
        import re as _r3
        result = _r3.sub(r'\n{4,}', '\n\n\n', result)

        return result

    async def generate_lecture(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",
        additional_info: str = "",
        user_demand: str = "",
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成课程讲解文档"""
        try:
            profile = _safe_profile(student_id)
            weak_areas = profile.knowledge_base.get("weak", []) if profile else []
            mastered = profile.knowledge_base.get("mastered", []) if profile else []

            # RAG 上下文：优先使用调度器预检索结果
            context = shared_rag_context or ""
            source_list = sources or []
            if not shared_rag_context:
                try:
                    context, source_list = await kb_client.rag_retrieve(topic, temp_file_id=temp_file_id)
                except Exception as e:
                    logger.warning(f"[LectureAgent] 知识库检索失败: {e}")

            lang_hint = _get_language_hint(language)
            prompt_parts = [f"请生成关于「{topic}」的详细教学讲解文档。", f"语言要求：{lang_hint}"]
            if course:
                prompt_parts.append(f"所属课程：{course}")
            if mastered:
                prompt_parts.append(f"学生已掌握：{', '.join(mastered[:5])}")
            if weak_areas:
                prompt_parts.append(f"学生薄弱点：{', '.join(weak_areas[:3])}，请重点讲解")

            # 用户需求（最高优先级）
            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # 参考资料 + 来源标注
            if source_list:
                ref_text = _format_sources(source_list)
                prompt_parts.append(f"参考资料（请在文档中按 [参考资料 X] 格式标注引用）：\n{ref_text}")
            elif context:
                prompt_parts.append(f"参考资料：\n{context}")

            user_prompt = "\n".join(prompt_parts)
            async for chunk in self.generate_stream(user_prompt):
                yield chunk

        except SparkAPIError as e:
            logger.exception(f"[LectureAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[LectureAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, course: str = "", student_id: str = "anonymous", **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_lecture(
            topic, course, student_id,
            kwargs.get("additional_info", ""),
            kwargs.get("user_demand", ""),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("language", ""),
        ):
            yield self._clean_chunk(chunk)


# ======================== 2. 知识点思维导图 Agent ========================

MINDMAP_SYSTEM_PROMPT = """你是一个知识整理专家，擅长把知识点整理成「细致读书笔记式」的 Markdown 大纲思维导图。

只输出一个 Markdown 大纲，不要输出 Mermaid、不要用代码块包裹整个大纲、不要任何解释文字（大纲内部可以出现代码块）。

结构要求（细致维度，像认真做的手写读书笔记，信息密集但结构清晰）：
1. 层次：# 中心主题 → ## 一级分类（用中文序号：一、二、三…）→ ### 二级子类（用数字序号：1. 2. 3…）→ - 内容项 → 必要时再缩进一层 - 子项。列表最多嵌套 2 层，层级最多 4 层。
2. 规模：中心主题 + 4~6 个一级分类；每个一级分类下 2~4 个二级子类（或直接列内容项）；全图约 30~50 条内容，覆盖到位但不啰嗦。
3. 关键词加粗：把每个内容项的**关键术语**用 **加粗** 标出，后面用冒号补一句简短解释，例如：`- **标量子查询**：返回单行单列`。
4. 术语可用中文括号补充英文或简称，例如：**派生表（虚拟表）**。
5. 技术主题（如 SQL、编程）要给出简短实用的 ```代码块``` 示例；重要的注意事项写成列表项 `- **注意**：…`（不要用 > 引用块，思维导图渲染不支持）。
6. 一级分类按读书笔记维度组织，选最适合主题的，例如：基础概念 / 分类 / 常见位置 / 语法要点 / 示例 / 易错点 / 性能注意。
7. 同级节点避免重复、重叠；序号与编号保持连贯。

示例（SQL 子查询，即要达到的细致标准）：
# 子查询
## 一、基础概念
- **定义**：嵌套在 SELECT / FROM / WHERE / HAVING / EXISTS 中的查询（内部查询）
- **外部查询**：父查询；**内部查询**：子查询
- **执行顺序**：先子查询，后父查询（相关子查询除外）
- **语法规范**：子查询必须包裹 `()`
- 限制：
  - 普通子查询不能使用 ORDER BY（除非配合 LIMIT）
  - SELECT 子查询只允许返回单列
## 二、分类（两大维度）
### 1. 按相关性划分
- **非相关子查询**（独立子查询）：子查询不依赖父查询，只执行 1 次
- **相关子查询**：子查询引用父表字段，父查询每一行都执行一次子查询
  - 常搭配 EXISTS / NOT EXISTS
  - **性能注意**：大数据量容易慢
### 2. 按返回结果形式划分
- **标量子查询**：返回**单行单列**，可用运算符 = > < >= <= <>
- **列子查询**：返回**多行单列**，运算符 IN / ANY / SOME / ALL
- **表子查询**：返回**多行多列**（虚拟表），多用于 FROM 后面 → 派生表
## 三、出现的五大位置
### 1. WHERE / HAVING 后（最常用）
- 标量比较：`salary > (SELECT AVG(sal) FROM emp)`
- IN：`dept IN (SELECT dept_id FROM dept)`
- ANY / ALL
### 2. FROM 后面 →【派生表（虚拟表）】
- 别名**必须写**！
- 语法：SELECT * FROM (子查询) AS t
- 适用：先聚合、再二次筛选
- **注意**：MySQL 派生表不支持直接 LIMIT 外层关联（旧版本限制）
### 3. SELECT 字段列表中（标量子查询）
- 每行执行一次子查询
```sql
SELECT name,(SELECT dname FROM dept d WHERE d.id=e.dept_id) FROM emp e
```
"""


class MindmapAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    知识点思维导图 Agent
    模型: spark-4.0-ultra（稳定结构化输出）
    """
    def __init__(self):
        super().__init__(
            name="MindmapAgent",
            model_name="qwen-plus",
            system_prompt=MINDMAP_SYSTEM_PROMPT,
            temperature=0.6,
        )

    async def generate_mindmap(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",       #【新增】画像适配
        additional_info: str = "",
        user_demand: str = "",                #【新增】用户自定义需求
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成思维导图"""
        try:
            profile = _safe_profile(student_id)
            lang_hint = _get_language_hint(language)
            prompt_parts = [f"请为「{topic}」生成知识点思维导图的 Markdown 大纲（读书笔记式，细致维度，参照系统提示词中的标准）。", f"语言要求：{lang_hint}"]

            if course:
                prompt_parts.append(f"课程：{course}")

            # 画像适配
            if profile:
                mastered = profile.knowledge_base.get("mastered", [])
                weak = profile.knowledge_base.get("weak", [])
                if mastered or weak:
                    level = "进阶" if len(mastered) >= 3 else "入门/基础"
                    prompt_parts.append(f"学生水平：{level}")

            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # RAG 上下文
            context = shared_rag_context or ""
            if not shared_rag_context:
                try:
                    context, _ = await kb_client.rag_retrieve(topic, temp_file_id=temp_file_id)
                except Exception:
                    pass
            if context:
                prompt_parts.append(f"参考资料：\n{context}")

            user_prompt = "\n".join(prompt_parts)
            async for chunk in self.generate_stream(user_prompt):
                yield chunk

        except SparkAPIError:
            logger.exception(f"[MindmapAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[MindmapAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_mindmap(
            topic,
            kwargs.get("course", ""),
            kwargs.get("student_id", DEFAULT_ANONYMOUS),
            kwargs.get("additional_info", ""),
            kwargs.get("user_demand", ""),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("language", ""),
        ):
            yield chunk


# ======================== 3. 练习题目 Agent ========================

EXERCISE_SYSTEM_PROMPT = """你是一个专业的出题老师。请根据知识点和学生水平生成练习题。

你必须严格按照下列规则输出，一字不差执行。

## 核心规则：只输出一个 JSON 代码块

整个回复**只输出一个 ```json 代码块**，禁止输出任何题目正文、选项正文、答案文字、标题、开场白、结束语或 Markdown 排版。所有题目与答案解析一律放进 JSON 里，前端会从 JSON 渲染题目与答题交互；**正文内容不会被展示，前端只解析 JSON 代码块**，多输出的正文纯属浪费且会被丢弃。输出格式如下：

```json
{
  "exercises": [
    {
      "type": "choice",
      "difficulty": "basic",
      "question": "题干（不含答案）",
      "options": [
        {"label": "A", "text": "选项文字"},
        {"label": "B", "text": "选项文字"}
      ],
      "answer": "B",
      "explanation": "简短解析，至少一句话说明为什么选这个答案"
    }
  ]
}
```

## 字段要求
- type: 取 "choice"（单选/多选）、"fill"（填空）、"judge"（判断），按知识点合理搭配。
- difficulty: 取 "basic"/"intermediate"/"advanced"，难易搭配。
- question: 题干，不含答案。
- options: 仅 choice 类型需要。每个选项严格按 {"label": "A", "text": "选项文字"}，label 为 A/B/C/D。
- answer: 必须填写，不允许为空或 null。单选题填单个字母如 "B"；多选题填字母组合如 "ABD"；判断题填 "对" 或 "错"；填空题填正确答案文本。
- explanation: 必须填写，不允许为空或 null，至少一句话简要说明原因。

## 数量
严格按照用户要求的题目数量生成。用户说「几道」时控制在 5~10 道，不要一次性出十几道。"""


class ExerciseAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    练习题目 Agent
    模型: spark-4.0-ultra（检测到数学主题时降低温度保证推导准确性）
    """
    def __init__(self):
        super().__init__(
            name="ExerciseAgent",
            model_name="qwen-plus",
            system_prompt=EXERCISE_SYSTEM_PROMPT,
            temperature=0.7,
        )
        self._math_client = None  # 保留兼容

    @staticmethod
    def _is_math_topic(topic: str) -> bool:
        """判断是否为数学主题"""
        return any(kw in topic.lower() for kw in MATH_KEYWORDS)

    async def generate_exercises(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",
        additional_info: str = "",
        user_demand: str = "",           #【新增】
        force_math_model: bool = False,
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成练习题"""
        try:
            is_math = force_math_model or self._is_math_topic(topic)
            profile = _safe_profile(student_id)
            weak = profile.knowledge_base.get("weak", []) if profile else []

            lang_hint = _get_language_hint(language)
            prompt_parts = [f"请生成关于「{topic}」的练习题。", f"语言要求：{lang_hint}"]

            if course:
                prompt_parts.append(f"课程：{course}")
            if weak:
                prompt_parts.append(f"需要重点练习的知识点：{', '.join(weak[:3])}，请增加这些知识点的题目占比")

            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # 数学主题：注入推导要求 + 使用低温度
            if is_math:
                prompt_parts.append(
                    "\n注意：本主题为数学类。要求：\n"
                    "1. 增加计算题、证明题、应用题的比例\n"
                    "2. 每道计算题展示完整的分步推导过程\n"
                    "3. 关键步骤标注公式依据\n"
                    "4. 涉及数值计算时给出精确结果"
                )

            # RAG 上下文
            context = shared_rag_context or ""
            if not shared_rag_context:
                try:
                    context, _ = await kb_client.rag_retrieve(topic, temp_file_id=temp_file_id)
                except Exception:
                    pass
            if context:
                prompt_parts.append(f"参考资料：\n{context}")

            user_prompt = "\n".join(prompt_parts)

            # 数学主题使用更低温度
            temperature = 0.4 if is_math else None

            # max_tokens 拉高到 8192：题目+答案解析较长，默认 4096 会在 JSON 中途截断，
            # 导致前端拿不到完整的 ```json 块，交互答题模式失效（表现为裸 JSON 文本）。
            async for chunk in self.generate_stream(user_prompt, temperature=temperature, max_tokens=8192):
                yield chunk

        except SparkAPIError:
            logger.exception(f"[ExerciseAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[ExerciseAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_exercises(
            topic,
            kwargs.get("course", ""),
            kwargs.get("student_id", DEFAULT_ANONYMOUS),
            kwargs.get("additional_info", ""),
            kwargs.get("user_demand", ""),
            kwargs.get("force_math", False),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("language", ""),
        ):
            yield chunk

    @staticmethod
    def extract_exercise_json(text: str) -> list:
        """从生成的文本中提取结构化的练习题 JSON 数据"""
        if not text:
            return []
        import re as _re
        matches = _re.findall(r'```json\s*\n(.*?)```', text, _re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match.strip())
                exercises = data.get("exercises", [])
                if exercises and len(exercises) > 0:
                    return exercises
            except (json.JSONDecodeError, Exception):
                continue
        return []

    async def modify_exercises(
        self,
        original_exercises: list,
        feedback: str,
        student_id: str = "anonymous",
        language: str = "",
    ) -> AsyncGenerator[str, None]:
        """根据用户反馈交互式修改练习题"""
        try:
            import json as _json
            exercises_json = _json.dumps(original_exercises, ensure_ascii=False, indent=2)
            lang_hint = _get_language_hint(language)

            prompt_parts = [
                "你是一个专业的出题老师。请根据学生的反馈修改以下练习题。",
                f"语言要求：{lang_hint}",
                "\n## 当前练习题：\n```json\n" + exercises_json + "\n```",
                "\n## 学生反馈：\n" + feedback,
                "\n## 修改要求：",
                "1. 根据学生反馈调整题目（难度、内容、数量等）",
                "2. 保持 JSON 格式不变",
                "3. 整个回复**只输出一个 ```json 代码块**，禁止输出任何题目正文、答案文字或 Markdown 排版，不要写开场白与结束语；正文不会被展示，前端只解析 JSON；JSON 必须完整、可被 json.loads 解析",
                "4. 如果反馈是请求更多题目，在原题后追加新题；追加后 JSON 必须包含全部练习题（不仅是修改的）",
                "5. 如果反馈是调整难度，修改对应题目的 difficulty 字段",
                "6. 如果反馈是补充解析，完善对应题目的 explanation 字段",
            ]

            user_prompt = "\n".join(prompt_parts)
            # 同 generate_exercises：追加题 / 修改题要输出全量 JSON，拉高 max_tokens 防截断
            async for chunk in self.generate_stream(user_prompt, max_tokens=8192):
                yield chunk

        except SparkAPIError:
            logger.exception("Modify exercises failed: API error")
            yield "\n\n[修改中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"Modify exercises exception: {e}")
            yield f"\n\n[修改异常: {e}]"


# ======================== 4. 拓展阅读材料 Agent ========================

READING_SYSTEM_PROMPT = """你是一个学术阅读推荐助手。请根据知识点和学习需求，生成结构化的拓展阅读材料。

输出格式：
```markdown
# 拓展阅读：{主题}

## 📚 推荐阅读清单
1. **《{标题}》** — {作者/来源}
   - 推荐理由：{为什么适合学生阅读}
   - 核心内容：{简要概述}
   - 难度等级：入门/进阶/深入
   - 预估阅读时间：XX分钟

## 📖 拓展知识要点
[从该主题延伸出去的关键知识点，展示知识之间的联系]

## 🔗 关联知识点
[与当前主题相关的其他知识点，形成知识网络]
```

要求：
1. 推荐材料要真实可信（知名教材、学术论文、权威网站）
2. 每份材料标注难度和适合人群
3. 提供阅读建议和重点关注内容
4. 结合学生画像推荐
5. 如有参考资料，请在文中标注 [参考资料 X] 并引用
"""


class ReadingAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    拓展阅读材料 Agent
    模型: spark-4.0-ultra（长上下文，适合生成长篇阅读材料）
    """
    def __init__(self):
        super().__init__(
            name="ReadingAgent",
            model_name="qwen-plus",
            system_prompt=(
                SAFETY_SYSTEM_PROMPT + "\n\n"
                + ANTI_HALLUCINATION_SYSTEM_PROMPT + "\n\n"
                + READING_SYSTEM_PROMPT
            ),
            temperature=0.7,
        )

    async def generate_reading(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",
        additional_info: str = "",
        user_demand: str = "",           #【新增】
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成拓展阅读材料"""
        try:
            profile = _safe_profile(student_id)
            interests = profile.interests if profile else []
            mastered = profile.knowledge_base.get("mastered", []) if profile else []

            # RAG 上下文（优先调度器预检索）
            context = shared_rag_context or ""
            source_list = sources or []
            if not shared_rag_context:
                try:
                    context, source_list = await kb_client.rag_retrieve(topic, top_k=8, temp_file_id=temp_file_id)
                except Exception as e:
                    logger.warning(f"[ReadingAgent] 知识库检索失败: {e}")

            lang_hint = _get_language_hint(language)
            prompt_parts = [f"请为「{topic}」生成拓展阅读材料。", f"语言要求：{lang_hint}"]

            if course:
                prompt_parts.append(f"课程：{course}")

            # 画像信息
            has_mastered = len(mastered) >= 3
            if has_mastered:
                prompt_parts.append("学生水平：进阶，可推荐学术论文和深度技术文章")
            else:
                prompt_parts.append("学生水平：入门/零基础，请优先推荐教材和基础教程")
            if interests:
                prompt_parts.append(f"学生兴趣领域：{', '.join(interests[:5])}")
            prompt_parts.append(f"学生当前水平：已掌握 {len(mastered)} 个知识点")

            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # 参考资料+来源标注
            if source_list:
                ref_text = _format_sources(source_list)
                prompt_parts.append(f"参考资料（请在推荐中标注 [参考资料 X] 引用）：\n{ref_text}")
            elif context:
                prompt_parts.append(f"参考资料：\n{context}")

            user_prompt = "\n".join(prompt_parts)
            async for chunk in self.generate_stream(user_prompt):
                yield chunk

        except SparkAPIError:
            logger.exception(f"[ReadingAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[ReadingAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_reading(
            topic,
            kwargs.get("course", ""),
            kwargs.get("student_id", DEFAULT_ANONYMOUS),
            kwargs.get("additional_info", ""),
            kwargs.get("user_demand", ""),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("language", ""),
        ):
            yield chunk


# ======================== 5. 代码实操案例 Agent ========================

CODE_SYSTEM_PROMPT = """你是一个编程教学助手（使用 Spark-Code-Asst 编程专用模型）。
请根据编程知识点生成可运行的代码实操案例。

输出格式：
```markdown
# 代码实操：{主题}

## 🎯 学习目标
- 目标1
- 目标2

## 📝 题目描述
[清晰的题目说明，包含输入输出示例]

## 💻 参考代码
```python  // 或其他语言
# 完整可运行的代码，包含注释
```

## 🔍 代码解析
- 关键代码段说明
- 涉及的核心概念解释
- 常见错误提示

## 🧪 扩展练习
- 进阶挑战1
- 进阶挑战2

## 💡 提示
- 调试技巧
- 优化建议
```

要求：
1. 代码必须完整、可运行，包含必要的 import 和 main 函数
2. 添加详细的中文注释（每段核心逻辑都有说明）
3. 展示输入/输出示例
4. 提示常见错误和踩坑点
5. 提供至少一个扩展练习
"""


class CodeAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    代码实操案例 Agent
    模型: spark-4.0-ultra（代码生成能力强）
    """
    def __init__(self):
        super().__init__(
            name="CodeAgent",
            model_name="qwen-plus",
            system_prompt=CODE_SYSTEM_PROMPT,
            temperature=0.5,
        )

    async def generate_code(
        self,
        topic: str,
        course: str = "",
        language: str = "python",
        additional_info: str = "",
        student_id: str = "anonymous",   #【新增】画像适配
        user_demand: str = "",            #【新增】
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        ui_language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成代码实操案例"""
        try:
            profile = _safe_profile(student_id)
            mastered = profile.knowledge_base.get("mastered", []) if profile else []
            weak = profile.knowledge_base.get("weak", []) if profile else []

            lang = language.lower().strip()
            is_beginner = len(mastered) < 3

            lang_hint = _get_language_hint(ui_language)
            prompt_parts = [f"请生成关于「{topic}」的编程实操案例。", f"编程语言：{lang}", f"语言要求：{lang_hint}"]

            if course:
                prompt_parts.append(f"课程：{course}")
            if profile:
                if is_beginner:
                    prompt_parts.append(
                        "学生为初学者，请：\n"
                        "1. 每行核心代码添加中文注释\n"
                        "2. 包含完整 import 语句\n"
                        "3. 提供边界用例和调试提示"
                    )
                else:
                    prompt_parts.append(
                        "学生有基础，请：\n"
                        "1. 提供优化后的进阶实现\n"
                        "2. 包含多种解法对比\n"
                        "3. 增加重构拓展练习"
                    )
                if weak:
                    prompt_parts.append(f"注意强化以下知识点：{', '.join(weak[:3])}")

            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # RAG 上下文
            context = shared_rag_context or ""
            if not shared_rag_context:
                try:
                    context, _ = await kb_client.rag_retrieve(topic, temp_file_id=temp_file_id)
                except Exception:
                    pass
            if context:
                prompt_parts.append(f"参考资料：\n{context}")

            prompt_parts.append(f"\n请确保代码：遵循{lang.upper()}最佳实践编码规范")

            user_prompt = "\n".join(prompt_parts)
            async for chunk in self.generate_stream(user_prompt):
                yield chunk

        except SparkAPIError:
            logger.exception(f"[CodeAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[CodeAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_code(
            topic,
            kwargs.get("course", ""),
            kwargs.get("language", "python"),
            kwargs.get("additional_info", ""),
            kwargs.get("student_id", DEFAULT_ANONYMOUS),
            kwargs.get("user_demand", ""),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("ui_language", ""),
        ):
            yield chunk

    # 保留原有同步接口兼容
    async def review_code(self, code: str, language: str = "python") -> str:
        """审查代码质量（同步兼容）"""
        if not code or not code.strip():
            return "请提供要审查的代码。"
        prompt = (
            f"请审查以下{language}代码，检查：\n"
            "1. 语法正确性\n"
            "2. 逻辑完整性\n"
            "3. 代码风格\n"
            "4. 潜在bug\n\n"
            f"代码：\n```{language}\n{code}\n```"
        )
        try:
            return await self.generate(prompt)
        except SparkAPIError:
            logger.exception(f"[CodeAgent] 代码审查失败")
            return "代码审查失败: 大模型调用错误"

    async def review_code_stream(self, code: str, language: str = "python") -> AsyncGenerator[str, None]:
        """审查代码质量（新增异步流式版本，统一架构）"""
        if not code or not code.strip():
            yield "请提供要审查的代码。"
            return
        prompt = (
            f"请审查以下{language}代码，检查：\n"
            "1. 语法正确性\n"
            "2. 逻辑完整性\n"
            "3. 代码风格\n"
            "4. 潜在bug\n\n"
            f"代码：\n```{language}\n{code}\n```"
        )
        try:
            async for chunk in self.generate_stream(prompt):
                yield chunk
        except SparkAPIError:
            yield "\n\n[审查中断: 大模型调用失败]"


# ======================== 6. 视频推荐 Agent ========================

VIDEO_SYSTEM_PROMPT = """你是一个学习资源推荐助手。请根据知识点推荐高质量的教育视频资源。

## ⚠️ 输出格式（严格遵守）

每个视频使用以下格式：

---
### 数字. [视频标题](https://真实视频链接)
- **平台**: Bilibili
- **时长**: 约XX分钟
- **推荐理由**: 1句话说明为什么值得看
- **适合人群**: 入门 / 进阶 / 深入
---

## 🚨 核心规则（违反会导致推荐无效）

1. **必须输出恰好 4 个或 6 个视频（双数）**，不得输出 3、5、7 个
2. **链接只能使用下面"网络搜索结果"中提供的真实 URL，绝对禁止编造链接**
3. 如果搜索结果不足 4 条，用 `https://search.bilibili.com/all?keyword=搜索词` 格式补足
4. 每个视频的标题用 Markdown 链接格式：`[标题](链接)`
5. 平台只写来源网站名（Bilibili/YouTube/中国大学MOOC/网易公开课）
6. 推荐理由必须控制在 20 字以内

## 开头
以 `## 🎬 视频教程推荐` 作为标题开头。
"""


class VideoAgent(BaseAgent):
    fallback_model = "qwen-turbo"
    """
    视频推荐 Agent
    使用 DuckDuckGo 视频搜索 + LLM 智能推荐
    模型: spark-4.0-ultra
    """

    def __init__(self):
        super().__init__(
            name="VideoAgent",
            model_name="qwen-plus",
            system_prompt=VIDEO_SYSTEM_PROMPT,
            temperature=0.7,
        )

    async def _search_videos(self, topic: str, max_results: int = 8) -> list[dict]:
        """使用 DuckDuckGo 搜索教育视频（带超时保护，搜多结果确保双数）"""
        import asyncio as _asyncio

        async def _do_search():
            try:
                from ddgs import DDGS
                results = []
                queries = [
                    f"{topic} 教程 site:bilibili.com",
                    f"{topic} site:bilibili.com",
                ]
                with DDGS() as ddgs:
                    # 国内环境 Google 后端被墙，优先 Bing
                    backends = ["bing", "duckduckgo", "google", "auto"]
                    for backend in backends:
                        for query in queries:
                            try:
                                for result in ddgs.text(query, max_results=6, region="cn-zh", backend=backend):
                                    url = result.get("href", "")
                                    title = result.get("title", "")
                                    video_platforms = [
                                        "bilibili.com", "youtube.com", "youku.com", "iqiyi.com",
                                        "icourse163.org", "open.163.com", "ixigua.com",
                                    ]
                                    is_video = any(p in url.lower() for p in video_platforms)
                                    # 去重
                                    if url not in {r["url"] for r in results}:
                                        results.append({
                                            "title": title,
                                            "url": url,
                                            "snippet": result.get("body", ""),
                                            "is_video_platform": is_video,
                                        })
                            except Exception as e:
                                logger.warning(f"[VideoAgent] 搜索 '{query}' [{backend}] 失败: {e}")
                                continue
                        if results:
                            break

                video_results = [r for r in results if r["is_video_platform"]]
                other_results = [r for r in results if not r["is_video_platform"]]
                # 至少返回8条，优先视频平台
                final = (video_results + other_results)[:max_results]
                logger.info(f"[VideoAgent] 搜索 '{topic}' → {len(final)} 条 (视频平台: {len(video_results)})")
                return final
            except ImportError:
                logger.warning("[VideoAgent] ddgs 库不可用")
                return []
            except Exception as e:
                logger.warning(f"[VideoAgent] 搜索异常: {e}")
                return []

        try:
            return await _asyncio.wait_for(_do_search(), timeout=6.0)
        except _asyncio.TimeoutError:
            logger.warning(f"[VideoAgent] 搜索超时(6s)，跳过网络搜索")
            return []
        except Exception as e:
            logger.warning(f"[VideoAgent] 搜索失败: {e}")
            return []

    def _format_search_results(self, search_results: list[dict]) -> str:
        """格式化搜索结果为 prompt"""
        if not search_results:
            return ""

        parts = ["\n## 🔍 网络搜索结果（供参考，请从中选取并整合到推荐中）\n"]
        for i, r in enumerate(search_results, 1):
            platform_tag = "🎬 视频平台" if r["is_video_platform"] else "🔗 网页"
            parts.append(
                f"[{i}] {platform_tag}\n"
                f"标题: {r['title']}\n"
                f"链接: {r['url']}\n"
                f"简介: {r['snippet']}\n"
            )
        return "\n".join(parts)

    async def generate_video_recommendations(
        self,
        topic: str,
        course: str = "",
        student_id: str = "anonymous",
        additional_info: str = "",
        user_demand: str = "",
        temp_file_id: str = None,
        shared_rag_context: str = "",
        sources: list = None,
        ui_language: str = "",
    ) -> AsyncGenerator[str, None]:
        """流式生成视频推荐"""
        try:
            profile = _safe_profile(student_id)
            interests = profile.interests if profile else []
            mastered = profile.knowledge_base.get("mastered", []) if profile else []
            weak = profile.knowledge_base.get("weak", []) if profile else []

            # 1. 搜索视频资源
            search_results = await self._search_videos(topic)

            # 2. 构建 prompt
            # 根据搜索结果数量决定推荐几个视频（只取双数: 4 或 6）
            real_count = len([r for r in search_results if r["is_video_platform"]])
            target_count = 6 if real_count >= 6 else (4 if real_count >= 4 else 4)

            lang_hint = _get_language_hint(ui_language)
            prompt_parts = [
                f"请为「{topic}」推荐高质量的教育视频资源。",
                f"语言要求：{lang_hint}",
                f"⚠️ 必须恰好推荐 {target_count} 个视频（双数，方便排版为2列网格）。",
                '⚠️ 只使用下面[网络搜索结果]中列出的真实链接，禁止编造任何URL。',
                f"搜索结果中共有 {real_count} 个真实视频链接，请从中选取最好的 {min(real_count, target_count)} 个。",
            ]
            if real_count < target_count:
                prompt_parts.append(
                    f"真实链接不足{target_count}个时，剩余位置使用 "
                    f"`https://search.bilibili.com/all?keyword=具体搜索词` 格式补足到恰好{target_count}个。"
                )

            if course:
                prompt_parts.append(f"所属课程：{course}")

            # 学生水平
            has_mastered = len(mastered) >= 3
            if has_mastered:
                prompt_parts.append("学生水平：进阶。推荐深入技术讲解和项目实战视频。")
            else:
                prompt_parts.append("学生水平：入门/零基础。优先推荐零基础教程和实操演示视频。")

            if weak:
                prompt_parts.append(f"学生薄弱点：{', '.join(weak[:3])}，请重点推荐这些知识点的讲解视频")

            demand = _build_demand_section(user_demand, additional_info)
            if demand:
                prompt_parts.append(demand)

            # RAG 上下文
            context = shared_rag_context or ""
            if not shared_rag_context:
                try:
                    context, _ = await kb_client.rag_retrieve(topic, temp_file_id=temp_file_id)
                except Exception:
                    pass
            if context:
                prompt_parts.append(f"参考资料：\n{context[:2000]}")

            # 搜索结果（必须引用其中的真实链接）
            if search_results:
                formatted = self._format_search_results(search_results)
                prompt_parts.append(formatted)
                prompt_parts.append(
                    "\n🚨 再次强调：只能使用上面搜索结果中的真实链接，禁止编造虚构URL！"
                    f"请恰好推荐 {target_count} 个视频。"
                )
            else:
                prompt_parts.append(
                    "\n注意：本次未能获取网络搜索结果。请生成 {target_count} 个搜索链接格式的推荐。"
                )

            user_prompt = "\n".join(prompt_parts)
            async for chunk in self.generate_stream(user_prompt):
                yield chunk

        except SparkAPIError:
            logger.exception(f"[VideoAgent] 大模型错误")
            yield f"\n\n[生成中断: 大模型调用失败]"
        except Exception as e:
            logger.exception(f"[VideoAgent] 生成异常")
            yield f"\n\n[生成异常: {e}]"

    async def process(self, topic: str, **kwargs) -> AsyncGenerator[str, None]:
        async for chunk in self.generate_video_recommendations(
            topic,
            kwargs.get("course", ""),
            kwargs.get("student_id", DEFAULT_ANONYMOUS),
            kwargs.get("additional_info", ""),
            kwargs.get("user_demand", ""),
            kwargs.get("temp_file_id"),
            kwargs.get("shared_rag_context", ""),
            kwargs.get("sources"),
            kwargs.get("ui_language", ""),
        ):
            yield chunk


# ======================== 全局实例 ========================

lecture_agent = LectureAgent()
mindmap_agent = MindmapAgent()
exercise_agent = ExerciseAgent()
reading_agent = ReadingAgent()
code_agent = CodeAgent()
video_agent = VideoAgent()
