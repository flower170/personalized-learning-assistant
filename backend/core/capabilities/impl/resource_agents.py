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

LECTURE_SYSTEM_PROMPT = """你是一个专业的课程讲解讲师。请生成**结构清晰、排版舒适**的教学文档。

## 📐 输出格式规范（必须严格遵守）

### 1. 标题层级
- 一级标题：`# ` 开头，仅用于文档总标题，全文只出现一次
- 二级标题：`## ` 开头，用于主要章节（一、二、三、四）
- 三级标题：`### ` 开头，用于子章节（1.1、1.2、2.1）

> ⚠️ 标题中的 `#` 和文字之间必须有空格

### 2. 必须包含的章节

## 一、概念解释
用通俗语言解释核心概念，重要术语用 **加粗** 强调

### 1.1 定义
核心定义说明

### 1.2 核心要素
分点列出关键要素

---

## 二、原理分析
拆解核心原理，分步骤讲解，技术术语用 `反引号` 标注

---

## 三、示例说明
提供完整的实操示例，代码块**必须标注语言**

### 3.1 基础示例
```python
# 完整代码，必须标注语言
```

> 💡 **提示**：补充说明

---

## 四、小结

### 4.1 知识要点回顾
- 要点1
- 要点2

### 4.2 延伸学习方向
- 方向1
- 方向2

### 3. 排版规范
- **加粗**：重要概念、关键术语、核心结论
- `反引号`：技术术语、函数名、变量名、文件名
- `> 💡 提示`：补充说明或小技巧
- `> ⚠️ 注意`：重要提醒或易错点
- `> 📌 说明`：额外说明
- `---`：主要章节之间的分隔线
- 每个段落之间空一行

### 4. 代码块规范
- **必须**标注语言：```python、```java、```bash
- 核心逻辑添加中文注释
- 代码块前后各空一行

### 5. 禁止事项
- ❌ 不要重复一级标题
- ❌ 不要出现 `###1.1` 这种格式（必须加空格）
- ❌ 不要用纯文本罗列代替列表
- ❌ 不要让代码块缺少语言标注

## 📋 格式示例

# Python 装饰器

> 📖 本节学习 Python 装饰器的原理和使用方法。

---

## 一、概念解释

### 1.1 什么是装饰器

装饰器是 Python 中用于**动态增强函数功能**的一种语法结构。它本质上是一个**高阶函数**，接收一个函数作为参数，返回一个新的函数。

---

## 二、原理分析

### 2.1 闭包基础

装饰器依赖于 Python 的**闭包**特性。闭包是指一个函数记住了其外部作用域的变量。

```python
def outer(x):
    def inner(y):
        return x + y
    return inner
```

---

## 三、示例说明

### 3.1 基础装饰器

```python
def timer(func):
    def wrapper(*args, **kwargs):
        import time
        start = time.time()
        result = func(*args, **kwargs)
        print(f"耗时: {time.time()-start:.3f}s")
        return result
    return wrapper
```

> 💡 `@timer` 等价于 `func = timer(func)`

---

## 四、小结

### 4.1 知识要点回顾
- 装饰器是**高阶函数**的应用
- `@` 语法糖简化了装饰器的使用

### 4.2 延伸学习方向
- 学习 `functools.wraps` 保留原函数元数据
- 学习带参数的装饰器
"""


class LectureAgent(BaseAgent):
    fallback_model = "glm-4.5-flash"
    """
    课程讲解文档 Agent
    模型: spark-4.0-ultra（旗舰模型，适合生成大型教学文档）
    """
    def __init__(self):
        super().__init__(
            name="LectureAgent",
            model_name="glm-4.7-flash",
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

MINDMAP_SYSTEM_PROMPT = """你是一个知识结构化专家。请将知识点组织为层级化的思维导图结构。

输出必须严格遵循以下两种格式之一（二选一）：

格式一 — Mermaid.js（优先，可自动渲染为图形）：
```mermaid
mindmap
  root((中心主题))
    一级分支1
      二级节点1.1
        三级节点1.1.1
      二级节点1.2
    一级分支2
      二级节点2.1
```

格式二 — Markdown 层级列表（备选）：
```markdown
# 中心主题
## 一级分支 1
- 二级节点 1.1
...
```

要求：
1. 层次深度至少3层，展现知识体系结构
2. 每个节点名称简洁明了（不超过15字）
3. 包含知识点之间的关联关系标注
4. 重要/核心概念可以突出标记
5. 优先输出完整的 ```mermaid mindmap 代码块，方便直接渲染为图形
"""


class MindmapAgent(BaseAgent):
    fallback_model = "glm-4.5-flash"
    """
    知识点思维导图 Agent
    模型: spark-4.0-ultra（稳定结构化输出）
    """
    def __init__(self):
        super().__init__(
            name="MindmapAgent",
            model_name="glm-4.7-flash",
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
            prompt_parts = [f"请为「{topic}」生成知识点思维导图，优先输出 Mermaid 格式。", f"语言要求：{lang_hint}"]

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
    fallback_model = "glm-4.5-flash"
    """
    练习题目 Agent
    模型: spark-4.0-ultra（检测到数学主题时降低温度保证推导准确性）
    """
    def __init__(self):
        super().__init__(
            name="ExerciseAgent",
            model_name="glm-4.7-flash",
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
    fallback_model = "glm-4.5-flash"
    """
    拓展阅读材料 Agent
    模型: spark-4.0-ultra（长上下文，适合生成长篇阅读材料）
    """
    def __init__(self):
        super().__init__(
            name="ReadingAgent",
            model_name="glm-4.7-flash",
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
    fallback_model = "glm-4.5-flash"
    """
    代码实操案例 Agent
    模型: spark-4.0-ultra（代码生成能力强）
    """
    def __init__(self):
        super().__init__(
            name="CodeAgent",
            model_name="glm-4.7-flash",
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
    fallback_model = "glm-4.5-flash"
    """
    视频推荐 Agent
    使用 DuckDuckGo 视频搜索 + LLM 智能推荐
    模型: spark-4.0-ultra
    """

    def __init__(self):
        super().__init__(
            name="VideoAgent",
            model_name="glm-4.7-flash",
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
