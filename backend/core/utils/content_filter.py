"""
内容安全过滤机制
检测并过滤生成内容中的敏感/违规信息
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ContentFilter:
    """
    内容安全过滤器
    包含关键词过滤、敏感内容检测、合规检查
    """

    # 敏感词列表（示例 — 生产环境应从外部词库加载）
    SENSITIVE_KEYWORDS: list[str] = []

    # 需要审核的内容模式
    REVIEW_PATTERNS = [
        # 政治敏感
        r"(?i)政治敏感|违规内容|习近平(?!新时代中国特色社会主义|思想)|江泽民|胡锦涛|温家宝",
        # 暴力
        r"暴力|恐怖袭击|杀人|自杀|毒品",
        # 色情
        r"色情|淫秽|成人内容|裸体",
        # 歧视
        r"种族歧视|性别歧视|地域歧视",
        # 虚假信息
        r"虚假|谣言|不实信息",
    ]

    # 教育内容本身的合规要求
    EDUCATIONAL_REQUIREMENTS = [
        "不得包含任何形式的歧视性内容",
        "学术内容应当基于主流学术观点",
        "涉及争议性话题时应当呈现多方观点",
        "不得鼓励或美化任何违法行为",
        "内容应当符合社会主义核心价值观",
    ]

    def __init__(self):
        self._load_sensitive_words()

    def _load_sensitive_words(self):
        """加载敏感词库（从文件或默认）"""
        # 这里可以从外部文件加载
        # 当前使用内置列表
        pass

    def check_text(self, text: str) -> dict:
        """
        检查文本内容安全性

        :return: 检查结果
        """
        findings = []

        # 1. 检查关键词
        for keyword in self.SENSITIVE_KEYWORDS:
            if keyword.lower() in text.lower():
                findings.append({
                    "type": "sensitive_keyword",
                    "content": keyword,
                    "severity": "block",
                })

        # 2. 检查正则模式
        for pattern in self.REVIEW_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                findings.append({
                    "type": "review_pattern",
                    "pattern": str(pattern),
                    "matches": matches[:3],
                    "severity": "review",
                })

        # 3. 检查 URL（防止外链不良信息）
        urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', text)
        if urls:
            findings.append({
                "type": "external_url",
                "urls": urls,
                "severity": "info",
            })

        verdict = "pass"
        for f in findings:
            if f["severity"] == "block":
                verdict = "blocked"
                break
            elif f["severity"] == "review":
                verdict = "need_review"

        return {
            "verdict": verdict,
            "findings": findings,
            "safe": verdict == "pass",
        }

    def filter_response(self, text: str) -> str:
        """
        过滤并清理响应内容
        对违规内容进行替换或移除

        :return: 过滤后的安全文本
        """
        # 替换敏感词为 ***
        result = text
        for keyword in self.SENSITIVE_KEYWORDS:
            result = result.replace(keyword, "*" * len(keyword))
        return result


# System prompt 安全加固
SAFETY_SYSTEM_PROMPT = """你是一个教育辅导助手，请遵守以下行为准则：

1. **内容合规**：生成的内容必须符合教育行业规范和法律法规
2. **学术严谨**：所有学术内容应当基于主流学术观点和教材
3. **正向引导**：引导学生积极思考，不传播负面信息
4. **隐私保护**：不询问或记录学生个人隐私信息（真实姓名、联系方式等）
5. **版权尊重**：不提供盗版教材、侵权内容
6. **年龄适宜**：内容适合各年龄段学生阅读
7. **争议处理**：涉及学术争议时，客观呈现不同学派的观点

如果用户提出不合理要求（如生成违规内容、代写作业等），请礼貌拒绝并解释原因。"""


# 全局过滤器
content_filter = ContentFilter()
