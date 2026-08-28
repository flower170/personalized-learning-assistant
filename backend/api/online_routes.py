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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse

from core.models.schemas import (
    WebPathStartRequest, WebPathAnswersRequest, WebPathConfirmRequest, DraftStreamRequest, DraftResourceRequest,
    PracticeDeepSearchRequest, PracticeCardUpdate, PracticeCheckinRequest,
    SaveAiExercisesRequest, RedoAiExerciseRequest, WrongRemoveRequest,
    CreateCollectionRequest, AddToCollectionRequest, RedoCollectionQuestionRequest,
    RemoveCollectionQuestionRequest, DeleteCollectionRequest,
    DeleteNoteRequest,
    NodeStudyRequest, SkillGapRequest,
    NodeResourceAddRequest, NodeResourceDeleteRequest, NodeResourceWatchRequest,
    NodeSkipRequest, DailyExerciseRequest, VideoSearchRequest, TaskToggleRequest,
    DailyLogAddRequest, DailyLogUpdateRequest, DailyLogDeleteRequest,
)
from core.capabilities.impl.web_path_plan_agent import web_path_plan_agent, WebPathPlanAgent
from core.capabilities.impl.practice_search import practice_card_searcher
from core.capabilities.impl.resource_agents import exercise_agent
from core.models import practice_data
from core.models.learning_path_data import (
    load_path, calc_progress, mark_node_task_done, mark_first_incomplete_task_done,
    skip_node, toggle_task_done,
)
from core.utils.video_cover import search_bilibili_videos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["online-path", "practice", "skill-gap"])


# ======================== 交互式联网学习路径 ========================

@router.post("/online-path/start")
async def online_path_start(req: WebPathStartRequest):
    """Stage 1：画像起步 + 联网补充，返回需要补充的问题或直接出草案"""
    try:
        return await web_path_plan_agent.start_conversation(
            req.student_id, req.topic, daily_hours=req.daily_hours, cycle=req.cycle)
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


@router.post("/online-path/draft-stream")
async def online_path_draft_stream(req: DraftStreamRequest):
    """流式生成路径草案（SSE）：progress/chunk 进度事件 + 最终 complete（含 draft）"""
    async def event_stream():
        try:
            async for evt in web_path_plan_agent.generate_draft_stream(
                req.student_id, req.topic, req.collected or {}, req.draft_id or ""):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("[online-path] draft-stream 失败")
            err = {"event": "error", "message": f"路径生成失败: {str(e)[:150]}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/online-path/draft-resource")
async def online_path_draft_resource(req: DraftResourceRequest):
    """向导草案阶段：按规划给某个节点添加一条学习资源（B站/文档链接）"""
    if not (req.title or "").strip() or not (req.url or "").strip():
        return {"ok": False, "error": "标题和链接不能为空"}
    draft = web_path_plan_agent.add_draft_resource(
        req.student_id, req.draft_id, req.node_id, req.title.strip(), req.url.strip(), req.platform)
    if draft is None:
        return {"ok": False, "error": "草案不存在或节点不存在，请重新规划"}
    return {"ok": True, "path": draft}


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
    # 节点学习资源（B站/视频/文档链接 + 看完状态）合并回写 nodes
    synced = practice_data.sync_resources_to_path(student_id, synced)
    # 课程级资源（整套课视频，node_id == "__course__"）挂到 path 顶层 course_resources
    synced = practice_data.sync_course_resources_to_path(student_id, synced)
    # 用户日计划学习记录（每天学了什么+打钩）按节点回写 nodes
    synced = practice_data.sync_daily_logs_to_path(student_id, synced)
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


@router.post("/practice/wrong-remove")
async def practice_wrong_remove(req: WrongRemoveRequest):
    """错题集移除：AI 错题删除记录；OJ 错题置为 done 移出错题集（保留练习卡）。"""
    if req.kind == "ai":
        ok = practice_data.remove_ai_exercise(req.student_id, req.target_id)
        if not ok:
            raise HTTPException(status_code=404, detail="错题不存在")
    else:
        card = practice_data.update_record(req.student_id, req.target_id, {"status": "done"})
        if not card:
            raise HTTPException(status_code=404, detail="练习卡不存在")
    return {"ok": True}


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


# ======================== 我的笔记（保存的思维导图） ========================

@router.get("/practice/notes")
async def practice_notes(student_id: str):
    """我的笔记：全部保存的思维导图图片笔记（updated_at 倒序）。"""
    return {"ok": True, "notes": practice_data.list_notes(student_id)}


