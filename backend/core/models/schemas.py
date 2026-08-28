"""
数据模型定义
包含所有 API 请求/响应的 Pydantic 模型
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ======================== 雷达图维度分值子模型 ========================

class RadarDimension(BaseModel):
    """雷达图单个维度分值"""
    name: str = Field(..., description="维度名称")
    score: float = Field(..., ge=0, le=10, description="0~10 量化分值")
    description: str = Field(default="", description="维度解读说明")


class RadarScores(BaseModel):
    """雷达图 6 维度分值集合"""
    dimensions: list[RadarDimension] = Field(default_factory=list, description="各维度分值")
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ======================== 完整学生画像（6+维度）========================

class StudentProfile(BaseModel):
    """学生画像（6+ 维度），无缝兼容 LearningPathAgent"""
    student_id: str = Field(default="", description="学生唯一主键")
    name: str = Field(default="", description="学生姓名")

    # ---- 维度1: 知识基础水平 ----
    knowledge_base: dict = Field(
        default_factory=lambda: {"mastered": [], "weak": [], "untouched": []},
        description="知识基础：已掌握/薄弱/未接触知识点列表",
    )

    # ---- 维度2: 认知学习风格 ----
    cognitive_style: str = Field(
        default="", description="认知风格：视觉型/听觉型/读写型/动觉型"
    )

    # ---- 维度3: 学习节奏偏好 ----
    preferred_pace: str = Field(
        default="", description="学习节奏偏好：慢速细学/适中/快速速成"
    )

    # ---- 维度4: 高频易错短板与思维误区 ----
    error_prone_areas: list[str] = Field(
        default_factory=list, description="易错点/常错题型/思维误区"
    )

    # ---- 维度5: 个人兴趣与应用偏好 ----
    interests: list[str] = Field(
        default_factory=list, description="兴趣领域/偏好话题/应用方向"
    )

    # ---- 维度6: 学习目标属性 ----
    learning_goals: dict = Field(
        default_factory=lambda: {"short_term": "", "long_term": ""},
        description="学习目标：短期目标/长期目标/目标属性(应试/就业/考研/自学兴趣)",
    )
    goal_attribute: str = Field(
        default="", description="学习目标属性：应试/就业/考研/自学兴趣"
    )

    # ---- 扩展维度7: 每日可投入学习时长 ----
    daily_available_hours: float = Field(
        default=0, ge=0, le=24, description="每日可投入学习时长(小时)"
    )

    # ---- 年级专业基础信息 ----
    grade: str = Field(default="", description="年级")
    major: str = Field(default="", description="专业")

    # ---- 学习历史 ----
    learning_history: list[dict] = Field(
        default_factory=list, description="学习历史记录"
    )

    # ---- 画像抽取证据：每个维度后附证据引用（来自哪轮对话、原文片段） ----
    evidence: dict = Field(
        default_factory=dict,
        description="每个维度字段的值来自哪条对话证据，key=字段路径（如 knowledge_base.weak.0），value=list[{turn:int, role:user|assistant, snippet:str, confidence:float}]",
    )

    # ---- 画像置信度：每个维度 0~1 置信度（由抽取器判断） ----
    confidence: dict = Field(
        default_factory=lambda: {
            "knowledge_base": 0.0, "cognitive_style": 0.0, "preferred_pace": 0.0,
            "error_prone_areas": 0.0, "interests": 0.0, "learning_goals": 0.0,
            "goal_attribute": 0.0, "daily_available_hours": 0.0,
        },
        description="各维度抽取置信度 0~1：key=维度名 value=0.0~1.0",
    )

    # ---- 画像完备率：每个维度 0~1 信息填充度（供对话 Agent 指导补哪个维度） ----
    completeness: dict = Field(
        default_factory=lambda: {
            "knowledge_base": 0.0, "cognitive_style": 0.0, "preferred_pace": 0.0,
            "error_prone_areas": 0.0, "interests": 0.0, "learning_goals": 0.0,
            "goal_attribute": 0.0, "daily_available_hours": 0.0,
            "overall": 0.0,
        },
        description="各维度信息完备率 0~1：key=维度名 value=0.0~1.0；含 overall 总完备率",
    )

    # ---- 画像元信息 ----
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source: str = Field(
        default="chat", description="画像来源: chat(对话构建)/manual(手动)/import(导入)"
    )
    version: int = Field(default=1, description="画像版本号")

    class Config:
        json_schema_extra = {
            "example": {
                "student_id": "stu_001",
                "name": "张三",
                "grade": "大二",
                "major": "计算机科学与技术",
                "knowledge_base": {
                    "mastered": ["Python基础语法", "变量与数据类型"],
                    "weak": ["面向对象编程", "异常处理"],
                    "untouched": ["装饰器", "生成器"],
                },
                "cognitive_style": "视觉型",
                "error_prone_areas": ["循环边界条件", "类继承关系"],
                "learning_goals": {
                    "short_term": "掌握Python面向对象编程",
                    "long_term": "成为全栈开发者",
                },
                "goal_attribute": "就业",
                "preferred_pace": "适中",
                "interests": ["Web开发", "数据分析"],
                "daily_available_hours": 2.5,
            }
        }


# ======================== 对话消息 ========================

class Message(BaseModel):
    """单条对话消息"""
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """对话请求"""
    student_id: str = Field(default="anonymous", description="学生ID")
    messages: list[Message] = Field(..., min_length=1, description="对话历史")
    stream: bool = Field(default=True, description="是否流式输出")


# ======================== 画像对话会话结构体 ========================

class ProfileChatInitRequest(BaseModel):
    """画像对话初始化请求"""
    student_id: str = Field(..., description="学生唯一标识")
    name: str = Field(default="", description="学生姓名")
    grade: str = Field(default="", description="年级")
    major: str = Field(default="", description="专业")


class ProfileChatInitResponse(BaseModel):
    """画像对话初始化响应"""
    session_id: str = Field(..., description="会话ID")
    student_id: str = Field(..., description="学生唯一标识")
    is_new: bool = Field(default=True, description="是否新建会话")
    first_question: str = Field(..., description="AI首轮提问")
    base_info: dict = Field(default_factory=dict, description="基础信息")


class ProfileChatSendRequest(BaseModel):
    """画像对话发送消息请求"""
    student_id: str = Field(..., description="学生唯一标识")
    session_id: str = Field(..., description="会话ID")
    message: str = Field(..., min_length=1, description="学生回复内容")


class ProfileChatSendResponse(BaseModel):
    """画像对话发送消息响应"""
    session_id: str = Field(..., description="会话ID")
    reply: str = Field(..., description="AI回复内容")
    is_completed: bool = Field(default=False, description="是否已完成画像采集")
    profile: Optional[StudentProfile] = Field(default=None, description="完成时返回完整画像")
    radar_scores: Optional[RadarScores] = Field(default=None, description="完成时返回雷达图分值")


class ProfileIncrementUpdateRequest(BaseModel):
    """增量更新画像请求（学习路径模块联动用）"""
    student_id: str = Field(..., description="学生唯一标识")
    updates: dict = Field(..., description="需更新的字段，支持部分更新")


class ProfileChatProgress(BaseModel):
    """画像对话采集进度"""
    stage: str = Field(..., description="当前采集阶段")
    current_dim: Optional[str] = Field(default=None, description="当前正在采集的维度")
    dims_done: list[str] = Field(default_factory=list, description="已完成的维度列表")
    total_dims: int = Field(default=6, description="总维度数")
    progress_percent: int = Field(default=0, ge=0, le=100, description="进度百分比")
    asked_count: int = Field(default=0, description="已提问次数")


# ======================== 资源生成 ========================

class ResourceRequest(BaseModel):
    """资源生成请求"""
    student_id: str
    resource_type: str = Field(
        ..., pattern="^(lecture|mindmap|exercise|reading|code)$",
        description="资源类型：lecture(讲解)/mindmap(导图)/exercise(练习)/reading(阅读)/code(代码)"
    )
    topic: str = Field(..., description="知识点/主题")
    course: str = Field(default="", description="所属课程")
    additional_info: str = Field(default="", description="补充说明/需求")
    user_demand: str = Field(default="", description="用户自定义需求（长文本，作为最高优先级约束）")
    temp_file_id: Optional[str] = Field(default=None, description="用户上传的临时知识库文档ID")


class ResourceResponse(BaseModel):
    """资源生成响应"""
    task_id: str
    resource_type: str
    status: str = Field(default="generating", pattern="^(generating|completed|failed)$")
    content: Optional[str] = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error: Optional[str] = None


# ======================== 学习路径 ========================

class LearningNode(BaseModel):
    """学习路径中的单个节点"""
    node_id: str
    title: str
    description: str
    resource_type: str
    estimated_duration: str = Field(default="30分钟")
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed)$")
    reason: str = Field(default="", description="推荐该节点的原因分析")
    resource_types: list[str] = Field(default_factory=list, description="推荐的资源类型列表")


class LearningPath(BaseModel):
    """个性化学习路径"""
    student_id: str
    path_name: str = Field(default="默认学习路径")
    nodes: list[LearningNode] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ======================== 通用 ========================

class ErrorResponse(BaseModel):
    """统一错误响应"""
    error_code: int
    error_msg: str
    detail: Optional[str] = None


# ======================== SQL 建表语句 ========================

PROFILE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS student_profiles (
    student_id VARCHAR(64) PRIMARY KEY,
    profile_data JSON NOT NULL,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student_id (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

PROFILE_CHAT_LOG_SQL = """
CREATE TABLE IF NOT EXISTS profile_chat_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL COMMENT 'user/assistant',
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (student_id, session_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

PROFILE_VERSION_SNAPSHOT_SQL = """
CREATE TABLE IF NOT EXISTS profile_version_snapshots (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(64) NOT NULL,
    version INT NOT NULL,
    snapshot_data JSON NOT NULL,
    source VARCHAR(32) DEFAULT 'chat' COMMENT '画像来源',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    UNIQUE KEY uk_student_version (student_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


# ======================== 联网学习路径 & 练习卡 & 技能差距 ========================

class WebPathStartRequest(BaseModel):
    """交互式联网路径 Stage 1 / Stage 3 发起"""
    student_id: str
    topic: str
    collected: Optional[dict] = None      # 已有信息（画像 + 已回答的问题）
    daily_hours: Optional[float] = None
    cycle: Optional[str] = None
    target: Optional[str] = None


class WebPathAnswersRequest(BaseModel):
    """交互式联网路径 Stage 2：用户补全信息"""
    student_id: str
    topic: str
    collected: Optional[dict] = None       # 之前攒的信息
    answers: dict = Field(default_factory=dict, description="用户对问题的回答，key=missing_key value=回答")


class WebPathConfirmRequest(BaseModel):
    """路径草案确认 / 修改"""
    student_id: str
    draft_id: str
    feedback: Optional[str] = None        # 留空=确认；非空=修改意见


class DraftStreamRequest(BaseModel):
    """流式路径草案生成（SSE）：draft_id 非空表示按意见重新生成"""
    student_id: str
    topic: str
    collected: dict = Field(default_factory=dict)
    draft_id: str = ""


class DraftResourceRequest(BaseModel):
    """向导草案阶段：给某个节点加一条学习资源（根据规划选 B站/文档链接）"""
    student_id: str
    draft_id: str
    node_id: str
    title: str
    url: str
    platform: str = ""


class PracticeDeepSearchRequest(BaseModel):
    """用户选「深入练习」时：按知识点搜官方 OJ 练习卡"""
    student_id: str
    node_id: str
    topic: Optional[str] = None
    knowledge_point: Optional[str] = None
    platforms: Optional[list[str]] = None
    count: Optional[int] = None
    max_results: Optional[int] = None


class PracticeCardUpdate(BaseModel):
    """更新练习卡状态/答案/笔记"""
    student_id: str
    card_id: str
    fields: dict = Field(default_factory=dict, description="可含 status/my_answer/note")


class PracticeCheckinRequest(BaseModel):
    """练习打卡"""
    student_id: str
    node_id: str
    note: Optional[str] = None


class SaveAiExercisesRequest(BaseModel):
    """聊天 AI 出题作答落库（与 /exercise/summarize 的 payload 一致，JSON string）"""
    student_id: str
    topic: str = ""
    exercises: str = ""     # JSON string: [{id,type,question,options,answer,explanation,difficulty}]
    answers: str = ""       # JSON string: {ex_id: {id,userAnswer,correct,type}}


class RedoAiExerciseRequest(BaseModel):
    """错题重做：AI 题重新作答"""
    student_id: str
    exercise_id: str
    user_answer: str = ""


class WrongRemoveRequest(BaseModel):
    """错题集移除：AI 错题删记录 / OJ 错题置为 done 移出错题集"""
    student_id: str
    kind: str = "ai"          # ai | oj
    target_id: str = ""       # AI: exercise_id；OJ: card_id


class CreateCollectionRequest(BaseModel):
    """新建命名题目集（我的题目）"""
    student_id: str
    name: str


class AddToCollectionRequest(BaseModel):
    """收藏一题到题目集"""
    student_id: str
    collection_id: str
    topic: str = ""
    exercise: dict = Field(default_factory=dict)


class RedoCollectionQuestionRequest(BaseModel):
    """题目集内重做"""
    student_id: str
    collection_id: str
    question_id: str
    user_answer: str = ""


class RemoveCollectionQuestionRequest(BaseModel):
    """从题目集移除一题"""
    student_id: str
    collection_id: str
    question_id: str


class DeleteCollectionRequest(BaseModel):
    """删除整个题目集"""
    student_id: str
    collection_id: str


class DeleteNoteRequest(BaseModel):
    """删除一条笔记"""
    student_id: str
    note_id: str
    """删除一条笔记"""
    student_id: str
    note_id: str


class NodeStudyRequest(BaseModel):
    """外部平台学习自评打卡"""
    student_id: str
    node_id: str
    platform: str = "其他"
    hours: float = 0
    problems: int = 0
    mastery: int = 0
    note: str = ""


class NodeResourceAddRequest(BaseModel):
    """给路径节点添加一条学习资源（如 B站课程链接）"""
    student_id: str
    node_id: str
    title: str
    url: str
    platform: str = ""


class NodeResourceDeleteRequest(BaseModel):
    """删除一条节点学习资源"""
    student_id: str
    rid: str


class NodeResourceWatchRequest(BaseModel):
    """标记某条资源「看完了」+ 自评"""
    student_id: str
    rid: str
    watch_note: str = ""


class NodeSkipRequest(BaseModel):
    """用户「这个知识点我会了」→ 跳过该节点"""
    student_id: str
    node_id: str


class DailyExerciseRequest(BaseModel):
    """今日练习：按节点/知识点出题"""
    student_id: str
    node_id: str = ""
    count: int = 3
    task_day: int | None = None


class VideoSearchRequest(BaseModel):
    """搜索 B站热门视频（按播放量/点赞排序）"""
    keyword: str
    page: int = 1


class TaskToggleRequest(BaseModel):
    """逐小任务打√（可逆）：标记/取消某节点的某一天任务完成"""
    student_id: str
    node_id: str
    day: int


class DailyLogAddRequest(BaseModel):
    """日计划：用户记录今天学了什么（自由添加）"""
    student_id: str
    node_id: str
    content: str
    date: Optional[str] = None   # 默认当天


class DailyLogUpdateRequest(BaseModel):
    """日计划：编辑某条记录内容 / 打钩"""
    student_id: str
    log_id: str
    content: Optional[str] = None
    done: Optional[bool] = None


class DailyLogDeleteRequest(BaseModel):
    """日计划：删除一条记录"""
    student_id: str
    log_id: str


class SkillGapRequest(BaseModel):
    """技能 vs 市场需求差距分析"""
    student_id: str
    role: Optional[str] = "后端开发工程师"
    language: Optional[str] = "zh-CN"
    top_k: Optional[int] = 6
