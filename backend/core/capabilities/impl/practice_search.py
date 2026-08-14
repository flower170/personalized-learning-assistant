"""
练习卡搜索器 — 从官方 OJ 平台找真实练习题

用户选了「深入练习」时触发：按知识点/主题搜索牛客、LeetCode、洛谷、AcWing、PTA
等平台的真实题目，返回结构化练习卡。

核心设计：
- PLATFORM_CONFIG：每个平台的 URL 正则（取 problem_no）+ site 限定查询词 + 官方搜索页模板
- search_problems：DuckDuckGo 按 site 限定查询 → 解析 URL 命中正则的候选 → 去重
- structure_cards：有候选则 LLM 挑题补知识点/难度；不足则用平台 search_url 兜底
- normalize_card：硬性校验链接必须命中平台正则或等于 search_url，防 LLM 编造链接
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

def _ddgs_query(query: str, max_results: int, region: str, backend: str) -> list[dict]:
    """在独立线程里执行 DDG 查询。ddgs.text() 是阻塞调用，且内部自带重试，
    直接 await 会卡死事件循环；放到线程里由外层 asyncio.wait_for 做超时控制。"""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results, region=region, backend=backend))
    except ImportError:
        logger.warning("[PracticeSearch] ddgs 库未安装，请 pip install ddgs")
        return []
    except Exception as e:
        logger.warning(f"[PracticeSearch] DDG 查询失败: {e}")
        return []


# ======================== 平台配置 ========================

PLATFORM_CONFIG: dict[str, dict] = {
    "LeetCode": {
        "url_pattern": re.compile(r"leetcode[^/]*\.(?:com|cn)/problems/([^/?#]+)"),
        "keyword": "leetcode 力扣",  # 宽查询关键词 — site: 限定在 Bing 会超时，改用宽查询+正则过滤
        "search_url": lambda kw: f"https://leetcode.cn/problemset/?search={quote(kw)}",
        "color": "#f59e0b",
    },
    "牛客": {
        "url_pattern": re.compile(r"nowcoder\.com/practice/([\w]+)"),
        "keyword": "nowcoder 牛客",
        "search_url": lambda kw: f"https://www.nowcoder.com/search?query={quote(kw)}",
        "color": "#00a1e9",
    },
    "洛谷": {
        "url_pattern": re.compile(r"luogu\.com\.cn/problem/(P?\d+)"),
        "keyword": "luogu 洛谷",
        "search_url": lambda kw: f"https://www.luogu.com.cn/problem/list?keyword={quote(kw)}",
        "color": "#16a34a",
    },
    "AcWing": {
        "url_pattern": re.compile(r"acwing\.com/problem/content/(\d+)/?"),
        "keyword": "acwing",
        "search_url": lambda kw: f"https://www.acwing.com/problem/search/1/?search_content={quote(kw)}",
        "color": "#6366f1",
    },
    "PTA": {
        "url_pattern": re.compile(r"pintia\.cn/problem-sets/[^/]+/problems/(\d+)"),
        "keyword": "pintia PTA 天梯赛",
        "search_url": lambda kw: f"https://pintia.cn/problem-sets?search={quote(kw)}",
        "color": "#dc2626",
    },
}

# 难度从低到高
DIFFICULTY_LEVELS = ("入门", "简单", "中等", "困难")


def _normalize_difficulty(d: str) -> str:
    """把 LLM/网页给的难度归一化到 DIFFICULTY_LEVELS"""
    if not d:
        return "简单"
    d = str(d).strip().lower()
    mapping = {
        "入门": "入门", "easy": "简单", "简单": "简单", "basic": "入门",
        "简单中等": "中等", "medium": "中等", "中等": "中等",
        "中等困难": "困难", "hard": "困难", "困难": "困难", "进阶": "困难",
    }
    for k, v in mapping.items():
        if k in d:
            return v
    return "简单"


class PracticeCardSearcher:
    """练习卡搜索器 — 确定性 URL 解析 + LLM 结构化"""

    def __init__(self):
        self._llm = None  # 懒加载 llm_service，避免循环导入

    def _get_llm(self):
        if self._llm is None:
            from services.llm import llm_service
            self._llm = llm_service
        return self._llm

    # ---------------- 搜索 ----------------

    async def search_problems(
        self,
        topic: str,
        platforms: Optional[list[str]] = None,
        max_results: int = 8,
        timeout: float = 30.0,
    ) -> list[dict]:
        """搜索官方 OJ 的真实题目链接（尽力而为，可能空）。

        实测结论（国内网络）：
        - site: 限定查询在 Bing/DDG 会长时间挂起（>25s），不可用
        - 「宽查询 + 正则硬过滤」能拿到 leetcode.cn/problems/ 官方链接，但耗时 10~20s 且不稳定
        - 可用后端只有 bing / auto；duckduckgo、google、brave 被墙
        - 返回空是常态 → 调用方必须用平台 search_url 兜底（official search 页永远可点）

        ddgs 的 text() 是阻塞调用，放进独立线程并对单次查询做超时，
        否则多后端 × 多查询循环会把整个 await 卡死（全局 wait_for 形同虚设）。

        :return: [{platform, problem_no, link, title, snippet}, ...]
        """
        import asyncio

        active = platforms or list(PLATFORM_CONFIG.keys())
        all_results: list[dict] = []
        seen_urls: set[str] = set()
        # 实测可用后端：bing / auto
        backends = ["bing", "auto"]
        per_query_timeout = 12.0  # 单次查询上限；bing 偶见 10s+，放 12s 让命中

        async def _do_search():
            for backend in backends:
                for platform in active:
                    cfg = PLATFORM_CONFIG[platform]
                    queries = [
                        f"{topic} {cfg['keyword']}",
                        f"{topic} {cfg['keyword']} 题解",
                    ]
                    for query in queries:
                        try:
                            raw = await asyncio.wait_for(
                                asyncio.to_thread(_ddgs_query, query, 8, "cn-zh", backend),
                                timeout=per_query_timeout,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(f"[PracticeSearch] '{query}' [{backend}] 超时({per_query_timeout}s)")
                            continue
                        except Exception as e:
                            logger.warning(f"[PracticeSearch] '{query}' [{backend}] 失败: {e}")
                            continue

                        for result in raw:
                            url = result.get("href", "") or ""
                            m = cfg["url_pattern"].search(url)
                            if not m:
                                continue
                            problem_no = m.group(1)
                            key = f"{platform}:{problem_no}"
                            if key in seen_urls:
                                continue
                            seen_urls.add(key)
                            all_results.append({
                                "platform": platform,
                                "problem_no": problem_no,
                                "link": url,
                                "title": result.get("title", ""),
                                "snippet": result.get("body", "")[:120],
                            })
                        if len(all_results) >= max_results:
                            return
                    if all_results:
                        break  # 本平台已有命中，不再试后续查询
                if all_results:
                    break  # 某平台命中，不再试后续后端

        try:
            await asyncio.wait_for(_do_search(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"[PracticeSearch] 整体搜索超时({timeout}s)，返回已收集的 {len(all_results)} 条")
        except Exception as e:
            logger.warning(f"[PracticeSearch] 搜索异常: {e}")

        if not all_results:
            logger.warning("[PracticeSearch] 未命中任何平台官方链接，交由调用方兜底")
        all_results.sort(key=lambda r: (active.index(r["platform"]) if r["platform"] in active else 99, 0))
        logger.info(f"[PracticeSearch] '{topic}' → {len(all_results)} 条真实题目链接")
        return all_results[:max_results]

    # ---------------- 结构化 ----------------

    async def structure_cards(
        self,
        candidates: list[dict],
        topic: str,
        knowledge_points: Optional[list[str]] = None,
        count: int = 3,
    ) -> list[dict]:
        """把候选搜索结果结构化为练习卡。

        1) 有候选 → LLM 从中挑 count 道，补 title/knowledge_point/difficulty
        2) 候选不足/为空 → 用平台官方 search_url 兜底生成（链接永远可点）
        3) 每张卡过 normalize_card 硬性校验
        """
        cards: list[dict] = []
        used: list[dict] = list(candidates)

        if used:
            cards = await self._llm_pick_cards(used, topic, knowledge_points, count)
            # LLM 失败则直接用原始候选
            if not cards:
                cards = [
                    {"platform": c["platform"], "problem_no": c["problem_no"],
                     "link": c["link"], "title": c["title"] or f"{topic}练习题",
                     "knowledge_point": (knowledge_points or [""])[0] if knowledge_points else "",
                     "difficulty": "简单"}
                    for c in used[:count]
                ]

        # 数量不足 → search_url 兜底补
        if len(cards) < count:
            fallback = self._fallback_cards(topic, knowledge_points, count - len(cards))
            cards.extend(fallback)

        return [self.normalize_card(c) for c in cards[:count]]

    async def _llm_pick_cards(
        self,
        candidates: list[dict],
        topic: str,
        knowledge_points: Optional[list[str]],
        count: int,
    ) -> list[dict]:
        """让 LLM 从候选中挑最相关的题，补知识点/难度。返回 [{platform, problem_no, link, title, knowledge_point, difficulty}]"""
        try:
            llm = self._get_llm()
            cand_text = "\n".join(
                f"[{i+1}] 平台:{c['platform']} 题号:{c['problem_no']} 链接:{c['link']} 标题:{c.get('title','')} 摘要:{c.get('snippet','')[:80]}"
                for i, c in enumerate(candidates)
            )
            kp_text = "、".join(knowledge_points) if knowledge_points else topic
            system = "你是编程练习题挑选助手。从候选题目中挑选最匹配主题的题目，补全信息。只输出 JSON，不要多余文字。"
            user = (
                f"主题：{topic}\n知识点：{kp_text}\n需要选 {count} 道。\n\n候选题目：\n{cand_text}\n\n"
                f'输出 JSON 数组：[{{"platform":"平台名","problem_no":"题号","link":"原链接","title":"题目名","knowledge_point":"所属知识点","difficulty":"入门|简单|中等|困难"}}]'
            )
            resp = await llm.simple_chat(system, user, model="glm-4.5-flash", temperature=0.2)
            if not resp:
                return []
            import json as _json
            # 提取 JSON 数组
            text = resp.strip()
            if "[" in text and "]" in text:
                text = text[text.index("["): text.rindex("]") + 1]
            data = _json.loads(text)
            if not isinstance(data, list):
                return []
            return [{
                "platform": str(d.get("platform", "")),
                "problem_no": str(d.get("problem_no", "")),
                "link": str(d.get("link", "")),
                "title": str(d.get("title", "")),
                "knowledge_point": str(d.get("knowledge_point", "")),
                "difficulty": _normalize_difficulty(d.get("difficulty", "简单")),
            } for d in data if d.get("platform") and d.get("link")]
        except Exception as e:
            logger.warning(f"[PracticeSearch] LLM 挑题失败: {e}")
            return []

    def _fallback_cards(self, topic: str, knowledge_points: Optional[list[str]], count: int) -> list[dict]:
        """候选不足时的官方搜索页兜底 — 链接永远可点（用户在官方搜索页自己挑题）。
        标题明确标成「搜索「知识点」」，让用户知道点开是平台的搜索页，不是伪装成一道具体题。"""
        cards = []
        platforms = list(PLATFORM_CONFIG.keys())
        kp = (knowledge_points or [topic])[0]
        for i in range(count):
            platform = platforms[i % len(platforms)]
            cfg = PLATFORM_CONFIG[platform]
            cards.append({
                "platform": platform,
                "problem_no": "",
                "link": cfg["search_url"](kp),
                "title": f"搜索「{kp}」",
                "knowledge_point": kp,
                "difficulty": "简单",
                "_fallback": True,
            })
        return cards

    # ---------------- 校验 ----------------

    @staticmethod
    def normalize_card(card: dict) -> dict:
        """保证字段齐全 + card_id；硬性校验 link 必须命中平台正则或等于 search_url 模板。"""
        platform = card.get("platform", "")
        cfg = PLATFORM_CONFIG.get(platform)
        link = str(card.get("link", "")).strip()
        problem_no = str(card.get("problem_no", "")).strip()

        if cfg:
            m = cfg["url_pattern"].search(link)
            if m and not problem_no:
                problem_no = m.group(1)
            # 硬性校验：链接要么命中平台正则，要么是官方搜索页格式，否则换成 search_url
            kw = card.get("knowledge_point") or card.get("title") or "题"
            expected_search_url = cfg["search_url"](kw)
            if not (m or link == expected_search_url):
                link = expected_search_url
                problem_no = ""

        # card_id 稳定标识：platform + problem_no + 标题 slug
        title = str(card.get("title", "")) or f"{platform}练习题"
        import re as _re
        slug = _re.sub(r"[^0-9A-Za-z一-鿿]", "", title)[:12] or "card"
        card_id = f"{platform}_{problem_no or slug}_{slug}".lower()

        now = datetime.now().isoformat(timespec="seconds")
        return {
            "card_id": card_id,
            "node_id": card.get("node_id", ""),
            "platform": platform,
            "problem_no": problem_no,
            "title": title,
            "link": link,
            "knowledge_point": str(card.get("knowledge_point", "")),
            "difficulty": _normalize_difficulty(card.get("difficulty", "简单")),
            "status": card.get("status", "undone"),
            "my_answer": card.get("my_answer", ""),
            "note": card.get("note", ""),
            "search_url": (cfg["search_url"](card.get("knowledge_point") or title) if cfg else ""),
            "created_at": card.get("created_at", now),
            "updated_at": card.get("updated_at", now),
            "solved_at": card.get("solved_at"),
            "_fallback": card.get("_fallback", False),
        }


practice_card_searcher = PracticeCardSearcher()


__all__ = ["PracticeCardSearcher", "practice_card_searcher", "PLATFORM_CONFIG",
           "_normalize_difficulty"]
