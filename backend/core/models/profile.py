"""
学生画像管理与持久化
支持内存存储（开发用）和后续扩展为数据库存储
"""
import json
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from core.models.schemas import StudentProfile, RadarScores, RadarDimension

logger = logging.getLogger(__name__)

# 画像抽取的 System Prompt（Prompt 2：后端内部调用，学生不可见）
PROFILE_EXTRACTION_SYSTEM_PROMPT = '''你是专业的学生画像增量抽取引擎。根据【上一版画像（旧画像）】和【完整对话记录（所有轮次）】，抽取结构化画像数据。
必须严格按照以下流程处理：

## 流程 1：六大维度 + 扩展维度 识别
从对话中提取以下 7+1 项信息：
- knowledge_base.mastered[] 已掌握知识点
- knowledge_base.weak[]     薄弱知识点 / 理解卡点
- knowledge_base.untouched[] 未接触知识点
- cognitive_style            视觉型/听觉型/读写型/动觉型（合理推断，不编造）
- preferred_pace             慢速细学/适中/快速速成
- error_prone_areas[]        常错题型/易错点/思维误区
  双归规则：学生自述"觉得难/不会/老出错/卡住/薄弱"的知识点（如"数组有点难"），必须同时归入 error_prone_areas[] 与 knowledge_base.weak[]，不得只归一处；knowledge_base.mastered 只放学生明确表示已掌握的内容。
- interests[]                兴趣领域/偏好话题/应用方向
- learning_goals.short_term  + learning_goals.long_term
- goal_attribute             应试/就业/考研/自学兴趣
- daily_available_hours      每日可投入时长（h，数值）

## 流程 2：新旧信息冲突处理（必须执行）
如果对话中出现新说法与【旧画像】中的字段冲突：
  - 以【对话中较晚的那轮】为准覆盖旧值；
  - 在 conflicts[] 中登记冲突：{dim:"字段名", old:"原值", new:"新值", turn:N, reason:"解释为何判定冲突"}；
  - 如果信息不足无法判断取舍，则保留旧值并降低该维度 confidence 0.15。

## 流程 3：填充证据（evidence）与置信度（confidence）
- 为每个维度字段附上证据：evidence["字段路径"] = list of {turn:对话轮次序号, role:"user/assistant", snippet:"原文片段（不超过60字）", confidence:0.0~1.0}
  例：evidence["cognitive_style"] = [{"turn":8,"role":"user","snippet":"我更喜欢看视频学和写代码","confidence":0.85}]
- 每维度 confidence = 有证据支持吗？证据清晰且互相印证吗？（0~1）
  没有证据 → 0.0；只有一条模糊证据 → 0.4；多条印证 → 0.8+；出现冲突未完全解决 → 0.5 以下

## 流程 4：完备率（completeness）计算
每维度完备率 0.0~1.0：
  knowledge_base：三列表（mastered/weak/untouched）合计 ≥ 6 条 → 1.0，按实际条数/6 线性
  cognitive_style：非空且有证据 → 1.0，否则 0
  preferred_pace ：非空 → 1.0，否则 0
  error_prone_areas：≥ 2 条 → 1.0，条数/2 线性
  interests        ：≥ 2 条 → 1.0，条数/2 线性
  learning_goals   ：short_term 和 long_term 都非空 → 1.0，只有一个 → 0.5，都空 → 0
  goal_attribute   ：非空且属于 应试/就业/考研/自学兴趣 之一 → 1.0，否则 0
  daily_available_hours：> 0 → 1.0，否则 0
  overall          ：8 个维度的算术平均（不要取 max）

## 流程 5：输出标准 JSON
只输出一个 JSON 对象（包裹在 ```json 块中也可），严格结构：
{
  "profile": {  // 与 StudentProfile schema 完全一致的 8 个维度字段 + base info
     // student_id/name/grade/major 从基础信息原文搬入；其余维度从流程1得出
  },
  "confidence": {  // 8 个维度 0~1
     "knowledge_base":.., "cognitive_style":.., "preferred_pace":..,
     "error_prone_areas":.., "interests":.., "learning_goals":..,
     "goal_attribute":.., "daily_available_hours":..
  },
  "completeness": { // 流程 4 计算结果 + overall
     "knowledge_base":.., "cognitive_style":.., "preferred_pace":..,
     "error_prone_areas":.., "interests":.., "learning_goals":..,
     "goal_attribute":.., "daily_available_hours":..,
     "overall": 0.0~1.0
  },
  "evidence": { /* 流程 3 结果 */ },
  "conflicts": [ /* 流程 2 登记的冲突列表，如无冲突则空数组 [] */ ],
  "reasoning_notes": [ /* 简要文字说明每条关键决策的理由，比如"cognitive_style=视觉型，来自 turn 8 用户原话我看视频学更快" */ ]
}

约束：
- 不编造；信息不足用空/[]/0.0。
- JSON 必须合法，所有字段名/结构与上面严格一致。
- reasoning_notes 每条不超过 60 字，总条数 ≤ 8。
'''

