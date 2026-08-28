"""
视频封面获取工具
支持 Bilibili / YouTube 等平台的封面提取
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Bilibili BV 号正则: BV 后跟 10 位字母数字
BILIBILI_BV_RE = re.compile(r'(?:bilibili\.com/video/)?BV([A-Za-z0-9]{10})')
BILIBILI_AV_RE = re.compile(r'(?:bilibili\.com/video/)?[Aa][Vv](\d+)')

# YouTube 视频 ID 正则
YOUTUBE_RE = re.compile(
    r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})'
)

# Bilibili API
BILIBILI_VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
BILIBILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}
# 搜索接口需要 buvid 指纹 cookie,否则返回 HTML 反爬页面(实测)
BILIBILI_BUVID_COOKIE = (
    "buvid3=1E5D9F9E-8B3C-4C4D-9B1E-7C8D9E0F1A2Binfoc; "
    "buvid4=1E5D9F9E-8B3C-4C4D-9B1E-7C8D9E0F1A2B1-0200000000000000000000000000"
)


async def search_bilibili_videos(
    keyword: str, page: int = 1, max_results: int = 20
) -> list[dict]:
    """直接调用 Bilibili 搜索 API 检索视频(按播放量降序)。

    返回每条:
    {bvid, title(去 <em> 高亮标签), url, cover(高清), duration, play, like, author}
    失败/异常 → 返回 [] 并打日志,不抛出。
    """
    if not keyword or not keyword.strip():
        return []
    headers = dict(BILIBILI_HEADERS)
    headers["Cookie"] = BILIBILI_BUVID_COOKIE
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(
                BILIBILI_SEARCH_API,
                params={"search_type": "video", "keyword": keyword.strip(), "page": page},
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(f"[B站搜索] HTTP {resp.status_code}")
                return []
            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"[B站搜索] API 错误: {data.get('message')}")
                return []
            results = []
            for item in (data.get("data", {}).get("result", []) or []):
                bvid = item.get("bvid", "")
                if not bvid:
                    continue
                title = item.get("title", "")
                # 去掉 B站返回的 <em class="keyword"> 高亮标签
                title = title.replace('<em class="keyword">', "").replace("</em>", "")
                pic = item.get("pic", "")
                results.append({
                    "bvid": bvid,
                    "title": title,
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "cover": f"{pic}@672w_378h_1c" if pic else "",
                    "duration": item.get("duration", ""),
                    "play": item.get("play", 0),
                    "like": item.get("like", 0),
                    "author": item.get("author", ""),
                })
            # 按播放量降序(播放量相同再按点赞)
            results.sort(key=lambda v: (v.get("play", 0), v.get("like", 0)), reverse=True)
            return results[:max_results]
    except httpx.TimeoutException:
        logger.warning(f"[B站搜索] 超时: {keyword[:30]}")
        return []
    except Exception as e:
        logger.warning(f"[B站搜索] 失败: {e}")
        return []


async def extract_bilibili_bvid(url: str) -> Optional[str]:
    """从 Bilibili URL 提取 BV 号"""
    m = BILIBILI_BV_RE.search(url)
    if m:
        return f"BV{m.group(1)}"
    return None


async def extract_bilibili_aid(url: str) -> Optional[int]:
    """从 Bilibili URL 提取 AV 号"""
    m = BILIBILI_AV_RE.search(url)
    if m:
        return int(m.group(1))
    return None


async def fetch_bilibili_cover(url_or_bvid: str) -> Optional[str]:
    """
    通过 Bilibili API 获取视频封面

    参数:
        url_or_bvid: Bilibili 视频链接 或 BV 号

    返回:
        封面图片 URL，失败返回 None
    """
    try:
        # 提取 BV 号
        bvid = await extract_bilibili_bvid(url_or_bvid)
        if not bvid:
            return None

        # 调用 Bilibili 公开 API
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(
                BILIBILI_VIDEO_INFO_API,
                params={"bvid": bvid},
                headers=BILIBILI_HEADERS,
            )
            if resp.status_code != 200:
                logger.warning(f"[封面] Bilibili API 返回 {resp.status_code}")
                return None

            data = resp.json()
            if data.get("code") != 0:
                logger.warning(f"[封面] Bilibili API 错误: {data.get('message')}")
                return None

            pic_url = data.get("data", {}).get("pic", "")
            if pic_url:
                # 使用高清封面 (@672w_378h_1c)
                return pic_url + "@672w_378h_1c"
            return None

    except httpx.TimeoutException:
        logger.warning(f"[封面] Bilibili API 超时: {url_or_bvid[:50]}")
        return None
    except Exception as e:
        logger.warning(f"[封面] 获取失败: {e}")
        return None


async def fetch_youtube_cover(url: str) -> Optional[str]:
    """获取 YouTube 视频封面"""
    m = YOUTUBE_RE.search(url)
    if not m:
        return None
    video_id = m.group(1)
    # YouTube 封面有多种分辨率，maxresdefault 最高清
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"


async def fetch_video_cover(url: str) -> Optional[str]:
    """
    根据视频 URL 获取封面（自动识别平台）

    返回:
        封面图片 URL，失败返回 None
    """
    url_lower = url.lower()
    if "bilibili.com" in url_lower or url_lower.startswith("bv"):
        return await fetch_bilibili_cover(url)
    elif any(d in url_lower for d in ["youtube.com", "youtu.be"]):
        return await fetch_youtube_cover(url)
    return None


async def fetch_all_covers(urls: list[str]) -> dict[str, str]:
    """
    批量获取视频封面

    参数:
        urls: 视频 URL 列表

    返回:
        {url: cover_url} 映射
    """
    import asyncio

    results = {}
    if not urls:
        return results

    async def _fetch_one(url: str):
        cover = await fetch_video_cover(url)
        if cover:
            results[url] = cover

    tasks = [_fetch_one(url) for url in urls[:10]]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"[封面] 批量获取 {len(urls)} 个链接 → {len(results)} 个封面")
    return results


def extract_video_urls_from_text(text: str) -> list[str]:
    """从文本中提取所有视频链接"""
    urls = []
    # Markdown 链接: [text](url)
    md_links = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', text)
    urls.extend(url for _, url in md_links)

    # 纯 URL
    raw_urls = re.findall(r'(https?://[^\s\n]+)', text)
    urls.extend(raw_urls)

    # 去重
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique
