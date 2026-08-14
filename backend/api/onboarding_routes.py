"""
新手引导 API 路由

- GET  /api/onboarding/{student_id}   引导状态（画像/路径 完成度 + current_step + all_done）
- POST /api/onboarding/skip           标记某步跳过（profile/path）
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models.onboarding_data import set_skip, get_onboarding_status

router = APIRouter(prefix="/api", tags=["onboarding"])


@router.get("/onboarding/{student_id}")
async def onboarding_status(student_id: str):
    """引导状态：画像/路径完成度、当前步骤、是否全部完成"""
    return get_onboarding_status(student_id)


class OnboardingSkipRequest(BaseModel):
    student_id: str
    step: str   # 'profile' | 'path'


@router.post("/onboarding/skip")
async def onboarding_skip(req: OnboardingSkipRequest):
    """标记某步跳过 → 引导推进到下一步。step 非法返回 400。"""
    if req.step not in ("profile", "path"):
        raise HTTPException(status_code=400, detail="step 必须是 profile 或 path")
    set_skip(req.student_id, req.step)
    return get_onboarding_status(req.student_id)


__all__ = ["router"]
