# -*- coding: utf-8 -*-
content = open('mcp_client.py', 'r', encoding='utf-8').read()

# 1. 添加 _stdio_session_acm 属性
content = content.replace(
    'self._stdio_proc_acm = None  # AsyncContextManager for stdio_client\n        self._tool_to_server',
    'self._stdio_proc_acm = None  # AsyncContextManager for stdio_client\n        self._stdio_session_acm = None  # None 或 session 实例（用于 __aexit__ 退出）\n        self._tool_to_server'
)

# 2. 修改 _start_local_stdio 方法
old_start = '''            read, write = await acm.__aenter__()
            session = ClientSession(read, write)
            await session.initialize()'''
new_start = '''            read, write = await acm.__aenter__()
            session = ClientSession(read, write)
            self._stdio_session_acm = session
            # 进入 session context manager，启动 dispatcher.run
            await session.__aenter__()
            # 现在才能初始化
            await session.initialize()'''
content = content.replace(old_start, new_start)

# 3. 修改 close() 方法
old_close = '''        for sid, session in list(self._server_sessions.items()):
            try:
                await session.close()
            except Exception:
                pass
        self._server_sessions.clear()'''
new_close = '''        for sid, session in list(self._server_sessions.items()):
            try:
                await session.close()
            except Exception:
                pass
            # 如果是本地 stdio session，需要退出其 async context manager（停止 task_group / dispatcher.run）
            if sid == "local" and getattr(self, '_stdio_session_acm', None) is not None:
                try:
                    await self._stdio_session_acm.__aexit__(None, None, None)
                except Exception:
                    pass
                self._stdio_session_acm = None
        self._server_sessions.clear()'''
content = content.replace(old_close, new_close)

open('mcp_client.py', 'w', encoding='utf-8').write(content)
print('修改完成！')
