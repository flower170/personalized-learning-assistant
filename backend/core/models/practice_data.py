"""
练习记录数据管理层 — JSON 文件持久化（与 learning_path_data.py 同模式）

职责：
- 练习卡落盘（seed_cards 幂等 upsert，保留已有状态）
- 练习记录更新（状态/答案/笔记）
- 打卡（check_in）与连续学习天数（streak）
- 进度统计（正确率、完成率、按节点分组、最近记录）
- AI 出题落库（save_ai_exercises 幂等 upsert，错题进错题集）

文件：data/practice_records/{student_id}.json

两类记录：
- records：OJ 练习卡（{node_id: [card, ...]}），来自「去官方找题」深搜，仅编程科目
- ai_exercises：聊天里 AI 出题的作答记录（subject-agnostic，任何科目都有效）
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "practice_records"

# 练习卡状态
STATUS_UNDONE = "undone"
STATUS_DONE = "done"
STATUS_CORRECT = "correct"
STATUS_WRONG = "wrong"


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _path(student_id: str) -> Path:
    return DATA_DIR / f"{student_id}.json"


def _empty_record(student_id: str) -> dict:
    return {
        "student_id": student_id,
        "path_topic": "",
        "records": {},       # {node_id: [card, ...]}
        "ai_exercises": [],  # [ai_exercise, ...]（聊天 AI 出题作答记录）
        "collections": [],   # [collection, ...]（我的题目：用户命名收藏的题目集）
        "node_studies": [],  # [study, ...]（外部平台学习自评上报，按 node_id 呼应路径）
        "checkins": [],      # [{date, node_id, note}]
        "streak": {"current": 0, "longest": 0, "last_checkin": None},
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_records(student_id: str) -> dict:
    """加载练习记录，无则返回空结构（不落盘）"""
    _ensure_dir()
    p = _path(student_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            base = _empty_record(student_id)
            base.update(data)
            return base
        except Exception as e:
            logger.error(f"加载练习记录失败 {student_id}: {e}")
    return _empty_record(student_id)


def save_records(student_id: str, data: dict):
    _ensure_dir()
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _path(student_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"[PracticeData] 已保存: {student_id}")


# ---------------- 练习卡 ----------------

def seed_cards(student_id: str, node_id: str, cards: list[dict]) -> list[dict]:
    """批量写入练习卡，按 card_id 幂等 upsert（已存在的卡保留状态/笔记）。"""
    if not cards:
        return []
    data = load_records(student_id)
    bucket = data["records"].setdefault(node_id, [])
    existing = {c["card_id"]: c for c in bucket}
    now = datetime.now().isoformat(timespec="seconds")
    for card in cards:
        card["node_id"] = node_id
        card.setdefault("created_at", now)
        card["updated_at"] = now
        cid = card.get("card_id")
        if not cid:
            continue
        if cid in existing:
            old = existing[cid]
            # 保留用户产生的状态/答案/笔记，只刷新结构化字段
            for k in ("status", "my_answer", "note", "solved_at"):
                if old.get(k):
                    card[k] = old[k]
        existing[cid] = card
    data["records"][node_id] = list(existing.values())
    save_records(student_id, data)
    return data["records"][node_id]


def update_record(student_id: str, card_id: str, fields: dict) -> Optional[dict]:
    """更新单张练习卡（状态/答案/笔记等），找不到返回 None。

    status 语义：undone=未做 / done=已做 / correct=做对 / wrong=做错
    从 done/wrong/correct → correct/wrong 视为答题，记 solved_at。
    """
    data = load_records(student_id)
    now = datetime.now().isoformat(timespec="seconds")
    for node_id, bucket in data["records"].items():
        for card in bucket:
            if card.get("card_id") != card_id:
                continue
            new_status = fields.get("status", card.get("status"))
            if new_status in (STATUS_DONE, STATUS_CORRECT, STATUS_WRONG) and card.get("status") in (STATUS_UNDONE, STATUS_DONE, STATUS_WRONG, STATUS_CORRECT) and new_status != card.get("status"):
                card["solved_at"] = now
            for k in ("status", "my_answer", "note"):
                if k in fields:
                    card[k] = fields[k]
            card["updated_at"] = now
            save_records(student_id, data)
            return card
    logger.warning(f"[PracticeData] 未找到练习卡: {card_id}")
    return None


def get_cards_by_node(student_id: str, node_id: str) -> list[dict]:
    data = load_records(student_id)
    return data["records"].get(node_id, [])


def get_all_records(student_id: str) -> dict:
    data = load_records(student_id)
    return {k: v for k, v in data["records"].items() if v}


def sync_cards_to_path(student_id: str, path_data: dict) -> dict:
    """把 records 里的练习卡回写到路径 nodes 的 practice_cards 字段（供前端聚合展示）。"""
    data = load_records(student_id)
    for node in path_data.get("nodes", []):
        nid = node.get("node_id")
        cards = data["records"].get(nid, [])
        if cards:
            node["practice_cards"] = cards
    return path_data


# ---------------- AI 出题落库 ----------------

def _ai_exercise_id(topic: str, question: str) -> str:
    """服务端稳定 id：topic + 题干 哈希。前端 ex_i 按索引生成（修改题目后会变），不能作主键。"""
    return "ai_" + hashlib.sha1(f"{topic}:::{question}".encode("utf-8")).hexdigest()[:16]


def _judge_answer(ex_type: str, canonical_answer, user_answer) -> Optional[bool]:
    """服务端重判对错（不信任前端 correct 布尔，防止伪造/不一致）。
    - choice: 答案 label 精确匹配（去空白、大小写不敏感）
    - judge: 'true'/'false' ↔ bool
    - fill: 去空白精确匹配（宽松含前后空格）
    - essay/application: 无法自动判 → None
    """
    if user_answer is None:
        return None
    if canonical_answer is None:
        return None
    ans = str(canonical_answer).strip()
    user = str(user_answer).strip()
    if ex_type in ("essay", "application", "multi_essay"):
        return None
    if ex_type == "judge":
        norm = {"true": True, "false": False, "对": True, "错": False,
                "正确": True, "错误": False, "√": True, "×": False,
                "v": True, "x": False}
        a = norm.get(ans.lower(), ans.lower() == "true")
        u = norm.get(user.lower(), user.lower() == "true")
        return a == u
    if ex_type == "choice" or ex_type in ("multiple", "multi"):
        # 多选答案可能形如 "ABD"，逐字母排序后比较
        a = "".join(sorted(ans.upper()))
        u = "".join(sorted(user.upper()))
        return a == u
    # fill / 其他：去空白精确
    return ans.replace(" ", "").lower() == user.replace(" ", "").lower()


def save_ai_exercises(student_id: str, topic: str,
                      exercises: list[dict], answers: dict) -> list[dict]:
    """聊天 AI 出题作答落库（幂等 upsert）。

    - 只持久化 answers 里存在作答的题
    - 按 exercise_id（topic+题干哈希）upsert，重复提交无害
    - 服务端重判对错；user_answer 与存量不同才 attempts += 1

    :param exercises: 题目 [{id, type, question, options, answer, explanation, difficulty}]
    :param answers:   作答 {"ex_0": {id, userAnswer, correct, type}}
    :return: 本次保存的 AI 记录列表
    """
    if not exercises or not answers:
        return []
    data = load_records(student_id)
    bucket = data["ai_exercises"]
    by_id = {r["exercise_id"]: r for r in bucket}
    now = datetime.now().isoformat(timespec="seconds")
    saved: list[dict] = []
    for ex in exercises:
        ex_id = ex.get("id") or ex.get("exercise_id")
        ans = answers.get(ex_id)
        if not ans:
            continue
        user_answer = ans.get("userAnswer", "")
        question = str(ex.get("question", "") or "").strip()
        if not question:
            continue
        eid = _ai_exercise_id(topic, question)
        ex_type = str(ex.get("type", "choice") or "choice")
        canonical = ex.get("answer")
        correct = _judge_answer(ex_type, canonical, user_answer)
        existing = by_id.get(eid)
        if existing:
            record = existing
            old_answer = record.get("user_answer")
            if old_answer != user_answer:
                record["attempts"] = int(record.get("attempts", 0)) + 1
            record["user_answer"] = user_answer
            record["correct"] = correct
            record["updated_at"] = now
        else:
            record = {
                "record_type": "ai_exercise",
                "exercise_id": eid,
                "topic": topic,
                "type": ex_type,
                "difficulty": str(ex.get("difficulty", "") or ""),
                "question": question,
                "options": ex.get("options", []) if ex_type == "choice" else [],
                "answer": canonical,
                "explanation": str(ex.get("explanation", "") or ""),
                "user_answer": user_answer,
                "correct": correct,
                "attempts": 1,
                "created_at": now,
                "updated_at": now,
            }
            by_id[eid] = record
            bucket.append(record)
        saved.append(record)
    if saved:
        save_records(student_id, data)
    return saved


def get_ai_exercises(student_id: str) -> list[dict]:
    """全部 AI 出题记录，updated_at 倒序。"""
    data = load_records(student_id)
    return sorted(data["ai_exercises"], key=lambda r: r.get("updated_at") or "", reverse=True)


def list_wrong_ai_exercises(student_id: str) -> list[dict]:
    """错题集 AI 段：correct is False 的记录，全量不截断。"""
    return [r for r in get_ai_exercises(student_id) if r.get("correct") is False]


def update_ai_exercise(student_id: str, exercise_id: str,
                       user_answer: str) -> Optional[dict]:
    """错题重做：服务端重判、更新 user_answer/correct/attempts/updated_at。
    找不到返回 None。"""
    data = load_records(student_id)
    now = datetime.now().isoformat(timespec="seconds")
    for record in data["ai_exercises"]:
        if record.get("exercise_id") != exercise_id:
            continue
        correct = _judge_answer(record.get("type"), record.get("answer"), user_answer)
        record["user_answer"] = user_answer
        record["correct"] = correct
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["updated_at"] = now
        save_records(student_id, data)
        return record
    logger.warning(f"[PracticeData] 未找到 AI 记录: {exercise_id}")
    return None


# ---------------- 题目集（我的题目：用户命名收藏） ----------------

def _collection_question_id(topic: str, question: str) -> str:
    """集合内稳定 id：topic + 题干 哈希（与 _ai_exercise_id 同模式）。"""
    return "cq_" + hashlib.sha1(f"{topic}:::{question}".encode("utf-8")).hexdigest()[:16]


def _normalize_collection_question(topic: str, ex: dict) -> Optional[dict]:
    """把前端题目 dict 清洗成集合内标准结构（同 save_ai_exercises 的清洗）。
    题干为空返回 None。"""
    question = str(ex.get("question", "") or "").strip()
    if not question:
        return None
    ex_type = str(ex.get("type", "choice") or "choice")
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "qid": _collection_question_id(topic, question),
        "topic": topic,
        "type": ex_type,
        "difficulty": str(ex.get("difficulty", "") or ""),
        "question": question,
        "options": ex.get("options", []) if ex_type == "choice" else [],
        "answer": ex.get("answer"),
        "explanation": str(ex.get("explanation", "") or ""),
        "user_answer": "",
        "correct": None,
        "attempts": 0,
        "created_at": now,
        "updated_at": now,
    }


def list_collections(student_id: str) -> list[dict]:
    """全部命名题目集（含题目与作答状态），updated_at 倒序。"""
    data = load_records(student_id)
    return sorted(data.get("collections", []),
                  key=lambda c: c.get("updated_at") or "", reverse=True)


def create_collection(student_id: str, name: str) -> Optional[dict]:
    """新建命名题目集（去空格；空名或重名返回 None）。"""
    name = (name or "").strip()
    if not name:
        return None
    data = load_records(student_id)
    if any(c.get("name") == name for c in data.get("collections", [])):
        logger.warning(f"[PracticeData] 题目集重名: {name}")
        return None
    now = datetime.now().isoformat(timespec="seconds")
    col = {
        "collection_id": "col_" + uuid.uuid4().hex[:12],
        "name": name,
        "created_at": now,
        "updated_at": now,
        "questions": [],
    }
    data.setdefault("collections", []).append(col)
    save_records(student_id, data)
    return col


def add_question_to_collection(student_id: str, collection_id: str,
                               topic: str, ex: dict) -> Optional[dict]:
    """把一题收藏进题目集（按 qid 幂等 upsert，已存在只刷新时间），返回该题。
    集合不存在 / 题干为空返回 None。"""
    q = _normalize_collection_question(topic or "", ex or {})
    if not q:
        return None
    data = load_records(student_id)
    now = datetime.now().isoformat(timespec="seconds")
    for col in data.get("collections", []):
        if col.get("collection_id") != collection_id:
            continue
        for existing in col.get("questions", []):
            if existing.get("qid") == q["qid"]:
                existing["updated_at"] = now
                col["updated_at"] = now
                save_records(student_id, data)
                return existing
        q["created_at"] = now
        q["updated_at"] = now
        col.setdefault("questions", []).append(q)
        col["updated_at"] = now
        save_records(student_id, data)
        return q
    logger.warning(f"[PracticeData] 未找到题目集: {collection_id}")
    return None


def redo_collection_question(student_id: str, collection_id: str,
                             qid: str, user_answer: str) -> Optional[dict]:
    """题目集内重做：服务端重判、attempts+1、更新 user_answer/correct/updated_at。"""
    data = load_records(student_id)
    now = datetime.now().isoformat(timespec="seconds")
    for col in data.get("collections", []):
        if col.get("collection_id") != collection_id:
            continue
        for q in col.get("questions", []):
            if q.get("qid") != qid:
                continue
            q["user_answer"] = user_answer
            q["correct"] = _judge_answer(q.get("type"), q.get("answer"), user_answer)
            q["attempts"] = int(q.get("attempts", 0)) + 1
            q["updated_at"] = now
            col["updated_at"] = now
            save_records(student_id, data)
            return q
    return None


def remove_question_from_collection(student_id: str, collection_id: str,
                                    qid: str) -> bool:
    """从题目集移除一题，返回是否真的删掉了。"""
    data = load_records(student_id)
    for col in data.get("collections", []):
        if col.get("collection_id") != collection_id:
            continue
        before = len(col.get("questions", []))
        col["questions"] = [q for q in col.get("questions", []) if q.get("qid") != qid]
        if len(col["questions"]) != before:
            col["updated_at"] = datetime.now().isoformat(timespec="seconds")
            save_records(student_id, data)
            return True
    return False


def delete_collection(student_id: str, collection_id: str) -> bool:
    """删除整个题目集，返回是否真的删掉了。"""
    data = load_records(student_id)
    before = len(data.get("collections", []))
    data["collections"] = [c for c in data.get("collections", [])
                           if c.get("collection_id") != collection_id]
    if len(data["collections"]) != before:
        save_records(student_id, data)
        return True
    return False


# ---------------- 外部平台学习打卡（自评，挂到路径节点） ----------------

def add_node_study(student_id: str, node_id: str, platform: str,
                   hours: float, problems: int, mastery: int,
                   note: str) -> dict:
    """记录一次「外部平台学习」自评上报，追加日志。"""
    data = load_records(student_id)
    now = datetime.now().isoformat(timespec="seconds")
    entry = {
        "node_id": node_id,
        "platform": platform or "其他",
        "hours": round(float(hours or 0), 1),
        "problems": int(problems or 0),
        "mastery": max(0, min(5, int(mastery or 0))),
        "note": note or "",
        "date": date.today().isoformat(),
        "updated_at": now,
    }
    data.setdefault("node_studies", []).append(entry)
    save_records(student_id, data)
    return entry


def summarize_node_studies(student_id: str) -> dict:
    """按 node_id 聚合外部学习：
    {node_id: {total_hours, total_problems, mastery(最近), platform(最近), latest_note, logs, last_updated}}"""
    data = load_records(student_id)
    agg: dict[str, dict] = {}
    for s in data.get("node_studies", []):
        nid = s.get("node_id") or ""
        if not nid:
            continue
        e = agg.get(nid) or {
            "node_id": nid, "platform": s.get("platform", ""),
            "total_hours": 0.0, "total_problems": 0,
            "mastery": 0, "latest_note": "", "logs": 0,
            "last_updated": s.get("updated_at", ""),
        }
        e["total_hours"] = round(e["total_hours"] + float(s.get("hours") or 0), 1)
        e["total_problems"] += int(s.get("problems") or 0)
        e["mastery"] = int(s.get("mastery") or 0)   # 最近一次上报即覆盖
        e["platform"] = s.get("platform", e["platform"])
        if s.get("note"):
            e["latest_note"] = s["note"]
        if s.get("updated_at", "") >= e["last_updated"]:
            e["last_updated"] = s.get("updated_at", "")
        e["logs"] += 1
        agg[nid] = e
    return agg


def sync_studies_to_path(student_id: str, path_data: dict) -> dict:
    """把外部学习聚合回写到路径 nodes 的 node_study 字段（所有科目都挂）。"""
    summary = summarize_node_studies(student_id)
    for node in path_data.get("nodes", []):
        nid = node.get("node_id")
        if nid in summary:
            node["node_study"] = summary[nid]
    return path_data


# ---------------- 打卡 & 连续天数 ----------------

def check_in(student_id: str, node_id: str, note: str = "") -> dict:
    """打卡：当天第一次打卡有效，返回 {today, streak}。"""
    data = load_records(student_id)
    today = date.today().isoformat()
    if not any(c["date"] == today for c in data["checkins"]):
        data["checkins"].append({"date": today, "node_id": node_id, "note": note})
        # 计算新 streak
        all_days = sorted({c["date"] for c in data["checkins"]}, reverse=True)
        cur, longest = 0, data["streak"].get("longest", 0)
        prev = date.today()
        for d in all_days:
            dd = date.fromisoformat(d)
            if cur == 0 or (prev - dd).days == 1:
                cur += 1
                prev = dd
            else:
                break
        data["streak"]["current"] = cur
        data["streak"]["longest"] = max(longest, cur)
        data["streak"]["last_checkin"] = today
        save_records(student_id, data)
    return {"today": today,
            "streak": data["streak"]["current"],
            "longest": data["streak"]["longest"]}


def calc_streak(student_id: str) -> dict:
    """返回当前/最长连续学习天数。"""
    data = load_records(student_id)
    all_days = sorted({c["date"] for c in data["checkins"]}, reverse=True)
    cur, longest = 0, 0
    prev = None
    for d in all_days:
        dd = date.fromisoformat(d)
        if prev is None or (prev - dd).days == 1:
            cur += 1
            prev = dd
        else:
            cur = 1
            prev = dd
        longest = max(longest, cur)
    # 若昨天没打卡，当前 streak 应归零（连续到今天才算）
    if all_days and date.fromisoformat(all_days[0]) < date.today():
        cur = 0
    return {"current": cur, "longest": longest,
            "last_checkin": all_days[0] if all_days else None}


# ---------------- 进度统计 ----------------

def calc_practice_progress(student_id: str) -> dict:
    """练习进度总览：
    {total_cards, done, undone, correct, wrong, progress_percent, accuracy_percent,
     by_node, recent, streak, checkins, total_checkins,   # OJ 卡统计
     ai_total, ai_correct, ai_wrong, ai_accuracy_percent, ai_recent,  # AI 出题统计
     total_correct, total_answered, total_accuracy_percent}           # OJ+AI 合并
    """
    data = load_records(student_id)
    by_node = {}
    total = done = correct = wrong = 0
    recent = []
    for node_id, bucket in data["records"].items():
        node_total = len(bucket)
        node_done = sum(1 for c in bucket if c.get("status") != STATUS_UNDONE)
        node_correct = sum(1 for c in bucket if c.get("status") == STATUS_CORRECT)
        node_wrong = sum(1 for c in bucket if c.get("status") == STATUS_WRONG)
        total += node_total
        done += node_done
        correct += node_correct
        wrong += node_wrong
        if node_total:
            by_node[node_id] = {
                "total": node_total, "done": node_done,
                "correct": node_correct, "wrong": node_wrong,
                "progress_percent": round(node_done / node_total * 100),
            }
        for c in bucket:
            recent.append({k: c.get(k) for k in (
                "card_id", "node_id", "platform", "title", "link",
                "knowledge_point", "difficulty", "status", "note", "updated_at")})
    recent.sort(key=lambda c: c.get("updated_at") or "", reverse=True)

    # AI 出题统计（correct in (True, False) 才计入；essay 等未自动判的不计）
    ai_exercises = data.get("ai_exercises", [])
    ai_answered = [r for r in ai_exercises if r.get("correct") is not None]
    ai_correct = sum(1 for r in ai_answered if r.get("correct") is True)
    ai_wrong = len(ai_answered) - ai_correct
    ai_recent = [{
        "exercise_id": r.get("exercise_id"),
        "topic": r.get("topic", ""),
        "question": (r.get("question") or "")[:60],
        "type": r.get("type", ""),
        "status": "correct" if r.get("correct") is True else "wrong",
        "updated_at": r.get("updated_at", ""),
    } for r in sorted(ai_exercises, key=lambda r: r.get("updated_at") or "", reverse=True)[:20]]

    answered = correct + wrong
    streak = calc_streak(student_id)
    total_answered = answered + len(ai_answered)
    total_correct = correct + ai_correct
    return {
        "student_id": student_id,
        "total_cards": total,
        "done": done,
        "undone": total - done,
        "correct": correct,
        "wrong": wrong,
        "progress_percent": round(done / total * 100) if total else 0,
        "accuracy_percent": round(correct / answered * 100) if answered else 0,
        "by_node": by_node,
        "recent": recent[:20],
        "streak": streak,
        "checkins": data["checkins"],
        "total_checkins": len(data["checkins"]),
        # AI 出题统计（subject-agnostic，任何科目都有效）
        "ai_total": len(ai_answered),
        "ai_correct": ai_correct,
        "ai_wrong": ai_wrong,
        "ai_accuracy_percent": round(ai_correct / len(ai_answered) * 100) if ai_answered else 0,
        "ai_recent": ai_recent,
        # OJ + AI 合并口径（供「总正确率」）
        "total_correct": total_correct,
        "total_answered": total_answered,
        "total_accuracy_percent": round(total_correct / total_answered * 100) if total_answered else 0,
    }


__all__ = [
    "load_records", "save_records", "seed_cards", "update_record",
    "get_cards_by_node", "get_all_records", "sync_cards_to_path",
    "save_ai_exercises", "get_ai_exercises", "list_wrong_ai_exercises",
    "update_ai_exercise", "_judge_answer",
    "list_collections", "create_collection", "add_question_to_collection",
    "redo_collection_question", "remove_question_from_collection",
    "delete_collection",
    "add_node_study", "summarize_node_studies", "sync_studies_to_path",
    "check_in", "calc_streak", "calc_practice_progress",
]
