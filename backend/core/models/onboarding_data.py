"""
新手引导状态管理层 — 画像 → 学习路径 → 学习资源，每步可跳过

只持久化「跳过」标记（data/user_onboarding/{student_id}.json），
完成态全部派生（画像字段完备度 / 路径文件是否存在），不重复存储，避免两套真相。

文件：data/user_onboarding/{student_id}.json
结构：{"student_id", "skips": {"profile": false, "path": false}, "updated_at"}
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models.profile import profile_manager
from core.models.learning_path_data import load_path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "user_onboarding"

STEPS = ("profile", "path")


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _path(student_id: str) -> Path:
    return DATA_DIR / f"{student_id}.json"


def load_onboarding(student_id: str) -> dict:
    """加载引导状态，无则返回默认（不落盘）"""
    _ensure_dir()
    p = _path(student_id)
    base = {"student_id": student_id, "skips": {}, "updated_at": ""}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            base.update(data)
            base.setdefault("skips", {})
            return base
        except Exception as e:
            logger.error(f"加载引导状态失败 {student_id}: {e}")
    return base


def save_onboarding(student_id: str, data: dict):
    _ensure_dir()
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _path(student_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_skip(student_id: str, step: str) -> dict:
    """标记某步跳过（profile/path）"""
    data = load_onboarding(student_id)
    data.setdefault("skips", {})[step] = True
    save_onboarding(student_id, data)
    return data


def clear_skip(student_id: str, step: str) -> dict:
    """「跳过后又去做」恢复：清除跳过标记"""
    data = load_onboarding(student_id)
    data.setdefault("skips", {}).pop(step, None)
    save_onboarding(student_id, data)
    return data


def is_profile_done(student_id: str) -> bool:
    """鲁棒「画像完成」判定。

    不能只看 completeness.overall —— get_profile 恒返回非 null（默认空画像），
    且历史数据（如 stu_001）字段全填但 completeness 可能为 0.0。
    兜底：已填充关键字段数 >= 3 也算完成。
    """
    profile = profile_manager.get_profile(student_id)
    if not profile:
        return False
    filled = 0
    if profile.name:
        filled += 1
    if profile.grade:
        filled += 1
    if profile.major:
        filled += 1
    if profile.cognitive_style:
        filled += 1
    if profile.preferred_pace:
        filled += 1
    kb = profile.knowledge_base or {}
    if kb.get("mastered") or kb.get("weak") or kb.get("untouched"):
        filled += 1
    if profile.interests:
        filled += 1
    goals = profile.learning_goals or {}
    if goals.get("short_term") or goals.get("long_term") or profile.goal_attribute:
        filled += 1
    if profile.error_prone_areas:
        filled += 1
    if (profile.daily_available_hours or 0) > 0:
        filled += 1
    overall = (profile.completeness or {}).get("overall", 0) or 0
    return overall >= 0.6 or filled >= 3


def is_path_done(student_id: str) -> bool:
    """路径完成 = 已确认路径文件存在"""
    return bool(load_path(student_id))


def get_onboarding_status(student_id: str) -> dict:
    """组装引导状态。

    current_step：第一个「未完成且未跳过」的步骤；全部完成/跳过 → 'done'。
    「资源」步骤不参与状态（= 聊天自由使用，恒可用）。
    """
    skips = load_onboarding(student_id).get("skips", {})
    profile_done = is_profile_done(student_id)
    path_done = is_path_done(student_id)
    profile_skipped = bool(skips.get("profile"))
    path_skipped = bool(skips.get("path"))

    profile_ok = profile_done or profile_skipped
    path_ok = path_done or path_skipped
    if not profile_ok:
        current_step = "profile"
    elif not path_ok:
        current_step = "path"
    else:
        current_step = "done"

    profile = profile_manager.get_profile(student_id)
    completeness = (profile.completeness or {}).get("overall", 0) or 0

    return {
        "ok": True,
        "student_id": student_id,
        "profile": {
            "done": profile_done,
            "skipped": profile_skipped,
            "completeness": round(completeness, 2),
        },
        "path": {
            "done": path_done,
            "skipped": path_skipped,
        },
        "current_step": current_step,
        "all_done": profile_ok and path_ok,
    }


__all__ = [
    "load_onboarding", "save_onboarding", "set_skip", "clear_skip",
    "is_profile_done", "is_path_done", "get_onboarding_status",
]
