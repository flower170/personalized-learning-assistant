import re

# 修改 mcp_client.py
with open(r'c:\Users\班\Desktop\A3_agent\backend\core\mcp_client.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # 1. 在 self._initialized = False 之前添加 self._server_cached_tools
    if 'self._initialized = False' in line and '_server_cached_tools' not in ''.join(lines[max(0,i-5):i+1]):
        new_lines.append('        self._server_cached_tools: list = []\n')
        new_lines.append(line)
        i += 1
        continue
    # 2. 在 return result (list_tools 方法中) 之前添加缓存赋值
    if line.strip() == 'return result' and i > 0 and 'list_tools' in ''.join(lines[max(0,i-20):i]):
        if i > 0 and 'self._server_cached_tools = result' not in lines[i-1]:
            new_lines.append('        self._server_cached_tools = result\n')
    new_lines.append(line)
    i += 1

with open(r'c:\Users\班\Desktop\A3_agent\backend\core\mcp_client.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('mcp_client.py 修改完成')
