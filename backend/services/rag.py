"""
统一 RAG 服务层 — 自包含实现（不依赖 app/）

唯一后端：讯飞星火知识库（chatdoc.xfyun.cn）+ 本地关键词降级（local_* 文件）
功能：文档上传、语义检索、WebSocket 知识库问答、RAG prompt 组装
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, AsyncGenerator, Optional

import httpx
import websockets

logger = logging.getLogger(__name__)


# ======================== 签名工具 ========================

def split_paragraphs(text: str) -> list[str]:
    """把文档文本切分为段落列表。
    docx 提取的段落用单个 \n 连接，txt 用空行分隔，这里统一按换行切分。
    """
    import re as _re
    paras = [p.strip() for p in _re.split(r"\s*\n\s*", text) if p.strip()]
    return paras


# ======================== 签名工具 ========================

# 常用中文停用词（用于本地关键词检索时的词切分）
_ZH_STOPWORDS = set(
    "的了吗呢吧啊呀哦嗯好吧则是在和有就不没都又或者什么怎么哪些如何请问帮我我想我们你你们他她它"
    "这个那个一个哪些怎样多少什么时候为什么因为所以但是然后还有请回答一下能可以会要"
)

# 查询词同义词扩展：用户口语 → 文档常用词（本地关键词检索用）
_QUERY_SYNONYMS = {
    "习题": "练习", "练习题": "练习", "课后习题": "练习", "课后题": "练习",
    "课后作业": "练习", "作业": "练习", "题目": "练习",
    "章": "章",
    "数组": "列表", "元组": "元组",
    "简介": "介绍",
}


def _expand_query_terms(query: str) -> list[str]:
    """把查询中的口语词扩展为文档常用词，返回额外检索词（无命中关系时返回空）。"""
    import re as _re
    extra: list[str] = []
    for colloquial, doc_term in _QUERY_SYNONYMS.items():
        if colloquial in query:
            # 去掉可能与现有词重复的
            if doc_term and doc_term not in extra:
                extra.append(doc_term)
    return extra


def _tokenize_query(query: str) -> tuple[list[str], list[str]]:
    """切分查询词：返回 (英文词列表, 中文连续字块列表)。
    中文不按空格分词（用户中文输入无空格），改为提取连续汉字串作为检索单元。
    """
    import re as _re
    eng = [w.lower() for w in _re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_.+-]*", query)]
    # 中文字块：连续汉字，去掉停用词字，长度≥2 才保留（单字匹配噪音大）
    zh_chunks = _re.findall(r"[一-鿿]{2,}", query)
    zh = [c for c in zh_chunks if c.lower() not in _ZH_STOPWORDS]
    return eng, zh


# 中文数字 → 阿拉伯数字（章节号识别）
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _parse_chapter_number(query: str) -> int | None:
    """从查询中提取章节号（如 '第一章'/'第1章'/'第一 章'），提取不到返回 None"""
    import re as _re
    m = _re.search(r"第\s*([0-9]+|[一二两三四五六七八九十]+)\s*章", query)
    if not m:
        return None
    raw = m.group(1)
    if raw.isdigit():
        return int(raw)
    # 中文数字（支持 十/十一/二十/二十一）
    if raw in _CN_NUM:
        return _CN_NUM[raw]
    if raw.startswith("十"):
        return 10 + (_CN_NUM.get(raw[1], 0) if len(raw) > 1 else 0)
    if raw.endswith("十"):
        return _CN_NUM.get(raw[0], 0) * 10
    return None


_CHAPTER_INTRO_HINT = ("介绍", "论述", "讲解", "演示", "概述", "讲述", "关于")


def score_paragraphs(query: str, paragraphs: list[str]) -> list[tuple[float, str]]:
    """中英文混合的关键词段落打分，返回 [(score, para)] 降序。

    支持章节感知：查询含「第X章」时，额外识别章节标题/章节内容概述段落并加权，
    优先返回与该章节最相关的内容。
    """
    if not query or not paragraphs:
        return []
    eng, zh = _tokenize_query(query)
    syn_terms = _expand_query_terms(query)
    chapter_num = _parse_chapter_number(query)

    scored: list[tuple[float, str]] = []
    for p in paragraphs:
        pl = p.lower()
        s = 0.0
        matched = 0
        for w in eng:
            if w and w in pl:
                s += 2.0
                matched += 1
        for c in zh:
            if c and c.lower() in pl:
                s += 2.0
                matched += 1
        # 同义词扩展词：命中给予权重（如"课后习题"→"练习"）
        for term in syn_terms:
            if term and term.lower() in pl:
                s += 2.0
                matched += 1

        # 章节感知加权：命中「第X章」标记的段落大幅加权
        if chapter_num is not None:
            chapter_marker = f"第{chapter_num}章"
            if chapter_marker in pl or f"第 {chapter_num} 章" in pl:
                s += 4.0
                matched += 1
                # 内容概述句（"第X章介绍…"）更高
                if any(h in pl for h in _CHAPTER_INTRO_HINT):
                    s += 2.0
            # 习题段落（"练习 X.Y：…"）与章节关联：问"第五章习题"时命中练习 5.x
            import re as _re
            m_ex = _re.match(r"^练习\s*(\d+)", p)
            if m_ex and int(m_ex.group(1)) == chapter_num:
                s += 4.0
                matched += 1

        # 字符级重叠加权（中文长问题且无完整命中的兜底）
        if matched == 0:
            q_chars = set("".join(zh + eng))
            if q_chars:
                p_chars = set(pl.replace(" ", ""))
                overlap = len(q_chars & p_chars) / max(1, len(q_chars))
                if overlap >= 0.4:
                    s = overlap * 1.5
        if s > 0:
            scored.append((s, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ======================== 签名工具 ========================

_KB_APP_ID = ""
_KB_SECRET = ""
_KB_API_URL = "https://chatdoc.xfyun.cn/openapi/v1"
_KB_WS_URL = "wss://chatdoc.xfyun.cn/openapi/chat"


def _configure_kb(app_id: str, secret: str, api_url: str = None, ws_url: str = None):
    """配置知识库鉴权信息（从 settings 调用）"""
    global _KB_APP_ID, _KB_SECRET, _KB_API_URL, _KB_WS_URL
    _KB_APP_ID = app_id
    _KB_SECRET = secret
    if api_url:
        _KB_API_URL = api_url
    if ws_url:
        _KB_WS_URL = ws_url


def _build_signature(app_id: str, secret: str, timestamp: int) -> str:
    md5_input = f"{app_id}{timestamp}"
    auth = hashlib.md5(md5_input.encode("utf-8")).hexdigest()
    digest = hmac.new(
        secret.encode("utf-8"), auth.encode("utf-8"), hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _get_auth_headers() -> dict:
    timestamp = int(time.time())
    signature = _build_signature(_KB_APP_ID, _KB_SECRET, timestamp)
    return {
        "appId": _KB_APP_ID,
        "timestamp": str(timestamp),
        "signature": signature,
    }


# ======================== Spark 知识库客户端 ========================

class SparkKnowledgeBase:
    """星火知识库客户端 — 文档上传、问答、RAG"""

    def __init__(self):
        self.api_base = _KB_API_URL
        self.ws_url = _KB_WS_URL
        self._http_client: Optional[httpx.AsyncClient] = None
        self._upload_client: Optional[httpx.AsyncClient] = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
        return self._http_client

    async def _get_upload_http(self) -> httpx.AsyncClient:
        if self._upload_client is None:
            self._upload_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0, write=120.0))
        return self._upload_client

    # ---- 文档上传 ----

    async def upload_document(self, file_path: str, file_name: Optional[str] = None) -> dict:
        from pathlib import Path
        import re as _re

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_size = path.stat().st_size
        if file_size > 20 * 1024 * 1024:
            raise ValueError(f"文件过大 ({file_size/1024/1024:.1f}MB)，超过 20MB 限制")

        raw_name = file_name or path.name
        safe_name = _re.sub(r'[^\w一-鿿.\-]', '_', raw_name)

        with open(path, "rb") as f:
            head = f.read(32)
            if not head or all(b == 0 for b in head):
                raise ValueError("文件内容为空或已损坏")

        headers = _get_auth_headers()
        headers.pop("Content-Type", None)
        client = await self._get_upload_http()
        url = f"{self.api_base}/file/upload"

        last_err = None
        for attempt in range(2):
            try:
                with open(path, "rb") as f:
                    resp = await client.post(
                        url, headers=headers,
                        data={"fileType": "wiki", "parseType": "AUTO"},
                        files={"file": (safe_name, f, self._guess_mime(safe_name))},
                    )
                ct = resp.headers.get("content-type", "")
                if "application/json" not in ct and "text/json" not in ct:
                    raise ValueError(f"讯飞接口返回异常 (ct={ct})")

                result = resp.json()
                if result.get("code") == 0:
                    return result
                else:
                    code = result.get("code")
                    msg = result.get("message", "")
                    desc = result.get("desc", "")
                    err_map = {
                        66001: "账号余量不足，扣量失败（需在讯飞开放平台购买/续费知识库服务量）",
                        10001: "认证失败，APP_ID或密钥错误",
                        60001: "文件类型不对",
                        60002: "文件大小超限（超过20MB）",
                        60011: "文件字数超限（超过100W字符）",
                    }
                    hint = err_map.get(code, "")
                    detail = desc or msg
                    last_err = f"讯飞错误[{code}]: {detail}{' — ' + hint if hint else ''}"
                    if attempt == 0:
                        await asyncio.sleep(1)
                        continue
                    raise ValueError(last_err)
            except httpx.TimeoutException:
                last_err = "讯飞知识库上传超时"
                if attempt == 0:
                    continue
                raise TimeoutError(last_err)
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                last_err = f"上传HTTP异常: {str(e)[:100]}"
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise ConnectionError(last_err)

        raise ConnectionError(last_err or "上传失败")

    @staticmethod
    def _guess_mime(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "md": "text/markdown",
            "txt": "text/plain",
        }.get(ext, "application/octet-stream")

    # ---- WebSocket 问答 ----

    async def chat_stream(self, question: str, file_id: str,
                          history: Optional[list[dict]] = None) -> AsyncGenerator[str, None]:
        timestamp = int(time.time())
        signature = _build_signature(_KB_APP_ID, _KB_SECRET, timestamp)
        ws_url = (f"{self.ws_url}?appId={_KB_APP_ID}&timestamp={timestamp}&signature={signature}")

        messages = [{"role": "user", "content": question}]
        if history:
            messages = history + messages

        payload = {
            "fileIds": [file_id],
            "messages": messages,
            "chatExtends": {
                "sparkWhenWithoutEmbedding": True,
                "wikiFilterScore": 0,
            },
        }

        try:
            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                await ws.send(json.dumps(payload, ensure_ascii=False))
                while True:
                    response = await ws.recv()
                    data = json.loads(response)
                    code = data.get("code", 0)
                    if code != 0:
                        yield f"\n\n[知识库错误: {data.get('message', '')}]"
                        break
                    # 响应结构: {"code":0, "data":{"content":"...","status":0|1|2}, "message":"success"}
                    payload_data = data.get("data") or {}
                    content = payload_data.get("content", "") or ""
                    if content:
                        yield content
                    if payload_data.get("status", 0) == 2:
                        break
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"知识库WebSocket异常: {e}")
            yield f"\n\n[知识库连接失败: {e}]"

    async def chat(self, question: str, file_id: str,
                   history: Optional[list[dict]] = None) -> str:
        parts = []
        async for chunk in self.chat_stream(question, file_id, history):
            parts.append(chunk)
        return "".join(parts)

    # ---- 语义检索 ----

    async def search(self, query: str, file_id: Optional[str] = None,
                     top_k: int = 5, min_score: float = 0.0) -> list[dict]:
        if not file_id:
            return []

        if file_id.startswith("local_"):
            return self._search_local(file_id, query, top_k)

        # 使用 chat_stream 获取知识库相关回答，并拆分成段落返回
        answer = await self.chat(query, file_id)
        if answer and not answer.startswith("[知识库错误:"):
            # 按段落拆分，模拟多条检索结果
            paragraphs = [p.strip() for p in answer.replace("\n\n", "\n").split("\n") if p.strip() and len(p.strip()) > 15]
            if not paragraphs:
                return [{"content": answer, "score": 0.9, "source": file_id}]
            results = []
            for i, para in enumerate(paragraphs[:top_k]):
                score = 0.9 * (1.0 - i * 0.15)  # 递减分值
                results.append({"content": para, "score": max(0.1, score),
                                "source": file_id})
            return results
        return []

    @staticmethod
    def _search_local(file_id: str, query: str, top_k: int = 5) -> list[dict]:
        from pathlib import Path
        upload_dir = Path(__file__).parent.parent / "static" / "uploads"
        txt_path = upload_dir / f"{file_id}.txt"
        if not txt_path.exists():
            return []

        try:
            text = txt_path.read_text(encoding="utf-8")
            paragraphs = split_paragraphs(text)
            scored = score_paragraphs(query, paragraphs)
            top = scored[:top_k]
            if top:
                return [{"content": p, "score": s, "source": file_id,
                         "source_label": "上传文档"} for s, p in top]
            return [{"content": p, "score": 0.1, "source": file_id,
                     "source_label": "上传文档"} for p in paragraphs[:3]]
        except Exception as e:
            logger.warning(f"本地检索失败: {e}")
            return []

    async def rag_retrieve(self, query: str, file_id: Optional[str] = None,
                           top_k: int = 5, temp_file_id: Optional[str] = None) -> tuple[str, list[dict]]:
        # 合并所有可用 file_id，只调用一次 WebSocket（减少连接数）
        all_ids: list[str] = []
        local_ids: list[str] = []

        for fid in (file_id, temp_file_id):
            if not fid:
                continue
            if fid.startswith("local_"):
                local_ids.append(fid)
            else:
                all_ids.append(fid)

        all_results: list[dict] = []

        # 1) 本地文件检索（关键词匹配，不涉及网络调用）
        for lid in local_ids:
            local_results = self._search_local(lid, query, top_k)
            for r in local_results:
                r["source_type"] = "user_upload"
                r["source_label"] = "用户上传文档"
            all_results.extend(local_results)

        # 2) 星火知识库检索（一次 WebSocket，传入所有 fileId）
        if all_ids:
            try:
                answer = await self.chat(query, all_ids[0])
                if answer and not answer.startswith("[知识库错误:"):
                    paragraphs = [p.strip() for p in answer.replace("\n\n", "\n").split("\n") if p.strip() and len(p.strip()) > 15]
                    for i, para in enumerate(paragraphs[:top_k]):
                        score = 0.9 * (1.0 - i * 0.15)
                        all_results.append({
                            "content": para,
                            "score": max(0.1, score),
                            "source": ",".join(all_ids),
                            "source_type": "system_kb",
                            "source_label": "星火知识库",
                        })
            except Exception as e:
                logger.warning(f"星火知识库检索跳过: {e}")

        if not all_results:
            return "", []

        context_parts = []
        for i, doc in enumerate(all_results, 1):
            context_parts.append(f"[参考资料 {i} - {doc.get('source_label', '')}]\n{doc['content']}\n")
        context = "\n---\n".join(context_parts)
        return context, all_results

    @staticmethod
    def build_rag_prompt(query: str, context: str) -> str:
        if not context:
            return query
        return (f"请基于以下参考资料回答问题。\n\n参考资料：\n{context}\n\n"
                "要求：\n1. 优先基于参考资料回答\n2. 引用时标注 [参考资料 X]\n3. 资料不足时如实说明\n\n"
                f"问题：{query}\n\n回答：")

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._upload_client:
            await self._upload_client.aclose()
            self._upload_client = None


# ======================== 全局实例 ========================

kb_client = SparkKnowledgeBase()

# 从配置加载鉴权信息
try:
    from core.config import settings
    _configure_kb(
        app_id=settings.KB_APP_ID,
        secret=settings.KB_SECRET,
        api_url=settings.KB_API_URL,
        ws_url=settings.KB_WS_URL,
    )
    kb_client.api_base = settings.KB_API_URL
    kb_client.ws_url = settings.KB_WS_URL
except Exception as e:
    logger.warning(f"[RAG] 知识库配置加载失败: {e}")


# ======================== 统一 RAG 服务 ========================

class RAGService:
    """统一 RAG 检索服务 — 多后端支持"""

    def __init__(self, backend: str = "spark"):
        if backend != "spark":
            logger.warning(f"[RAGService] backend={backend} 已移除，强制使用 spark 后端")
            backend = "spark"
        self._backend = backend
        logger.info(f"[RAGService] 初始化，后端: {backend}（讯飞星火知识库 + 本地关键词降级）")

    @property
    def backend(self) -> str:
        return self._backend

    # ---- 语义检索 ----

    async def search(self, query: str, file_id: Optional[str] = None,
                     top_k: int = 5) -> list[dict]:
        return await kb_client.search(query, file_id, top_k)

    async def rag_retrieve(self, query: str, file_id: Optional[str] = None,
                           top_k: int = 5, temp_file_id: Optional[str] = None) -> tuple[str, list[dict]]:
        return await kb_client.rag_retrieve(query, file_id, top_k, temp_file_id)

    async def upload_document(self, file_path: str, file_name: Optional[str] = None) -> dict:
        return await kb_client.upload_document(file_path, file_name)

    def build_rag_prompt(self, query: str, context: str) -> str:
        return kb_client.build_rag_prompt(query, context)

    # ---- 健康检查 ----

    async def health_check(self) -> dict:
        status = {"backend": "spark（讯飞知识库 + 本地关键词降级）", "available": True}
        try:
            await kb_client._get_http()
            status["spark_kb"] = "connected"
        except Exception as e:
            status["spark_kb"] = f"error: {str(e)[:80]}"
            status["available"] = False
        status["local_keyword_fallback"] = "enabled"
        return status


rag_service = RAGService(backend="spark")


__all__ = [
    "RAGService", "rag_service",
    "SparkKnowledgeBase", "kb_client",
    "_configure_kb",
]