@router.get("/practice/notes/image/{student_id}/{note_id}")
async def practice_note_image(student_id: str, note_id: str):
    """返回某条笔记的思维导图 PNG 图片。"""
    note = next((n for n in practice_data.list_notes(student_id)
                 if n.get("note_id") == note_id), None)
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    p = practice_data.note_image_file(student_id, note_id)
    if not p:
        raise HTTPException(status_code=404, detail="笔记图片不存在")
    return FileResponse(p, media_type="image/png")


@router.post("/practice/notes/add")
async def practice_notes_add(student_id: str = Form(...),
                             title: str = Form(...),
                             topic: str = Form(""),
                             image: UploadFile = File(...)):
    """保存一条思维导图图片笔记（multipart：标题 + 可选主题 + PNG 图片）。"""
    image_bytes = await image.read()
    if len(image_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片过大（>8MB）")
    if not title.strip() or not image_bytes:
        raise HTTPException(status_code=400, detail="笔记标题和图片不能为空")
    note = practice_data.add_note(student_id, title.strip(), topic, image_bytes)
    if not note:
        raise HTTPException(status_code=500, detail="笔记保存失败")
    return {"ok": True, "note": note}


@router.post("/practice/notes/delete")
async def practice_notes_delete(req: DeleteNoteRequest):
    """删除一条笔记（含图片文件）。"""
    ok = practice_data.delete_note(req.student_id, req.note_id)
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


# ======================== 节点学习资源（B站/视频/文档链接 + 看完自评） ========================

@router.post("/practice/node-resources/add")
async def practice_node_resources_add(req: NodeResourceAddRequest):
    """给路径节点添加一条学习资源（如 B站课程链接），返回资源条目。"""
    res = practice_data.add_node_resource(
        req.student_id, req.node_id, req.title, req.url, req.platform or "")
    if not res:
        raise HTTPException(status_code=400, detail="标题和链接不能为空")
    return {"ok": True, "resource": res}


@router.post("/practice/node-resources/delete")
async def practice_node_resources_delete(req: NodeResourceDeleteRequest):
    """删除一条节点学习资源。"""
    ok = practice_data.delete_node_resource(req.student_id, req.rid)
    return {"ok": ok}


@router.post("/practice/node-resources/watched")
async def practice_node_resources_watched(req: NodeResourceWatchRequest):
    """标记某条资源「看完了」+ 自评（学到了什么）→ 推动路径进度。

    课程级资源（node_id == "__course__"，整套课视频）看完 → 推进第一个未完成任务；
    节点级资源 → 推进该节点第一个未完成任务。"""
    res = practice_data.mark_resource_watched(req.student_id, req.rid, req.watch_note or "")
    if not res:
        raise HTTPException(status_code=404, detail="资源不存在")
    task_marked = False
    try:
        if res.get("node_id") == practice_data.COURSE_NODE_ID:
            task_marked = mark_first_incomplete_task_done(req.student_id)
        else:
            task_marked = mark_node_task_done(req.student_id, res.get("node_id", ""))
    except Exception as e:
        logger.warning(f"[practice] 资源看完推进度失败: {e}")
    return {"ok": True, "resource": res, "task_marked": task_marked}


@router.post("/practice/node-skip")
async def practice_node_skip(req: NodeSkipRequest):
    """用户「这个知识点我会了」→ 跳过该节点全部日任务/学习记录，返回推进数。"""
    marked = skip_node(req.student_id, req.node_id)
    return {"ok": True, "marked": marked}


# ======================== 日计划：用户记录每天学了什么 + 打钩 ========================

@router.post("/practice/daily-log/add")
async def practice_daily_log_add(req: DailyLogAddRequest):
    """给某节点加一条「今天学了什么」记录（默认当天，未打钩）。"""
    log = practice_data.add_daily_log(req.student_id, req.node_id, req.content, req.date)
    if not log:
        raise HTTPException(status_code=400, detail="学习内容不能为空")
    return {"ok": True, "log": log}


@router.post("/practice/daily-log/update")
async def practice_daily_log_update(req: DailyLogUpdateRequest):
    """编辑某条记录的内容 / 打钩状态。"""
    log = practice_data.update_daily_log(req.student_id, req.log_id,
                                         req.content, req.done)
    if not log:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True, "log": log}