# 旧的画像更新 Prompt（已废弃，使用 PROFILE_EXTRACTION_SYSTEM_PROMPT 统一做增量抽取）
_UNSUPPORTED_LEGACY_UPDATE_PROMPT = "已废弃，改用 PROFILE_EXTRACTION_SYSTEM_PROMPT 统一做增量抽取"

# 维度名称映射（用于雷达图）
DIM_LABELS = {
    "knowledge_base": "知识基础水平",
    "cognitive_style": "认知学习风格",
    "pace_preference": "学习节奏偏好",
    "error_prone": "高频易错短板",
    "interest_direction": "个人兴趣方向",
    "goal_attribute": "学习目标属性",
    "daily_hours": "每日投入时长",
}


class ProfileManager:
    """
    学生画像管理器
    当前使用文件存储（开发/演示用），可扩展为数据库
    """

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self._storage_dir = Path(storage_dir)
        else:
            self._storage_dir = Path(__file__).parent.parent.parent / "data" / "profiles"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        # 内存缓存
        self._cache: dict[str, StudentProfile] = {}

    def _profile_path(self, student_id: str) -> Path:
        return self._storage_dir / f"{student_id}.json"

    def get_profile(self, student_id: str) -> StudentProfile:
        """获取学生画像（缓存中有则返回，无则从文件加载或创建默认）"""
        if student_id in self._cache:
            return self._cache[student_id]

        path = self._profile_path(student_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                profile = StudentProfile(**data)
                self._cache[student_id] = profile
                return profile
            except Exception as e:
                logger.warning(f"加载画像失败 {student_id}: {e}")

        # 创建默认画像
        profile = StudentProfile(student_id=student_id)
        self._cache[student_id] = profile
        return profile

    def save_profile(self, profile: StudentProfile):
        """保存画像到文件并更新缓存"""
        path = self._profile_path(profile.student_id)
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        self._cache[profile.student_id] = profile
        logger.info(f"画像已保存: {profile.student_id}")

    def reset_profile(self, student_id: str) -> StudentProfile:
        """重置画像（用于新对话开始）"""
        self.delete_profile(student_id)
        profile = StudentProfile(student_id=student_id)
        self._cache[student_id] = profile
        return profile

    def update_profile(self, profile: StudentProfile, updates: dict) -> StudentProfile:
        """增量更新画像（只在当前值非空时合并，不保留旧测试数据）"""
        for key, value in updates.items():
            if not hasattr(profile, key) or not value:
                continue

            current = getattr(profile, key)

            if isinstance(value, list) and isinstance(current, list):
                setattr(profile, key, value)
            elif isinstance(value, dict) and isinstance(current, dict):
                for k, v in value.items():
                    if v:
                        current[k] = v
                setattr(profile, key, current)
            else:
                setattr(profile, key, value)
        profile.updated_at = datetime.now().isoformat()
        self.save_profile(profile)
        return profile

    def incremental_update(self, student_id: str, updates: dict) -> StudentProfile:
        """
        增量更新画像（局部修改单个/多个维度）。
        用于学习路径打卡、学习进度变动等反向更新画像。
        支持只传需修改的字段，不影响其他字段。
        """
        profile = self.get_profile(student_id)
        changed = False
        for key, value in updates.items():
            if not hasattr(profile, key):
                continue
            current = getattr(profile, key)
            if isinstance(value, list) and isinstance(current, list):
                if value is not None:
                    setattr(profile, key, value)
                    changed = True
            elif isinstance(value, dict) and isinstance(current, dict):
                merged = False
                for k, v in value.items():
                    if v is not None:
                        current[k] = v
                        merged = True
                if merged:
                    setattr(profile, key, current)
                    changed = True
            else:
                if value is not None:
                    setattr(profile, key, value)
                    changed = True

        if changed:
            profile.version += 1
            profile.updated_at = datetime.now().isoformat()
            self.save_profile(profile)
            logger.info(f"[ProfileManager] 增量更新成功: student_id={student_id}, keys={list(updates.keys())}")

        return profile

    def extract_radar_scores(self, student_id: str) -> RadarScores:
        """
        提取6个维度转为0~10量化数值，供给前端雷达图绘图
        评分规则基于画像数据丰度与质量
        """
        profile = self.get_profile(student_id)
        dimensions = []

        # 1. 知识基础水平 (0-10)
        kb = profile.knowledge_base
        mastered_count = len(kb.get("mastered", []))
        weak_count = len(kb.get("weak", []))
        untouched_count = len(kb.get("untouched", []))
        total_knowledge = mastered_count + weak_count + untouched_count
        if total_knowledge > 0:
            knowledge_score = min(10, round((mastered_count / max(total_knowledge, 1)) * 5
                                            + (1 - weak_count / max(total_knowledge, 1)) * 3
                                            + min(total_knowledge, 5) * 0.4, 1))
        else:
            knowledge_score = 0.0
        dimensions.append(RadarDimension(
            name="知识基础水平",
            score=max(0, min(10, knowledge_score)),
            description=f"已掌握{mastered_count}个 / 薄弱{weak_count}个 / 未接触{untouched_count}个知识点"
        ))

        # 2. 认知学习风格 (0-10)
        style_score = 0.0
        if profile.cognitive_style:
            style_keywords = {"视觉型": 7, "读写型": 6, "听觉型": 5, "动觉型": 6, "视觉": 7, "读写": 6, "听觉": 5, "实操": 6}
            for kw, s in style_keywords.items():
                if kw in profile.cognitive_style:
                    style_score = s
                    break
        dimensions.append(RadarDimension(
            name="认知学习风格",
            score=style_score,
            description=profile.cognitive_style or "未识别，建议继续观察"
        ))

        # 3. 高频易错短板 (0-10 反向: 分值越高说明发现越明确)
        error_count = len(profile.error_prone_areas)
        error_score = min(10, error_count * 2 + 2) if error_count > 0 else 0.0
        dimensions.append(RadarDimension(
            name="高频易错短板",
            score=error_score,
            description=", ".join(profile.error_prone_areas[:3]) if profile.error_prone_areas else "暂未发现明确短板"
        ))

        # 4. 个人兴趣与应用偏好 (0-10)
        interest_count = len(profile.interests)
        interest_score = min(10, interest_count * 1.5 + 3) if interest_count > 0 else 0.0
        dimensions.append(RadarDimension(
            name="个人兴趣方向",
            score=interest_score,
            description=", ".join(profile.interests[:3]) if profile.interests else "暂未收集"
        ))

        # 6. 学习目标 (0-10)
        goals = profile.learning_goals or {}
        goal_score = 0.0
        if goals.get("short_term") or goals.get("long_term"):
            goal_score = 6.0
            if goals.get("short_term") and goals.get("long_term"):
                goal_score = 8.0
        dimensions.append(RadarDimension(
            name="学习目标",
            score=goal_score,
            description=f"短期: {goals.get('short_term', '未设置')[:20] or '未设置'} | 长期: {goals.get('long_term', '未设置')[:20] or '未设置'}"
        ))

        # 7. 目标属性 (0-10)
        ga_map = {"就业": 9, "考研": 8, "应试": 7, "考证": 7, "兴趣": 5, "自学": 5}
        ga_score = 0.0
        ga_desc = profile.goal_attribute or ""
        if ga_desc:
            ga_score = 6.0
            for kw, s in ga_map.items():
                if kw in ga_desc:
                    ga_score = s
                    break
        dimensions.append(RadarDimension(
            name="目标属性",
            score=ga_score,
            description=ga_desc or "未明确"
        ))

        return RadarScores(dimensions=dimensions)

    def delete_profile(self, student_id: str):
        """删除学生画像"""
        self._cache.pop(student_id, None)
        path = self._profile_path(student_id)
        if path.exists():
            path.unlink()
            logger.info(f"画像已删除: {student_id}")

    def list_all(self) -> list[str]:
        """列出所有学生ID"""
        return [p.stem for p in self._storage_dir.glob("*.json")]


# 全局画像管理器
profile_manager = ProfileManager()
