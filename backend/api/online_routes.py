"""
联网学习路径 / 练习卡 / 技能差距 API 路由

分组：
- POST /api/online-path/start          三阶段交互 Stage 1（画像起步 + 联网 + 提问）
- POST /api/online-path/answers        三阶段交互 Stage 2（补全信息）
- POST /api/online-path/generate       三阶段交互 Stage 3（出草案）
- POST /api/online-path/confirm        确认 / 带 feedback 修改
- GET  /api/online-path/{student_id}   已确认路径 + 进度
- POST /api/practice/deep-search       用户选「深入练习」时按知识点搜官方 OJ 练习卡
- GET  /api/practice/cards             某节点的练习卡
- POST /api/practice/update            更新练习卡状态/答案/笔记
- POST /api/practice/checkin           打卡
- GET  /api/practice/progress/{student_id}  进度 + 激励数据
- POST /api/skill-gap/analyze          技能差距雷达数据
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from core.models.schemas import (
    WebPathStartRequest, WebPathAnswersRequest, WebPathConfirmRequest,
    PracticeDeepSearchRequest, PracticeCardUpdate, PracticeCheckinRequest,
    SaveAiExercisesRequest, RedoAiExerciseRequest,
    CreateCollectionRequest, AddToCollectionRequest, RedoCollectionQuestionRequest,
    RemoveCollectionQuestionRequest, DeleteCollectionRequest, NodeStudyRequest,
    SkillGapRequest,
)
from core.capabilities.impl.web_path_plan_agent import web_path_plan_agent, WebPathPlanAgent
from core.capabilities.impl.practice_search import practice_card_searcher
from core.models import practice_data
from core.models.learning_path_data import load_path, calc_progress, mark_node_task_done

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["online-path", "practice", "skill-gap"])


# ======================== 交互式联网学习路径 ========================

@router.post("/online-path/start")
async def online_path_start(req: WebPathStartRequest):
    """Stage 1：画像起步 + 联网补充，返回需要补充的问题或直接出草案"""
    try:
        return await web_path_plan_agent.start_conversation(req.student_id, req.topic)
    except Exception as e:
        logger.exception("[online-path] start 失败")
        raise HTTPException(status_code=500, detail=f"路径规划初始化失败: {str(e)[:200]}")


@router.post("/online-path/answers")
async def online_path_answers(req: WebPathAnswersRequest):
    """Stage 2：补全信息，仍缺继续问，够了出草案"""
    try:
        return await web_path_plan_agent.provide_info(
            req.student_id, req.topic, {"collected": req.collected, "answers": req.answers})
    except Exception as e:
        logger.exception("[online-path] answers 失败")
        raise HTTPException(status_code=500, detail=f"信息处理失败: {str(e)[:200]}")


@router.post("/online-path/generate")
async def online_path_generate(req: WebPathStartRequest):
    """Stage 3 入口：已有足够信息，直接出草案"""
    try:
        collected = req.collected or {}
        if not collected.get("daily_hours"):
            collected["daily_hours"] = req.daily_hours
        if not collected.get("cycle"):
            collected["cycle"] = req.cycle
        if not collected.get("target"):
            collected["target"] = req.target
        return await web_path_plan_agent.generate_draft(req.student_id, req.topic, collected)
    except Exception as e:
        logger.exception("[online-path] generate 失败")
        raise HTTPException(status_code=500, detail=f"草案生成失败: {str(e)[:200]}")


@router.post("/online-path/confirm")
async def online_path_confirm(req: WebPathConfirmRequest):
    """确认草案 → 落库；带 feedback → 重新生成草案"""
    try:
        return await web_path_plan_agent.confirm_path(
            req.student_id, req.draft_id, req.feedback or "")
    except Exception as e:
        logger.exception("[online-path] confirm 失败")
        raise HTTPException(status_code=500, detail=f"路径确认失败: {str(e)[:200]}")


@router.get("/online-path/{student_id}")
async def online_path_get(student_id: str):
    """已确认路径 + 进度（练习卡回写到 nodes 方便前端聚合）"""
    path = load_path(student_id)
    if not path:
        return {"ok": False, "path": None, "message": "还没有已确认的学习路径"}

    # 非编程科目 → 剥离 OJ 练习卡。LeetCode/牛客等都是编程题库，物理/化学等科目不该有卡。
    # 同时自愈历史遗留数据：修复前保存的路径 JSON 里可能残留当时挂错的卡（如「牛客物理题」）。
    coll = path.get("collected") or {}
    subject = coll.get("subject") or coll.get("role") or path.get("topic") or ""
    is_non_programming = bool(subject) and not WebPathPlanAgent._is_programming_subject(subject)
    if is_non_programming:
        for stage in path.get("stages", []):
            stage["practice_cards"] = []

    synced = practice_data.sync_cards_to_path(student_id, path)
    # 外部学习自评聚合回写 nodes（所有科目都挂，非编程科目没 OJ 卡时尤其有用）
    synced = practice_data.sync_studies_to_path(student_id, synced)
    if is_non_programming:
        # 历史 practice_records 可能残留旧路径版本（如编程阶段）的卡，一并剥离
        for node in synced.get("nodes", []):
            node["practice_cards"] = []

    progress = calc_progress(synced)
    # is_programming：前端据此决定要不要显示「去官方找题」按钮（非编程科目不显示）
    return {"ok": True, "path": synced, "progress": progress,
            "is_programming": not is_non_programming}


# ======================== 练习卡 ========================

@router.post("/practice/deep-search")
async def practice_deep_search(req: PracticeDeepSearchRequest):
    """用户选「深入练习」时触发：按知识点搜官方 OJ 练习卡并落盘。
    搜索是尽力而为（当前网络 DDG/bing 基本不可达），搜不到就退回平台官方搜索页链接；
    非编程科目直接返回空——牛客/LeetCode 上没有物理题。"""
    try:
        topic = req.topic or req.knowledge_point or "编程"
        # 非编程科目：不给编程 OJ 卡
        path = load_path(req.student_id)
        if path:
            coll = path.get("collected") or {}
            subject = coll.get("subject") or coll.get("role") or path.get("topic") or ""
            if subject and not WebPathPlanAgent._is_programming_subject(subject):
                return {"ok": True, "node_id": req.node_id, "cards": [],
                        "source": "unsupported",
                        "message": "该科目没有对应的官方 OJ 题库，建议直接用课本/真题练习"}
        # 尽力而为搜索，超时压到 10s（当前网络每次都搜不到，别让用户白等 30s）
        candidates = await practice_card_searcher.search_problems(
            topic, platforms=req.platforms, max_results=req.max_results or 8, timeout=10.0)
        cards = await practice_card_searcher.structure_cards(
            candidates, topic, [req.knowledge_point] if req.knowledge_point else None,
            count=req.count or 3)
        saved = practice_data.seed_cards(req.student_id, req.node_id, cards)
        if candidates:
            msg = f"找到 {len(saved)} 道官方真实题目，去做题后回来标记状态吧！"
        else:
            msg = "没搜到精确题，给你官方平台的搜索入口，点进去按知识点挑一道练吧。"
        return {
            "ok": True,
            "node_id": req.node_id,
            "cards": saved,
            "source": "search" if candidates else "fallback",
            "message": msg,
        }
    except Exception as e:
        logger.exception("[practice] deep-search 失败")
        raise HTTPException(status_code=500, detail=f"练习搜索失败: {str(e)[:200]}")


@router.get("/practice/cards")
async def practice_cards(student_id: str, node_id: str):
    """某节点下的练习卡。非编程科目返回空——编程 OJ 卡（牛客/LeetCode）对物理等科目没意义。"""
    path = load_path(student_id)
    if path:
        coll = path.get("collected") or {}
        subject = coll.get("subject") or coll.get("role") or path.get("topic") or ""
        if subject and not WebPathPlanAgent._is_programming_subject(subject):
            return {"ok": True, "node_id": node_id, "cards": []}
    return {"ok": True, "node_id": node_id,
            "cards": practice_data.get_cards_by_node(student_id, node_id)}


@router.post("/practice/update")
async def practice_update(req: PracticeCardUpdate):
    """更新练习卡状态/答案/笔记"""
    card = practice_data.update_record(req.student_id, req.card_id, req.fields or {})
    if not card:
        raise HTTPException(status_code=404, detail="练习卡不存在")
    return {"ok": True, "card": card}


@router.post("/practice/checkin")
async def practice_checkin(req: PracticeCheckinRequest):
    """打卡：当天首次有效，返回连续学习天数"""
    result = practice_data.check_in(req.student_id, req.node_id, req.note or "")
    return {"ok": True, **result}


@router.get("/practice/progress/{student_id}")
async def practice_progress(student_id: str):
    """练习进度 + 激励数据（正确率/streak/打卡/最近记录）。

    OJ 卡统计对非编程科目清零（编程 OJ 卡对物理等科目没意义），
    但 ai_* 统计保留——AI 出题对任何科目都有效。清零块只覆盖 OJ 键。"""
    prog = practice_data.calc_practice_progress(student_id)
    # 非编程科目：卡数据（进度/错题/最近练习）清零，保留打卡与 streak（合法用户行为）
    path = load_path(student_id)
    if path:
        coll = path.get("collected") or {}
        subject = coll.get("subject") or coll.get("role") or path.get("topic") or ""
        if subject and not WebPathPlanAgent._is_programming_subject(subject):
            prog.update({
                "total_cards": 0, "done": 0, "undone": 0, "correct": 0, "wrong": 0,
                "progress_percent": 0, "accuracy_percent": 0,
                "by_node": {}, "recent": [],
            })
    return {"ok": True, "progress": prog}


# ======================== AI 出题落库 ========================

@router.post("/practice/save-ai-exercises")
async def practice_save_ai_exercises(req: SaveAiExercisesRequest):
    """聊天 AI 出题作答落库（幂等 upsert）→ 进「我的练习」统计与错题集。

    exercises/answers 与 /exercise/summarize 同构（JSON string），服务端重判对错。"""
    try:
        exercises = json.loads(req.exercises) if isinstance(req.exercises, str) and req.exercises else (req.exercises or [])
        answers = json.loads(req.answers) if isinstance(req.answers, str) and req.answers else (req.answers or {})
        if not isinstance(exercises, list):
            exercises = []
        if not isinstance(answers, dict):
            answers = {}
        saved = practice_data.save_ai_exercises(req.student_id, req.topic, exercises, answers)
        return {"ok": True, "saved": len(saved),
                "progress": practice_data.calc_practice_progress(req.student_id)}
    except Exception as e:
        logger.exception("[practice] save-ai-exercises 失败")
        raise HTTPException(status_code=500, detail=f"AI 练习保存失败: {str(e)[:200]}")


@router.get("/practice/wrong-questions")
async def practice_wrong_questions(student_id: str):
    """错题集：OJ 错题（全量，不截断）+ AI 错题（全量）。
    OJ 卡仅编程科目有；AI 错题任何科目都有。"""
    data = practice_data.load_records(student_id)
    oj = [
        {k: c.get(k) for k in ("card_id", "node_id", "platform", "problem_no", "title", "link",
                               "knowledge_point", "difficulty", "status", "my_answer", "note",
                               "solved_at", "updated_at")}
        for bucket in data["records"].values()
        for c in bucket if c.get("status") == "wrong"
    ]
    oj.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
    ai = practice_data.list_wrong_ai_exercises(student_id)
    return {"ok": True, "oj": oj, "ai": ai}


@router.post("/practice/redo-ai-exercise")
async def practice_redo_ai_exercise(req: RedoAiExerciseRequest):
    """错题重做：服务端重判，做对移出错题集 / 做错保留。"""
    record = practice_data.update_ai_exercise(req.student_id, req.exercise_id, req.user_answer)
    if not record:
        raise HTTPException(status_code=404, detail="AI 题目不存在")
    return {"ok": True, "correct": record["correct"], "record": record,
            "progress": practice_data.calc_practice_progress(req.student_id)}


# ======================== 题目集（我的题目：命名收藏） ========================

@router.get("/practice/collections")
async def practice_collections(student_id: str):
    """我的题目：全部命名题目集（含题目/题型/作答状态）。"""
    return {"ok": True, "collections": practice_data.list_collections(student_id)}


@router.post("/practice/collections/create")
async def practice_collections_create(req: CreateCollectionRequest):
    """新建命名题目集（空名/重名返回 400）。"""
    col = practice_data.create_collection(req.student_id, req.name)
    if not col:
        raise HTTPException(status_code=400, detail="题目集名称不能为空或已存在")
    return {"ok": True, "collection": col}


@router.post("/practice/collections/add")
async def practice_collections_add(req: AddToCollectionRequest):
    """收藏一题到题目集（按 qid 幂等 upsert）。"""
    q = practice_data.add_question_to_collection(
        req.student_id, req.collection_id, req.topic, req.exercise or {})
    if not q:
        raise HTTPException(status_code=404, detail="题目集不存在或题目内容为空")
    return {"ok": True, "question": q}


@router.post("/practice/collections/redo")
async def practice_collections_redo(req: RedoCollectionQuestionRequest):
    """题目集内重做：服务端重判。"""
    q = practice_data.redo_collection_question(
        req.student_id, req.collection_id, req.question_id, req.user_answer)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    return {"ok": True, "correct": q.get("correct"), "question": q}


@router.post("/practice/collections/remove-question")
async def practice_collections_remove(req: RemoveCollectionQuestionRequest):
    """从题目集移除一题。"""
    ok = practice_data.remove_question_from_collection(
        req.student_id, req.collection_id, req.question_id)
    return {"ok": ok}


@router.post("/practice/collections/delete")
async def practice_collections_delete(req: DeleteCollectionRequest):
    """删除整个题目集。"""
    ok = practice_data.delete_collection(req.student_id, req.collection_id)
    return {"ok": ok}


# ======================== 外部平台学习打卡（自评，呼应路径） ========================

@router.post("/practice/node-study")
async def practice_node_study(req: NodeStudyRequest):
    """记录「外部平台学习」自评上报；尽力把该节点下一个日任务标完成（呼应路径进度条）。"""
    study = practice_data.add_node_study(
        req.student_id, req.node_id, req.platform or "其他",
        req.hours or 0, req.problems or 0, req.mastery or 0, req.note or "")
    task_marked = False
    try:
        task_marked = mark_node_task_done(req.student_id, req.node_id)
    except Exception as e:
        logger.warning(f"[practice] mark_node_task_done 失败: {e}")
    return {"ok": True, "study": study, "task_marked": task_marked}


# ======================== 技能差距 ========================

@router.post("/skill-gap/analyze")
async def skill_gap_analyze(req: SkillGapRequest):
    """技能 vs 市场需求差距分析（雷达图数据）"""
    from core.capabilities.impl.skill_gap_agent import skill_gap_agent
    try:
        result = await skill_gap_agent.analyze(
            req.student_id, req.role or "后端开发工程师",
            req.language or "zh-CN", top_k=req.top_k or 6)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("[skill-gap] analyze 失败")
        raise HTTPException(status_code=500, detail=f"技能差距分析失败: {str(e)[:200]}")


__all__ = ["router"]
