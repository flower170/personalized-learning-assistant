# -*- coding: utf-8 -*-
"""调试3：用真实 Redis 会话历史跑抽取，看 knowledge_base 解析结果"""
import asyncio
import io
import json
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
import redis as _redis
from core.models.profile import PROFILE_EXTRACTION_SYSTEM_PROMPT

STUDENT = "ftty_clean_03"
SESSION = "b445ad54e7f7"


def load_env(p=".env"):
    env = {}
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def build_conv(chat_history):
    lines = []
    for i, m in enumerate(chat_history, 1):
        role = m.get("role", "user") if isinstance(m, dict) else "user"
        content = m.get("content", "") if isinstance(m, dict) else str(m)
        prefix = "学生" if role == "user" else "助手"
        lines.append(f"turn {i}: {prefix}: {content}")
    return "\n".join(lines)


async def main():
    r = _redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True, protocol=2)
    key = f"profile_chat:{STUDENT}:{SESSION}"
    chat_history = json.loads(r.hget(key, "chat_history") or "[]")
    base_info = json.loads(r.hget(key, "base_info") or "{}")
    print(f"chat_history 长度: {len(chat_history)}")
    print(f"base_info: {base_info}")
    print(f"cv: {r.hget(key, 'consecutive_valid_replies')}")

    conv_text = build_conv(chat_history)
    prompt = (
        f"{PROFILE_EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"[上一版画像（旧画像）]\n{{}}\n\n"
        f"[完整对话记录（turn 从 1 开始编号）]\n{conv_text}\n\n"
        f"[基础信息]\n{json.dumps(base_info, ensure_ascii=False, indent=2)}\n\n"
        f"强制性要求：输出 JSON 的 profile 段必须包含 student_id、name、grade、major 四个字段，从以上[基础信息]获取。"
    )

    key_glm = load_env()["GLM_API_KEY"]
    async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=15)) as c:
        t0 = time.time()
        rr = await c.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            headers={"Authorization": f"Bearer {key_glm}", "Content-Type": "application/json"},
            json={
                "model": "glm-4.5-flash",
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": "请提取画像"}],
                "temperature": 0.1,
                "max_tokens": 8192,
                "stream": False,
            },
        )
        el = time.time() - t0
        content = (rr.json().get("choices", [{}])[0].get("message", {}).get("content", "") or "")
        print(f"耗时 {el:.1f}s, content 长度 {len(content)}")

        # 复刻 _try_extract_json
        from core.capabilities.impl.profile_chat_agent import ProfileChatAgent
        parsed = ProfileChatAgent._try_extract_json(content)
        if parsed:
            profile = parsed.get("profile") or {}
            print("=== profile 段 ===")
            print("  learning_goals:", json.dumps(profile.get("learning_goals"), ensure_ascii=False))
            print("  knowledge_base:", json.dumps(profile.get("knowledge_base"), ensure_ascii=False))
            print("  error_prone:", profile.get("error_prone_areas"))
            print("  interests:", profile.get("interests"))
            print("  daily_hours:", profile.get("daily_available_hours"))
            print("  confidence keys:", list((parsed.get("confidence") or {}).keys()))
        else:
            print("解析失败")


asyncio.run(main())
