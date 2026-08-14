"""
学习路径数据管理层
基于JSON文件持久化，无需数据库
"""
import json
import logging
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "learning_paths"

def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def _path(student_id: str) -> Path:
    return DATA_DIR / f"{student_id}.json"


def load_path(student_id: str) -> Optional[dict]:
    """加载学生学习路径"""
    _ensure_dir()
    p = _path(student_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"加载路径失败 {student_id}: {e}")
    return None


def save_path(student_id: str, data: dict):
    """保存学生学习路径"""
    _ensure_dir()
    data["updated_at"] = datetime.now().isoformat()
    _path(student_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"[LP] 已保存: {student_id} (v{data.get('version',1)})")


def calc_progress(data: dict) -> dict:
    """计算进度统计"""
    total_tasks = 0
    completed_tasks = 0
    for node in data.get("nodes", []):
        for task in node.get("daily_tasks", []):
            total_tasks += 1
            if task.get("completed"):
                completed_tasks += 1

    total_days = data.get("total_duration_days", 1)
    elapsed = (datetime.now() - datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))).days
    elapsed = max(0, elapsed)

    percent = round(completed_tasks / total_tasks * 100) if total_tasks else 0
    expected_pct = min(100, round(elapsed / total_days * 100))
    status = "on_track"
    if percent < expected_pct - 15:
        status = "behind"
    elif percent > expected_pct + 15:
        status = "ahead"

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "progress_percent": percent,
        "elapsed_days": elapsed,
        "total_days": total_days,
        "expected_percent": expected_pct,
        "status": status,
        "remaining_tasks": total_tasks - completed_tasks,
    }


def mark_node_task_done(student_id: str, node_id: str) -> bool:
    """把指定节点第一个未完成的日任务标为已完成（外部学习上报 → 路径进度前移）。
    找不到节点 / 该节点任务已全部完成返回 False。"""
    data = load_path(student_id)
    if not data:
        return False
    for node in data.get("nodes", []):
        if node.get("node_id") != node_id:
            continue
        for task in node.get("daily_tasks", []):
            if not task.get("completed"):
                task["completed"] = True
                task["checkin_date"] = date.today().isoformat()
                save_path(student_id, data)
                return True
    return False


def split_daily_tasks(nodes: list[dict], total_days: int, daily_minutes: int) -> list[dict]:
    """将学习路径步骤自动拆分为每日任务"""
    day_counter = 1
    for node in nodes:
        estimated_days = node.get("estimated_days", 1)
        tasks = []
        for d in range(estimated_days):
            if day_counter > total_days:
                break
            tasks.append({
                "day": day_counter,
                "title": f"{node.get('title','')} - 第{d+1}天" if estimated_days > 1 else node.get("title", ""),
                "description": f"学习时长: {daily_minutes}分钟",
                "completed": False,
                "checkin_date": None,
                "checkin_notes": "",
            })
            day_counter += 1
        node["daily_tasks"] = tasks
    return nodes


def rebuild_daily_tasks(data: dict) -> dict:
    """根据当前进度重建剩余任务"""
    today = datetime.now()
    created = datetime.fromisoformat(data.get("created_at", today.isoformat()))
    elapsed = (today - created).days
    total_days = data.get("total_duration_days", 30)
    daily_minutes = data.get("daily_minutes", 60)
    remaining_days = max(1, total_days - elapsed)

    # 标记已有打卡
    completed_map = {}
    for node in data.get("nodes", []):
        for task in node.get("daily_tasks", []):
            if task.get("completed"):
                completed_map[task["day"]] = task

    new_day = 1
    for node in data.get("nodes", []):
        est = node.get("estimated_days", 1)
        tasks = []
        for d in range(est):
            if new_day > total_days:
                break
            if new_day in completed_map:
                tasks.append(completed_map[new_day])
            elif new_day <= elapsed:
                tasks.append({"day": new_day, "title": f"{node['title']} - 第{d+1}天", "description": f"{daily_minutes}分钟", "completed": False, "checkin_date": None, "checkin_notes": "", "skipped": True})
            else:
                tasks.append({"day": new_day, "title": f"{node['title']} - 第{d+1}天", "description": f"{daily_minutes}分钟", "completed": False, "checkin_date": None, "checkin_notes": ""})
            new_day += 1
        node["daily_tasks"] = tasks

    data["version"] = data.get("version", 1) + 1
    return data
