import re

file_path = r"c:\Users\班\Desktop\A3_agent\backend\core\capabilities\resource.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 修改 1: RAG 检索
old1 = '''        shared_context, sources = "", []
        try:
            rag_tool = get_tool("rag_retrieve")
            if rag_tool:
                shared_context, sources = await rag_tool(topic, top_k=8, temp_file_id=temp_file_id)
                if sources:
                    yield {"event": "resource_progress",
                           "data": f"✅ 已加载 {len(sources)} 份参考资料"}
        except Exception as e:
            logger.warning(f"[ResourceCapability] RAG 检索跳过: {e}")'''

new1 = '''        shared_context, sources = "", []
        try:
            from core.tools import tool_registry
            _result = await tool_registry.execute("rag_retrieve", query=topic, top_k=8, temp_file_id=temp_file_id)
            # MCP 返回可能是列表或 dict，兼容解析
            if isinstance(_result, (list, tuple)) and len(_result) == 2:
                shared_context, sources = _result
            elif isinstance(_result, dict) and "0" in _result and "1" in _result:
                shared_context, sources = _result["0"], _result["1"]
            else:
                # 默认兜底：字符串文本已返回
                shared_context, sources = str(_result) if _result else "", []
            if sources:
                yield {"event": "resource_progress",
                       "data": f"✅ 已加载 {len(sources)} 份参考资料"}
        except Exception as _e:
            logger.warning(f"[ResourceCapability] RAG 检索跳过: {_e}")'''

if old1 in content:
    content = content.replace(old1, new1)
    print("修改 1 成功：RAG 检索部分")
else:
    print("修改 1 失败：未找到匹配的原代码")

# 修改 2: mermaid_render
old2 = '''            if rtype == "mindmap" and full_content:
                mermaid_tool = get_tool("mermaid_render")
                if mermaid_tool:
                    render_result = await mermaid_tool(full_content, student_id)
                    if render_result.get("image_url"):
                        end_event["image_url"] = render_result["image_url"]
                    if render_result.get("raw_mermaid"):
                        end_event["raw_mermaid"] = render_result["raw_mermaid"]'''

new2 = '''            if rtype == "mindmap" and full_content:
                from core.tools import tool_registry
                render_result = await tool_registry.execute("mermaid_render", text=full_content, student_id=student_id)
                if render_result.get("image_url"):
                    end_event["image_url"] = render_result["image_url"]
                if render_result.get("raw_mermaid"):
                    end_event["raw_mermaid"] = render_result["raw_mermaid"]'''

if old2 in content:
    content = content.replace(old2, new2)
    print("修改 2 成功：mermaid_render 部分")
else:
    print("修改 2 失败：未找到匹配的原代码")

# 修改 3: content_check
old3 = '''            # 安全检查
            safety_tool = get_tool("content_check")
            if safety_tool:
                safety = await safety_tool(full_content)
                end_event["safe"] = safety.get("safe", True)'''

new3 = '''            # 安全检查
            from core.tools import tool_registry
            safety = await tool_registry.execute("content_check", text=full_content)
            end_event["safe"] = safety.get("safe", True)'''

if old3 in content:
    content = content.replace(old3, new3)
    print("修改 3 成功：content_check 部分")
else:
    print("修改 3 失败：未找到匹配的原代码")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("\n文件写入完成！")
