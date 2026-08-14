# -*- coding: utf-8 -*-
"""调试：抽取任务的 LLM 原始输出 + _try_extract_json 解析结果"""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.models.profile import PROFILE_EXTRACTION_SYSTEM_PROMPT
from core.models.spark_client import SparkAPIClient

CONV = """turn 1: 助手: 你好小明，作为大二计算机专业的学生，你最近的学习目标是什么，以及未来希望在这个专业领域达到什么样的成就呢？
turn 2: 学生: 我的短期目标是学好SQL，长期目标是做数据分析师
turn 3: 助手: 太棒了，明确的数据分析师目标很清晰！那么目前在SQL学习上，你已经掌握了哪些知识点，还有哪些内容正在学习呢？
turn 4: 学生: 我目前刚入门，会基础查询，多表连接和窗口函数不熟
turn 5: 助手: 很好，看来你在SQL基础查询方面已经有了不错的起点！那么除了SQL之外，你还掌握了哪些编程语言或者计算机基础知识呢？
turn 6: 学生: 我每天能投入2小时学习，喜欢看视频教程"""

OLD_PROFILE = "{}"
BASE_INFO = json.dumps({"student_id": "ftty_clean_01", "name": "小明", "grade": "大二", "major": "计算机"}, ensure_ascii=False)


async def main():
    prompt = (
        f"{PROFILE_EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"[上一版画像（旧画像）]\n{OLD_PROFILE}\n\n"
        f"[完整对话记录（turn 从 1 开始编号）]\n{CONV}\n\n"
        f"[基础信息]\n{BASE_INFO}\n\n"
        f"强制性要求：输出 JSON 的 profile 段必须包含 student_id、name、grade、major 四个字段，从以上[基础信息]获取。"
    )
    client = SparkAPIClient.for_model("glm-4.5-flash")
    print(">>> 调用 GLM 抽取...")
    resp = await client.chat(
        [{"role": "system", "content": prompt}, {"role": "user", "content": "请提取画像"}],
        temperature=0.1, max_tokens=4096,
    )
    print(">>> 原始响应（前 2000 字符）:")
    print(resp[:2000])
    print()
    print(">>> 解析结果:")
    # 复刻 _try_extract_json
    from core.capabilities.impl.profile_chat_agent import ProfileChatAgent
    parsed = ProfileChatAgent._try_extract_json(resp)
    if parsed:
        print("  profile:", json.dumps(parsed.get("profile"), ensure_ascii=False)[:800])
        print("  confidence keys:", list((parsed.get("confidence") or {}).keys()))
    else:
        print("  None（解析失败）")


asyncio.run(main())