@router.post("/practice/daily-log/delete")
async def practice_daily_log_delete(req: DailyLogDeleteRequest):
    """删除一条学习记录。"""
    ok = practice_data.delete_daily_log(req.student_id, req.log_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


# ======================== 今日练习（每天不同题目） ========================

def _node_exercise_topic(path: dict, node_id: str, task_day: int | None = None) -> tuple[str, str]:
    """取节点用于出题的知识点 + 节点/任务标题。node_id 为空时自动定位"今天该学的节点"。

    task_day 给定 → 取该节点指定 day 的日任务作主题（从具体任务做题）；
    否则取该节点第一个未完成任务；都没有则用节点 title。"""
    nodes = path.get("nodes", []) or []
    if not nodes:
        return "", ""

    target = None
    if node_id:
        target = next((n for n in nodes if n.get("node_id") == node_id), None)
    if not target:
        # 新口径优先：第一个有未打钩学习记录的节点
        target = next((n for n in nodes
                       if any(not l.get("done") for l in n.get("daily_logs", []))), None)
    if not target:
        # 旧口径：含今天 day 的节点 → 首个未完成任务节点
        today = (datetime.now() - datetime.fromisoformat(
            path.get("created_at", datetime.now().isoformat()))).days + 1
        target = next((n for n in nodes
                       if any(t.get("day") == today for t in n.get("daily_tasks", []))), None)
    if not target:
        target = next((n for n in nodes
                       if any(not t.get("completed") for t in n.get("daily_tasks", []))), None)
    if not target:
        target = next((n for n in nodes if n.get("daily_logs")), None)
    if not target:
        target = nodes[0]

    title = (target.get("title") or "").strip()
    # 新口径主题：最近一条未打钩学习记录的内容（用户正在学的）
    undone = [l for l in (target.get("daily_logs") or []) if not l.get("done")]
    if undone:
        topic = (undone[-1].get("content") or "").strip()
        if topic:
            return topic, target.get("node_id", "")
    task = None
    if task_day is not None:
        task = next((t for t in target.get("daily_tasks", [])
                     if t.get("day") == task_day), None)
    if task is None:
        task = next((t for t in target.get("daily_tasks", []) if not t.get("completed")), None)
    task_title = (task.get("title") or title) if task else title
    # 去掉「- 第X天」尾巴，用纯知识点做主题
    import re as _re
    clean = _re.sub(r"[-－—]\s*第\d+天$", "", task_title).strip() or title
    return clean, target.get("node_id", "")


@router.post("/practice/daily-exercises")
async def practice_daily_exercises(req: DailyExerciseRequest):
    """今日练习：按当前节点/知识点用 AI 出 count 道题（不落库，作答走 save-ai-exercises）。"""
    path = load_path(req.student_id)
    if not path:
        return {"ok": True, "node_id": req.node_id, "exercises": [],
                "message": "还没有学习路径，先去规划吧"}
    topic, node_id = _node_exercise_topic(path, req.node_id, req.task_day)
    if not topic:
        return {"ok": True, "node_id": node_id, "exercises": [],
                "message": "暂时没有可练习的知识点"}
    count = max(1, min(10, req.count or 3))
    demand = (
        f"这是「今日练习」：围绕知识点「{topic}」生成 {count} 道题目，"
        f"题型混合选择/填空/判断，难度基础到进阶。请严格按照数量生成 {count} 道，不要多也不要少。"
    )
    try:
        chunks: list[str] = []
        async for chunk in exercise_agent.generate_exercises(
                topic, student_id=req.student_id, user_demand=demand):
            chunks.append(chunk or "")
        text = "".join(chunks)
        exercises = exercise_agent.extract_exercise_json(text) or []
        exercises = exercises[:count]
        return {"ok": True, "node_id": node_id, "topic": topic, "exercises": exercises}
    except Exception as e:
        logger.exception("[practice] daily-exercises 失败")
        raise HTTPException(status_code=500, detail=f"出题失败: {str(e)[:200]}")


@router.post("/practice/video-search")
async def practice_video_search(req: VideoSearchRequest):
    """搜索 B站热门视频（按播放量/点赞降序），供用户选择加入节点资源。"""
    keyword = (req.keyword or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="请输入搜索关键词")
    videos = await search_bilibili_videos(keyword, max(1, req.page))
    return {
        "ok": True,
        "videos": videos,
        "message": "没搜到，试试别的关键词或自定义添加" if not videos else "",
    }


@router.post("/practice/task-toggle")
async def practice_task_toggle(req: TaskToggleRequest):
    """逐小任务打√（可逆）：切换某节点某天任务的完成状态。"""
    task = toggle_task_done(req.student_id, req.node_id, req.day)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    path = load_path(req.student_id)
    progress = calc_progress(path) if path else None
    return {"ok": True, "task": task, "progress": progress}


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
