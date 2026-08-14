"""
防幻觉机制
通过多策略验证确保生成内容的准确性
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class HallucinationGuard:
    """
    幻觉防护层
    组合多种策略检测和降低幻觉风险
    """

    # 需要避免的模糊/不确切表述
    VAGUE_PATTERNS = [
        r"可能[是]?",
        r"应该[是]?",
        r"一般来说",
        r"通常情况下",
        r"据推测",
        r"我[猜觉]得",
        r"maybe",
        r"probably",
        r"不确定",
        r"没有明确信息",
    ]

    # 学术内容中的事实性断言检查模式
    FACTUAL_CLAIM_PATTERNS = [
        r"成立于\d+年",
        r"由(.+?)提出",
        r"首次(.+?)于\d+",
        r"共有\d+[种个类项条]",
        r"(\d+\.?\d*)\s*%",
    ]

    @classmethod
    def check_vague_language(cls, text: str) -> list[dict]:
        """
        检测模糊/不确定表述

        :return: 模糊表述列表 [{"pattern": "...", "position": int}]
        """
        findings = []
        for pattern in cls.VAGUE_PATTERNS:
            for match in re.finditer(pattern, text):
                findings.append({
                    "pattern": pattern,
                    "matched": match.group(),
                    "position": match.start(),
                    "context": text[max(0, match.start() - 20):match.end() + 20],
                })
        return findings

    @classmethod
    def check_citation_quality(cls, text: str, required_refs: list[str] = None) -> dict:
        """
        检查引用质量：生成内容是否引用了提供的参考资料

        :param text: 生成的内容
        :param required_refs: 参考资料列表
        :return: 检查结果
        """
        if not required_refs:
            return {"has_citations": False, "cited_refs": [], "missing_refs": [], "score": 1.0}

        cited = []
        for i, ref in enumerate(required_refs):
            if ref.lower() in text.lower():
                cited.append(ref)

        # 提取引用标记 [1], [2], (来源: xxx) 等
        citation_marks = re.findall(r'\[\d+\]|\(来源[:：][^)]+\)|参考资料\s*\d+', text)

        missing = [r for r in required_refs if r not in cited]
        score = len(cited) / len(required_refs) if required_refs else 1.0

        return {
            "has_citations": len(citation_marks) > 0,
            "citation_marks": citation_marks,
            "cited_refs": cited,
            "missing_refs": missing,
            "score": round(score, 2),
        }

    @classmethod
    def check_knowledge_boundary(cls, text: str, known_topics: list[str]) -> list[dict]:
        """
        检查生成内容是否超出已知知识边界

        :param text: 生成文本
        :param known_topics: 已知的知识主题列表
        :return: 超出边界的内容片段
        """
        # 简化实现：检测内容中是否包含不在已知主题范围内的专业术语
        # 实际场景可使用 NER + 知识图谱匹配
        out_of_bound = []
        # 这里预留接口，后续可接入专业领域知识库做精确校验
        return out_of_bound

    @classmethod
    def verify_academic_content(cls, text: str) -> dict:
        """
        综合验证学术内容的准确性

        :return: 验证报告
        """
        issues = []

        # 1. 检查模糊表述
        vague = cls.check_vague_language(text)
        if vague:
            issues.append({
                "type": "vague_language",
                "severity": "warning",
                "count": len(vague),
                "details": vague[:5],  # 只报告前5个
            })

        # 2. 检查事实性断言
        factual_claims = []
        for pattern in cls.FACTUAL_CLAIM_PATTERNS:
            for match in re.finditer(pattern, text):
                factual_claims.append(match.group())
        if factual_claims:
            issues.append({
                "type": "unverified_factual_claims",
                "severity": "info",
                "claims": factual_claims,
                "note": "以上事实性断言建议通过知识库检索验证",
            })

        # 3. 其他检查项...

        verdict = "pass" if not any(i["severity"] == "error" for i in issues) else "need_review"
        return {
            "verdict": verdict,
            "issues": issues,
            "vague_count": len(vague),
        }


# RAG 增强的防幻觉提示词
ANTI_HALLUCINATION_SYSTEM_PROMPT = """你是一个严谨的教育内容助手。在生成回答时，请严格遵守以下原则：

1. **基于事实**：只陈述你从参考资料中明确获取的信息
2. **注明来源**：引用具体内容时标注对应的参考资料编号
3. **诚实承认未知**：如果参考资料中没有相关信息，明确说"参考资料中未提及"
4. **区分已知与推测**：如果是基于已有知识的合理推论，明确说明"基于已有知识推断"
5. **避免模糊表述**：不使用"可能""大概""也许"等不确定词汇来描述事实性内容
6. **数值精确**：涉及数字、日期、比例等信息时，确保与参考资料一致

如果无法从参考资料中找到确切答案，请说：
「根据现有的参考资料，我无法找到关于这个问题的确切信息。建议查阅更权威的教材或资料。」"""
