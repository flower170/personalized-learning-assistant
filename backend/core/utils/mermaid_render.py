"""
Mermaid 思维导图本地渲染工具
适配 Windows mmdc 11.x，使用 PUPPETEER_EXECUTABLE_PATH 环境变量指定浏览器

用法：
  1. 安装: npm install -g @mermaid-js/mermaid-cli
  2. 校验: mmdc --version
  3. 确保 Edge 或 Chrome 已安装
"""
import asyncio
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ===== 目录 =====
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
MINDMAP_DIR = STATIC_DIR / "mindmap"
try:
    MINDMAP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"[MermaidRender] 目录: {MINDMAP_DIR}")
except Exception as e:
    logger.error(f"[MermaidRender] 目录创建失败: {e}")

# ===== mmdc 路径探测 =====
MMDC_PATH = shutil.which("mmdc")
if not MMDC_PATH:
    for p in [
        Path(os.environ.get("APPDATA", "").replace("Roaming", "") + "npm"),
        Path(os.environ.get("LOCALAPPDATA", "") + "\\npm"),
        Path.home() / "AppData/Roaming/npm",
        Path.home() / "AppData/Local/npm",
    ]:
        for name in ("mmdc.cmd", "mmdc"):
            if (p / name).exists():
                MMDC_PATH = str(p / name)
                break
        if MMDC_PATH:
            break

_MMDC_RUNNER = None
if MMDC_PATH:
    _cli_js = Path(MMDC_PATH).parent / "node_modules" / "@mermaid-js" / "mermaid-cli" / "src" / "cli.js"
    if _cli_js.exists():
        _MMDC_RUNNER = ["node", str(_cli_js)]
        logger.info(f"[MermaidRender] mmdc: {_cli_js}")
    else:
        _MMDC_RUNNER = [str(MMDC_PATH)]
        logger.warning(f"[MermaidRender] mmdc CMD 回退: {MMDC_PATH}")
else:
    logger.warning("[MermaidRender] mmdc 未安装, PNG 不可用")

# ===== Edge/Chrome 路径探测（用于 PUPPETEER_EXECUTABLE_PATH）=====
_EDGE_CANDIDATES = [
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    os.path.expandvars("%LOCALAPPDATA%/Microsoft/Edge/Application/msedge.exe"),
    # Chrome
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
]
BROWSER_PATH = None
# 先找 Edge/Chrome 系统安装
for p in _EDGE_CANDIDATES:
    if Path(p).exists():
        BROWSER_PATH = p
        break
# 没找到则找 puppeteer 内置 Chromium
if not BROWSER_PATH:
    for chrome_dir in Path.home().joinpath(".cache/puppeteer").glob("chrome/win64-*/chrome-win64/chrome.exe"):
        BROWSER_PATH = str(chrome_dir)
        break
if BROWSER_PATH:
    logger.info(f"[MermaidRender] 浏览器: {BROWSER_PATH}")
else:
    logger.info("[MermaidRender] 未找到 Edge/Chrome，使用 puppeteer 内置")


def extract_mermaid_code(text: str) -> Optional[str]:
    """提取 mermaid mindmap 代码"""
    pattern = r"```mermaid\s*\n?(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    for code in matches:
        code = code.strip()
        if code.startswith("mindmap") or "mindmap" in code[:80]:
            return code
    lines = text.split("\n")
    in_mindmap = False
    buf = []
    for line in lines:
        if line.strip().startswith("mindmap"):
            in_mindmap = True
        if in_mindmap:
            buf.append(line)
            if len(buf) > 2 and line.strip() and not line.startswith((" ", "\t", "mindmap")):
                break
    return "\n".join(buf) if len(buf) >= 3 else None


async def render_mermaid_to_png(
    mermaid_code: str,
    student_id: str = "anonymous",
) -> tuple[Optional[str], Optional[str]]:
    """
    渲染 Mermaid → PNG

    :return: (前端URL, 本地路径) — 例如 ("/static/mindmap/stu_001_uuid.png", "C:/.../...png")
             渲染失败返回 (None, None)
    """
    if not _MMDC_RUNNER:
        logger.warning("[MermaidRender] mmdc 不可用，跳过渲染")
        return None, None
    if not mermaid_code:
        logger.warning("[MermaidRender] 空代码，跳过")
        return None, None

    uid = uuid.uuid4().hex[:8]
    stem = f"{student_id}_{uid}"
    mmd_path = MINDMAP_DIR / f"{stem}.mmd"
    png_path = MINDMAP_DIR / f"{stem}.png"

    try:
        mmd_path.write_text(mermaid_code, encoding="utf-8")
    except Exception as e:
        logger.error(f"[MermaidRender] .mmd 写入失败: {e}")
        return None, None

    # 构建 mmdc 命令（通过环境变量指定浏览器，不生成临时配置文件）
    cmd = _MMDC_RUNNER + [
        "-i", str(mmd_path),
        "-o", str(png_path),
        "-w", "1200", "-H", "800", "-b", "white",
        "-q",  # quiet 模式减少日志
    ]

    env = os.environ.copy()
    if BROWSER_PATH:
        env["PUPPETEER_EXECUTABLE_PATH"] = BROWSER_PATH

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")[:200]
            logger.warning(f"[MermaidRender] 渲染失败(code={proc.returncode}): {err_msg}")
            return None, None

        await asyncio.sleep(0.3)  # 等待文件系统同步

        if png_path.exists() and png_path.stat().st_size > 50:
            url = f"/static/mindmap/{stem}.png"
            logger.info(f"[MermaidRender] 成功: {png_path} ({png_path.stat().st_size} bytes)")
            return url, str(png_path)
        else:
            logger.warning(f"[MermaidRender] PNG 未生成或太小: {png_path}")
            return None, None

    except asyncio.TimeoutError:
        logger.warning("[MermaidRender] 超时")
        return None, None
    except FileNotFoundError:
        logger.error("[MermaidRender] node 未找到")
        return None, None
    except Exception as e:
        logger.exception(f"[MermaidRender] 异常: {e}")
        return None, None
    finally:
        try:
            if mmd_path.exists():
                mmd_path.unlink()
        except Exception:
            pass


async def render_mermaid_from_text(
    text: str,
    student_id: str = "anonymous",
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从文本中提取 Mermaid 代码并渲染

    :return: (前端URL, 本地路径, 原始Mermaid代码)
             渲染失败 URL 和 local_path 为 None，但 raw_code 始终有值
    """
    mermaid_code = extract_mermaid_code(text)
    if not mermaid_code:
        return None, None, None
    url, local_path = await render_mermaid_to_png(mermaid_code, student_id)
    return url, local_path, mermaid_code
