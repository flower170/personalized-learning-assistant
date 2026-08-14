<template>
  <div class="practice-view">
    <!-- 头部 -->
    <div class="prv-header">
      <div class="prv-title-row">
        <h2><el-icon><Notebook /></el-icon> 我的练习</h2>
        <div class="prv-actions">
          <el-button size="small" @click="refresh">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
          <el-button size="small" @click="$router.push('/')">
            <el-icon><Back /></el-icon> 返回聊天
          </el-button>
        </div>
      </div>
      <p class="prv-sub">把学过的知识点，去官方 OJ 刷题巩固。记录进度、打卡、见证连续学习天数。</p>
    </div>

    <div v-loading="pathLoading" class="prv-body">
      <!-- 空状态：无已确认路径 -->
      <div v-if="!pathLoading && !path" class="prv-empty">
        <el-icon :size="56" color="#c7d2fe"><Notebook /></el-icon>
        <h3>还没有学习路径</h3>
        <p>去聊天里发起「学习路径规划」，确认一份专属学习路径后，就能在这里刷题打卡了</p>
        <el-button type="primary" @click="$router.push('/')">去发起路径规划</el-button>
      </div>

      <template v-else-if="path">
        <!-- ═══════ 顶部：已确认的学习路径 ═══════ -->
        <div class="prv-card">
          <div class="prv-card-head">
            <div>
              <div class="prv-path-name">{{ path.path_name || '学习路径' }}</div>
              <div v-if="path.goal" class="prv-path-goal">{{ path.goal }}</div>
            </div>
            <el-tag :type="pathProgressTag" effect="light">{{ pathStatusText }}</el-tag>
          </div>

          <!-- 路径进度条 -->
          <div class="prv-path-progress" v-if="pathProgress">
            <el-progress
              :percentage="pathProgress.progress_percent || 0"
              :stroke-width="10"
              :color="pathBarColor"
            />
            <span class="prv-path-progress-text">
              已完成 {{ pathProgress.completed_tasks }}/{{ pathProgress.total_tasks }} 个学习任务 ·
              已过 {{ pathProgress.elapsed_days }}/{{ pathProgress.total_days }} 天
              <span v-if="pathProgress.remaining_tasks > 0">· 还剩 {{ pathProgress.remaining_tasks }} 个任务</span>
            </span>
          </div>

          <!-- 阶段（宏观：月计划） -->
          <div v-if="path.stages?.length" class="prv-stages">
            <div class="prv-sec-label">阶段计划</div>
            <div class="prv-stage-list">
              <div v-for="(st, i) in path.stages" :key="st.stage || i" class="prv-stage">
                <div class="prv-stage-line">
                  <span class="prv-stage-dot">{{ st.stage || i + 1 }}</span>
                  <span v-if="i < path.stages.length - 1" class="prv-stage-conn"></span>
                </div>
                <div class="prv-stage-body">
                  <div class="prv-stage-title">{{ st.title }}</div>
                  <div v-if="st.description" class="prv-stage-desc">{{ st.description }}</div>
                  <div v-if="st.focus_points?.length" class="prv-tags">
                    <el-tag v-for="f in st.focus_points" :key="f" size="small" effect="plain">{{ f }}</el-tag>
                  </div>
                  <div v-if="st.practice_cards?.length" class="prv-stage-cards">
                    <a
                      v-for="c in st.practice_cards"
                      :key="c.card_id"
                      :href="c.link"
                      target="_blank"
                      rel="noopener"
                      class="prv-stage-card-link"
                    >
                      {{ c.platform }} · {{ c.title || c.knowledge_point }}
                    </a>
                  </div>
                  <span v-if="st.estimated_days" class="prv-stage-days">约 {{ st.estimated_days }} 天</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 节点（微观：日计划）+ 练习卡 -->
          <div v-if="path.nodes?.length" class="prv-nodes">
            <div class="prv-sec-label">日计划 &amp; 练习</div>
            <div v-for="node in path.nodes" :key="node.node_id" class="prv-node">
              <div class="prv-node-head">
                <div class="prv-node-title">
                  <span class="prv-node-badge">{{ node.node_id }}</span>
                  {{ node.title }}
                </div>
                <span v-if="node.estimated_days" class="prv-node-days">{{ node.estimated_days }} 天</span>
              </div>
              <div v-if="node.description" class="prv-node-desc">{{ node.description }}</div>

              <!-- 日任务 -->
              <div v-if="node.daily_tasks?.length" class="prv-tasks">
                <el-tooltip
                  v-for="task in node.daily_tasks.slice(0, 4)"
                  :key="task.day"
                  :content="`第${task.day}天：${task.title}${task.completed ? ' ✓ 已完成' : ''}`"
                  placement="top"
                >
                  <span class="prv-task-chip" :class="{ done: task.completed }">
                    D{{ task.day }}
                  </span>
                </el-tooltip>
                <span v-if="node.daily_tasks.length > 4" class="prv-task-more">
                  +{{ node.daily_tasks.length - 4 }}
                </span>
              </div>

              <!-- 练习卡（按节点） -->
              <div class="prv-node-cards">
                <PracticeCardList
                  :student-id="chatStore.userId"
                  :node-id="node.node_id"
                  :cards="node.practice_cards || []"
                  :loading="node._loading"
                  :can-search="isProgramming"
                  @find="findCards(node)"
                  @updated="refresh"
                />
              </div>

              <!-- 外部平台学习（自评，呼应路径进度） -->
              <div class="prv-node-study">
                <div v-if="node.node_study" class="prv-node-study-summary">
                  <span>{{ node.node_study.platform || '外部平台' }}</span>
                  <span>累计 {{ node.node_study.total_hours }}h</span>
                  <span>{{ node.node_study.total_problems }} 题</span>
                  <span class="prv-mastery">{{ masteryStars(node.node_study.mastery) }}</span>
                  <span v-if="node.node_study.latest_note" class="prv-node-study-note">· {{ node.node_study.latest_note }}</span>
                </div>
                <el-button size="small" plain class="prv-node-study-btn" @click="openStudyDialog(node)">
                  ✍️ 外部学习打卡
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══════ 我的题目：命名题目集（收藏 AI 出的题） ═══════ -->
        <div class="prv-card prv-collections">
          <div class="prv-collections-head">
            <div class="prv-collections-title">📂 我的题目 <span class="prv-stat-mini">({{ collectionTotal }} 题)</span></div>
            <el-button size="small" type="primary" plain @click="openCreateCol">
              <el-icon><Plus /></el-icon> 新建题目集
            </el-button>
          </div>

          <div v-if="!collections.length" class="prv-empty-small prv-collections-empty">
            在聊天答题时点「📥 加入错题集」，把题目收进你的题目集，随时回来重做巩固。
          </div>

          <div v-for="col in collections" :key="col.collection_id" class="prv-col">
            <div
              class="prv-col-head"
              :class="{ active: expandedCol === col.collection_id }"
              @click="expandedCol = expandedCol === col.collection_id ? '' : col.collection_id"
            >
              <div class="prv-col-title">
                <span class="prv-col-arrow">{{ expandedCol === col.collection_id ? '▾' : '▸' }}</span>
                <span class="prv-col-name">📁 {{ col.name }}</span>
                <span class="prv-col-count">{{ col.questions.length }} 题</span>
                <span
                  v-for="t in colTypeBadges(col)"
                  :key="t.label"
                  class="prv-col-type-chip"
                  :style="{ background: t.color }"
                >{{ t.label }}</span>
              </div>
              <el-dropdown trigger="click" @command="cmd => onColCommand(cmd, col)" @click.stop>
                <el-button size="small" text type="primary" @click.stop>
                  <el-icon><MoreFilled /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="delete">🗑️ 删除题目集</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>

            <div v-if="expandedCol === col.collection_id" class="prv-col-body">
              <div v-if="!col.questions.length" class="prv-empty-small">
                这个题目集还是空的，去聊天答题时点「加入错题集」收题吧。
              </div>
              <div v-for="q in col.questions" :key="q.qid" class="prv-col-q">
                <ExerciseCard
                  :exercise="colQToCard(q)"
                  :current-index="0"
                  :total-exercises="1"
                  standalone
                  @answer="e => onRedoCol(col, q, e)"
                />
                <div class="prv-col-q-ops">
                  <el-button size="small" text type="danger" @click="onRemoveQ(col, q)">移除</el-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══════ 中部：进度追踪 + 激励 ═══════ -->
        <div class="prv-grid">
          <!-- 统计卡片 -->
          <div class="prv-card prv-stats">
            <div class="prv-sec-label">进度追踪</div>
            <div class="prv-stats-row">
              <div class="prv-stat">
                <el-progress
                  type="circle"
                  :percentage="progress?.progress_percent || 0"
                  :width="92"
                  :color="'#6366f1'"
                >
                  <template #default>
                    <div class="prv-stat-big">{{ progress?.progress_percent || 0 }}%</div>
                  </template>
                </el-progress>
                <div class="prv-stat-label">练习完成</div>
                <div class="prv-stat-sub">{{ progress?.done || 0 }}/{{ progress?.total_cards || 0 }} 题</div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num" :class="{ warn: (progress?.total_accuracy_percent || 0) < 60 }">
                  {{ progress?.total_accuracy_percent || 0 }}%
                </div>
                <div class="prv-stat-label">正确率 <span class="prv-stat-mini">OJ+AI</span></div>
                <div class="prv-stat-sub">
                  {{ progress?.total_correct || 0 }} 对 / {{ progress?.total_answered || 0 }} 答
                </div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num hot">🔥 {{ progress?.streak?.current || 0 }}</div>
                <div class="prv-stat-label">连续打卡</div>
                <div class="prv-stat-sub">最长 {{ progress?.streak?.longest || 0 }} 天</div>
              </div>
              <div class="prv-stat">
                <div class="prv-stat-num">{{ progress?.total_checkins || 0 }}</div>
                <div class="prv-stat-label">累计打卡</div>
                <div class="prv-stat-sub">今天要打卡吗？</div>
              </div>
            </div>
            <div class="prv-checkin-row">
              <el-button type="primary" round :disabled="checkedToday" @click="openCheckin">
                <el-icon><Calendar /></el-icon>
                {{ checkedToday ? '今日已打卡 ✓' : '今日打卡' }}
              </el-button>
              <el-button v-if="wrongTotal > 0" round type="warning" plain @click="scrollToWrong">
                <el-icon><Warning /></el-icon> {{ wrongTotal }} 道错题待回顾
              </el-button>
            </div>
            <!-- AI 出题练习统计（任何科目都有效，非编程科目 OJ 卡被清零但 AI 统计存活） -->
            <div v-if="(progress?.ai_total || 0) > 0" class="prv-ai-bar">
              🧠 AI 练习：共 {{ progress.ai_total }} 题 · 对 {{ progress.ai_correct }} · 错 {{ progress.ai_wrong }} · 正确率 {{ progress.ai_accuracy_percent }}%
            </div>
          </div>

          <!-- 最近打卡 -->
          <div class="prv-card">
            <div class="prv-sec-label">打卡记录</div>
            <div v-if="progress?.checkins?.length" class="prv-checkin-list">
              <div v-for="c in recentCheckins" :key="c.date" class="prv-checkin-item">
                <span class="prv-checkin-date">{{ c.date }}</span>
                <span class="prv-checkin-node">{{ nodeTitle(c.node_id) }}</span>
                <span v-if="c.note" class="prv-checkin-note">{{ c.note }}</span>
              </div>
            </div>
            <div v-else class="prv-empty-small">还没有打卡记录，学完今天的内容就打个卡吧！</div>
          </div>
        </div>

        <!-- ═══════ 下部：练习回顾 ═══════ -->
        <div class="prv-grid">
          <!-- 错题集（OJ 错题 + AI 错题，全量不截断） -->
          <div class="prv-card">
            <div class="prv-sec-label">错题集</div>

            <!-- OJ 错题：跳官方平台重做 -->
            <div v-if="wrongOj.length" class="prv-sub-sec">
              <div class="prv-sub-label">OJ 错题 <span class="prv-stat-mini">({{ wrongOj.length }} 道)</span></div>
              <div class="prv-mistake-list">
                <div v-for="c in wrongOj" :key="c.card_id" class="prv-mistake-item" :id="'wrong-' + c.card_id">
                  <div class="prv-mistake-head">
                    <span class="pc-platform" :style="{ color: platformColor(c.platform) }">{{ c.platform }}</span>
                    <span v-if="c.problem_no" class="prv-mistake-no">{{ c.problem_no }}</span>
                    <a v-if="c.link" :href="c.link" target="_blank" rel="noopener" class="prv-mistake-link">重做 →</a>
                  </div>
                  <div class="prv-mistake-title">{{ c.title }}</div>
                  <div v-if="c.note" class="prv-mistake-note">{{ c.note }}</div>
                </div>
              </div>
            </div>

            <!-- AI 错题：页内重做（做对即移出错题集） -->
            <div v-if="wrongAi.length" class="prv-sub-sec">
              <div class="prv-sub-label">AI 错题 <span class="prv-stat-mini">({{ wrongAi.length }} 道，页内重做)</span></div>
              <div class="prv-ai-wrong-list">
                <div v-for="rec in wrongAi" :key="rec.exercise_id + '-' + rec.updated_at" class="prv-ai-wrong-item">
                  <div class="prv-ai-wrong-topic">{{ rec.topic || 'AI 练习' }}</div>
                  <ExerciseCard
                    :exercise="aiToCard(rec)"
                    :current-index="0"
                    :total-exercises="1"
                    standalone
                    @answer="(e) => onRedoAi(rec, e)"
                  />
                </div>
              </div>
            </div>

            <div v-if="!wrongOj.length && !wrongAi.length" class="prv-empty-small">太棒了，目前没有错题</div>
          </div>

          <!-- 最近练习记录 -->
          <div class="prv-card">
            <div class="prv-sec-label">最近练习</div>
            <div v-if="progress?.recent?.length" class="prv-recent-list">
              <div v-for="r in progress.recent.slice(0, 10)" :key="r.card_id" class="prv-recent-item">
                <span class="prv-recent-status" :class="'st-' + r.status">{{ statusText(r.status) }}</span>
                <span class="prv-recent-title">{{ r.title }}</span>
                <span class="prv-recent-time">{{ shortTime(r.updated_at) }}</span>
              </div>
            </div>
            <div v-else class="prv-empty-small">
              <template v-if="isProgramming">还没有练习记录，从上面任意节点的「去官方找题」开始吧！</template>
              <template v-else>该科目没有对应的官方 OJ 题库，直接用课本/真题练习并打卡即可。</template>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建题目集弹窗 -->
    <el-dialog v-model="createCollectionVisible" title="📁 新建题目集" width="380px" append-to-body>
      <el-input v-model="newColName" placeholder="题目集名称，如：SQL 错题" maxlength="30" @keyup.enter="onCreateCol" />
      <template #footer>
        <el-button @click="createCollectionVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newColName.trim()" :loading="savingCol" @click="onCreateCol">创建</el-button>
      </template>
    </el-dialog>

    <!-- 外部学习打卡弹窗 -->
    <el-dialog v-model="studyDialogVisible" title="✍️ 外部学习打卡" width="440px" append-to-body>
      <div class="prv-dialog-tip">在牛客/力扣等平台学完，回来填一下，让路径记录你的进度：</div>
      <el-form label-width="80px" class="prv-study-form">
        <el-form-item label="平台">
          <el-select v-model="studyForm.platform" style="width:100%">
            <el-option v-for="p in STUDY_PLATFORMS" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="学习时长">
          <el-input-number v-model="studyForm.hours" :min="0" :max="24" :step="0.5" />
          <span class="prv-form-unit">小时</span>
        </el-form-item>
        <el-form-item label="完成题数">
          <el-input-number v-model="studyForm.problems" :min="0" :max="500" :step="1" />
          <span class="prv-form-unit">题</span>
        </el-form-item>
        <el-form-item label="掌握度">
          <el-rate v-model="studyForm.mastery" :max="5" show-text />
        </el-form-item>
        <el-form-item label="心得">
          <el-input v-model="studyForm.note" type="textarea" :rows="2" placeholder="学到了什么？比如：掌握了前缀和…" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="studyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingStudy" @click="doNodeStudy">提交</el-button>
      </template>
    </el-dialog>

    <!-- 打卡弹窗 -->
    <el-dialog v-model="checkinVisible" title="🔥 今日打卡" width="420px" append-to-body>
      <div class="prv-dialog-tip">选择今天完成学习的节点（可留空），写一句学习心得吧</div>
      <el-select v-model="checkinNode" placeholder="选择节点（可选）" clearable style="width:100%;margin-bottom:10px">
        <el-option v-for="n in path?.nodes || []" :key="n.node_id" :label="n.title" :value="n.node_id" />
      </el-select>
      <el-input
        v-model="checkinNote"
        type="textarea"
        :rows="3"
        placeholder="今天学到了什么？比如：掌握了前缀和…"
      />
      <template #footer>
        <el-button @click="checkinVisible = false">取消</el-button>
        <el-button type="primary" :loading="checking" @click="doCheckin">确认打卡</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { ElMessage, ElMessageBox } from 'element-plus'
import PracticeCardList from '@/components/PracticeCardList.vue'
import ExerciseCard from '@/components/ExerciseCard.vue'
import { Notebook, Refresh, Back, Calendar, Warning, Plus, MoreFilled } from '@element-plus/icons-vue'
import { onlinePathApi, practiceApi } from '@/api'

const router = useRouter()
const chatStore = useChatStore()

const path = ref(null)
const progress = ref(null)
const pathLoading = ref(true)
const refreshing = ref(false)
// 是否编程/CS 科目——非编程科目（物理/化学等）隐藏「去官方找题」（牛客/LeetCode 上没有物理题）
const isProgramming = ref(true)
// 错题集（全量）：OJ 错题 + AI 错题（来自 GET /practice/wrong-questions，不截断）
const wrongOj = ref([])
const wrongAi = ref([])
// 我的题目（命名题目集）
const collections = ref([])
const expandedCol = ref('')
const createCollectionVisible = ref(false)
const newColName = ref('')
const savingCol = ref(false)
// 外部平台学习打卡
const STUDY_PLATFORMS = ['牛客网', 'LeetCode', '洛谷', '蓝桥杯', '中国大学MOOC', '课本', '真题', '其他']
const studyDialogVisible = ref(false)
const studyNode = ref(null)
const studyForm = ref({ platform: '牛客网', hours: 1, problems: 5, mastery: 3, note: '' })
const savingStudy = ref(false)

let pathProgress = ref(null)

const pathStatusText = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: '进度正常', behind: '进度落后', ahead: '进度超前' }[s] || ''
})
const pathProgressTag = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: 'success', behind: 'danger', ahead: 'warning' }[s] || 'info'
})
const pathBarColor = computed(() => {
  const s = pathProgress.value?.status
  return { on_track: '#10b981', behind: '#ef4444', ahead: '#f59e0b' }[s] || '#6366f1'
})

const checkedToday = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return progress.value?.checkins?.some(c => c.date === today) || false
})

const recentCheckins = computed(() => (progress.value?.checkins || []).slice(-8).reverse())

const wrongTotal = computed(() => wrongOj.value.length + wrongAi.value.length)

/** AI 错题记录 → ExerciseCard 所需的题目结构 */
function aiToCard(rec) {
  return {
    id: '复习',
    type: rec.type || 'choice',
    question: rec.question,
    options: rec.options || [],
    answer: rec.answer,
    explanation: rec.explanation,
    difficulty: rec.difficulty,
    topic: rec.topic,
  }
}

/** AI 错题重做：服务端判对错；做对移出错题集，做错保留可再试 */
async function onRedoAi(rec, e) {
  try {
    const res = await practiceApi.redoAiExercise(chatStore.userId, rec.exercise_id, e.userAnswer)
    if (res.ok) {
      if (res.correct) ElMessage.success('回答正确！已移出错题集')
      else ElMessage.warning('还是不对，看下解析想清楚后再试一次吧')
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`重做保存失败: ${err.message}`)
  }
}

// ==================== 我的题目（命名题目集） ====================

const collectionTotal = computed(() => collections.value.reduce((s, c) => s + (c.questions?.length || 0), 0))

/** 集合内题型汇总 chips（如：选择 3 / 填空 1） */
function colTypeBadges(col) {
  const count = {}
  for (const q of col.questions || []) {
    const label = { choice: '选择', fill: '填空', judge: '判断', essay: '简答', application: '应用' }[q.type] || q.type
    count[label] = (count[label] || 0) + 1
  }
  const colors = { 选择: '#6366f1', 填空: '#10b981', 判断: '#f59e0b', 简答: '#ec4899', 应用: '#8b5cf6' }
  return Object.entries(count).map(([label, n]) => ({ label: `${label} ${n}`, color: colors[label] || '#6b7280' }))
}

/** 集合内题目记录 → ExerciseCard 所需的题目结构 */
function colQToCard(q) {
  return {
    id: '收藏',
    type: q.type || 'choice',
    question: q.question,
    options: q.options || [],
    answer: q.answer,
    explanation: q.explanation,
    difficulty: q.difficulty,
    topic: q.topic,
  }
}

async function loadCollections() {
  try {
    const res = await practiceApi.listCollections(chatStore.userId)
    collections.value = res?.collections || []
  } catch (e) {
    console.error('加载题目集失败', e)
  }
}

function openCreateCol() {
  newColName.value = ''
  createCollectionVisible.value = true
}

async function onCreateCol() {
  const name = newColName.value.trim()
  if (!name) return
  savingCol.value = true
  try {
    const res = await practiceApi.createCollection(chatStore.userId, name)
    if (res.ok) {
      ElMessage.success('题目集已创建')
      createCollectionVisible.value = false
      newColName.value = ''
      await loadCollections()
    } else {
      ElMessage.warning(res.detail || '创建失败，可能已存在同名题目集')
    }
  } catch (e) {
    ElMessage.error('创建失败，请稍后重试')
  } finally {
    savingCol.value = false
  }
}

async function onDeleteCol(col) {
  try {
    await ElMessageBox.confirm(`确定删除题目集「${col.name}」吗？其中的题目会被移除。`, '删除题目集', { type: 'warning' })
    const res = await practiceApi.deleteCollection(chatStore.userId, col.collection_id)
    if (res.ok) {
      ElMessage.success('已删除')
      if (expandedCol.value === col.collection_id) expandedCol.value = ''
      await loadCollections()
    }
  } catch (e) { /* 取消 */ }
}

function onColCommand(cmd, col) {
  if (cmd === 'delete') onDeleteCol(col)
}

async function onRemoveQ(col, q) {
  try {
    await ElMessageBox.confirm('确定从题目集中移除这题吗？', '移除题目', { type: 'warning' })
    const res = await practiceApi.removeCollectionQuestion(chatStore.userId, col.collection_id, q.qid)
    if (res.ok) {
      ElMessage.success('已移除')
      await loadCollections()
    }
  } catch (e) { /* 取消 */ }
}

/** 集合内重做：服务端判对错，本地更新状态避免整页重载丢展开 */
async function onRedoCol(col, q, e) {
  try {
    const res = await practiceApi.redoCollectionQuestion(chatStore.userId, col.collection_id, q.qid, e.userAnswer)
    if (res.ok) {
      if (res.correct) ElMessage.success('回答正确！')
      else ElMessage.warning('还是不对，看下解析再想想吧')
      if (res.question) Object.assign(q, res.question)
    }
  } catch (err) {
    ElMessage.error(`保存失败: ${err.message}`)
  }
}

// ==================== 外部平台学习打卡（自评，呼应路径） ====================

function masteryStars(n) {
  const v = Math.max(0, Math.min(5, n || 0))
  return '★'.repeat(v) + '☆'.repeat(5 - v)
}

function openStudyDialog(node) {
  studyNode.value = node
  studyForm.value = {
    platform: node?.node_study?.platform || '牛客网',
    hours: 1,
    problems: 0,
    mastery: node?.node_study?.mastery || 3,
    note: '',
  }
  studyDialogVisible.value = true
}

async function doNodeStudy() {
  savingStudy.value = true
  try {
    const res = await practiceApi.nodeStudy(chatStore.userId, studyNode.value.node_id, studyForm.value)
    if (res.ok) {
      ElMessage.success(res.task_marked ? '已记录，路径进度已更新 ✅' : '已记录 ✅')
      studyDialogVisible.value = false
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`保存失败: ${err.message}`)
  } finally {
    savingStudy.value = false
  }
}

function platformColor(p) {
  return { LeetCode: '#f59e0b', 牛客: '#00a1e9', 洛谷: '#16a34a', AcWing: '#6366f1', PTA: '#dc2626' }[p] || '#6b7280'
}
function statusText(s) {
  return { undone: '未做', done: '已做', correct: '做对', wrong: '做错' }[s] || s
}
function shortTime(iso) {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' ')
}
function nodeTitle(nodeId) {
  return path.value?.nodes?.find(n => n.node_id === nodeId)?.title || nodeId
}

// 卡片搜索（深入练习触发）
async function findCards(node) {
  if (!isProgramming.value) {
    ElMessage.info('该科目没有对应的官方 OJ 题库')
    return
  }
  node._loading = true
  try {
    const res = await practiceApi.deepSearch(chatStore.userId, node.node_id, node.title, node.title, { count: 3 })
    if (res.ok) {
      node.practice_cards = res.cards
      ElMessage.success(res.message || `已找到 ${res.cards?.length} 道练习`)
      await refresh(true)
    }
  } catch (err) {
    console.error('deep-search 失败:', err)
    ElMessage.error('官方题库搜索失败，请稍后重试')
  } finally {
    node._loading = false
  }
}

// 打卡
const checkinVisible = ref(false)
const checkinNode = ref('')
const checkinNote = ref('')
const checking = ref(false)

function openCheckin() {
  checkinNode.value = ''
  checkinNote.value = ''
  checkinVisible.value = true
}
async function doCheckin() {
  checking.value = true
  try {
    const res = await practiceApi.checkin(chatStore.userId, checkinNode.value || '', checkinNote.value)
    if (res.ok) {
      ElMessage.success(`打卡成功！连续 ${res.streak} 天 🔥`)
      checkinVisible.value = false
      await refresh(true)
    }
  } catch (err) {
    ElMessage.error(`打卡失败: ${err.message}`)
  } finally {
    checking.value = false
  }
}

async function refresh(silent = false) {
  if (!silent) refreshing.value = true
  const [pRes, prRes, wRes, cRes] = await Promise.allSettled([
    onlinePathApi.get(chatStore.userId),
    practiceApi.progress(chatStore.userId),
    practiceApi.wrongQuestions(chatStore.userId),
    practiceApi.listCollections(chatStore.userId),
  ])
  if (pRes.status === 'fulfilled') {
    path.value = pRes.value?.ok ? pRes.value.path : null
    pathProgress.value = pRes.value?.progress || null
    isProgramming.value = pRes.value?.is_programming !== false
  } else {
    path.value = null
  }
  if (prRes.status === 'fulfilled') progress.value = prRes.value?.progress || null
  if (wRes.status === 'fulfilled') {
    wrongOj.value = wRes.value?.oj || []
    wrongAi.value = wRes.value?.ai || []
  }
  if (cRes.status === 'fulfilled') collections.value = cRes.value?.collections || []
  if (!silent) {
    pathLoading.value = false
    refreshing.value = false
  }
}

function scrollToWrong() {
  const el = document.querySelector('.prv-mistake-item')
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

onMounted(() => refresh())
</script>

<style scoped>
.practice-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6fa;
}
.prv-header {
  padding: 20px 28px 0;
  flex-shrink: 0;
}
.prv-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prv-title-row h2 {
  font-size: 18px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.prv-sub { font-size: 13px; color: #9ca3af; margin-top: 4px; }
.prv-actions { display: flex; gap: 8px; }

.prv-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 28px 32px;
}

/* 卡片 & 布局 */
.prv-card {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.prv-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) { .prv-grid { grid-template-columns: 1fr; } }

.prv-sec-label {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 12px;
  letter-spacing: 0.3px;
}

/* 空状态 */
.prv-empty {
  text-align: center;
  padding: 80px 20px;
  color: #9ca3af;
}
.prv-empty h3 { margin: 12px 0 6px; color: #374151; }
.prv-empty p { margin-bottom: 20px; font-size: 14px; max-width: 420px; margin-left: auto; margin-right: auto; }
.prv-empty-small { font-size: 13px; color: #d1d5db; padding: 8px 0; }

/* 路径卡 */
.prv-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.prv-path-name { font-size: 17px; font-weight: 700; color: #1f2937; }
.prv-path-goal { font-size: 13px; color: #6b7280; margin-top: 4px; }

.prv-path-progress {
  margin: 14px 0 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.prv-path-progress .el-progress { flex: 1; }
.prv-path-progress-text { font-size: 12px; color: #9ca3af; white-space: nowrap; }

/* 阶段时间线 */
.prv-stages { margin-top: 16px; }
.prv-stage-list { display: flex; flex-direction: column; gap: 0; }
.prv-stage { display: flex; gap: 12px; }
.prv-stage-line { display: flex; flex-direction: column; align-items: center; width: 22px; flex-shrink: 0; }
.prv-stage-dot {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.prv-stage-conn { width: 2px; flex: 1; min-height: 14px; background: #e5e7eb; }
.prv-stage-body { flex: 1; padding-bottom: 16px; }
.prv-stage-title { font-size: 14px; font-weight: 600; color: #374151; }
.prv-stage-desc { font-size: 12.5px; color: #6b7280; margin-top: 3px; line-height: 1.5; }
.prv-stage-days { font-size: 11px; color: #9ca3af; margin-top: 4px; display: inline-block; }
.prv-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.prv-stage-cards { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.prv-stage-card-link {
  font-size: 11.5px;
  color: #6366f1;
  text-decoration: none;
  border: 1px solid #e0e7ff;
  background: #eef2ff;
  border-radius: 6px;
  padding: 3px 8px;
  transition: border-color 0.15s, background 0.15s;
}
.prv-stage-card-link:hover { border-color: #6366f1; background: #e0e7ff; }

/* 节点 */
.prv-nodes { margin-top: 16px; }
.prv-node {
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
  background: #fbfbfd;
}
.prv-node-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.prv-node-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #374151; }
.prv-node-badge {
  font-size: 10px;
  color: #6366f1;
  background: #eef0ff;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 700;
  flex-shrink: 0;
}
.prv-node-days { font-size: 11px; color: #9ca3af; flex-shrink: 0; }
.prv-node-desc { font-size: 12.5px; color: #6b7280; margin-top: 4px; }

.prv-tasks { display: flex; gap: 4px; margin-top: 8px; flex-wrap: wrap; }
.prv-task-chip {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 6px;
  background: #eef0f4;
  color: #6b7280;
  cursor: default;
}
.prv-task-chip.done { background: #dcfce7; color: #166534; }
.prv-task-more { font-size: 10px; color: #9ca3af; align-self: center; }
.prv-node-cards { margin-top: 10px; }

/* 统计 */
.prv-stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 14px;
}
@media (max-width: 700px) { .prv-stats-row { grid-template-columns: repeat(2, 1fr); } }
.prv-stat { text-align: center; padding: 10px 4px; }
.prv-stat-big { font-size: 20px; font-weight: 800; color: #6366f1; }
.prv-stat-num { font-size: 26px; font-weight: 800; color: #1f2937; }
.prv-stat-num.hot { color: #f97316; }
.prv-stat-num.warn { color: #ef4444; }
.prv-stat-label { font-size: 12px; color: #6b7280; margin-top: 4px; }
.prv-stat-mini { font-size: 10px; color: #9ca3af; font-weight: 400; }
.prv-stat-sub { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.prv-checkin-row { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }

/* AI 练习统计条 */
.prv-ai-bar {
  margin-top: 12px;
  padding: 8px 12px;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  font-size: 12.5px;
  color: #4338ca;
  text-align: center;
}

/* 错题集分段 */
.prv-sub-sec { margin-bottom: 14px; }
.prv-sub-sec:last-child { margin-bottom: 0; }
.prv-sub-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 8px;
}
.prv-ai-wrong-list { display: flex; flex-direction: column; gap: 12px; }
.prv-ai-wrong-item {
  border: 1px solid #fee2e2;
  background: #fffbfb;
  border-radius: 10px;
  padding: 10px;
}
.prv-ai-wrong-topic {
  font-size: 12px;
  color: #ef4444;
  font-weight: 600;
  margin-bottom: 8px;
}

/* 打卡记录 */
.prv-checkin-list { display: flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; }
.prv-checkin-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  padding: 6px 10px;
  background: #f9fafb;
  border-radius: 8px;
}
.prv-checkin-date { color: #6366f1; font-weight: 600; flex-shrink: 0; }
.prv-checkin-node { color: #374151; flex-shrink: 0; max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prv-checkin-note { color: #9ca3af; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 错题本 */
.prv-mistake-list { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.prv-mistake-item {
  border: 1px solid #fee2e2;
  background: #fff5f5;
  border-radius: 8px;
  padding: 8px 10px;
}
.prv-mistake-head { display: flex; align-items: center; gap: 8px; }
.prv-mistake-no { font-size: 11px; color: #9ca3af; background: #fee2e2; padding: 1px 6px; border-radius: 4px; }
.prv-mistake-link { margin-left: auto; font-size: 12px; color: #ef4444; text-decoration: none; font-weight: 600; }
.prv-mistake-title { font-size: 13px; font-weight: 600; color: #374151; margin-top: 3px; }
.prv-mistake-note { font-size: 12px; color: #6b7280; margin-top: 3px; }

/* 最近练习 */
.prv-recent-list { display: flex; flex-direction: column; max-height: 300px; overflow-y: auto; }
.prv-recent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid #f3f4f6;
  font-size: 12.5px;
}
.prv-recent-status {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  flex-shrink: 0;
}
.st-undone { background: #eef0f4; color: #6b7280; }
.st-done { background: #dbeafe; color: #1d4ed8; }
.st-correct { background: #dcfce7; color: #166534; }
.st-wrong { background: #fee2e2; color: #b91c1c; }
.prv-recent-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #374151; }
.prv-recent-time { font-size: 11px; color: #9ca3af; flex-shrink: 0; }

.prv-dialog-tip { font-size: 12.5px; color: #6b7280; margin-bottom: 10px; }

/* 我的题目（题目集） */
.prv-collections-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.prv-collections-title { font-size: 13px; font-weight: 600; color: #6b7280; }
.prv-collections-empty { padding: 6px 0 2px; }
.prv-col { border: 1px solid #eef0f4; border-radius: 10px; margin-bottom: 8px; }
.prv-col-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.prv-col-head:hover, .prv-col-head.active { background: #f8f9ff; }
.prv-col-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.prv-col-arrow { font-size: 11px; color: #9ca3af; }
.prv-col-name { font-size: 13.5px; font-weight: 600; color: #1f2937; }
.prv-col-count { font-size: 12px; color: #9ca3af; }
.prv-col-type-chip {
  font-size: 10px; color: #fff; padding: 1px 7px; border-radius: 8px; font-weight: 600;
}
.prv-col-body { padding: 4px 12px 12px; border-top: 1px dashed #eef0f4; }
.prv-col-q { margin-top: 12px; }
.prv-col-q-ops { display: flex; justify-content: flex-end; }

/* 节点外部学习 */
.prv-node-study {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #eef0f4;
}
.prv-node-study-summary {
  font-size: 12.5px;
  color: #6b7280;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
  padding: 4px 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.prv-mastery { color: #f59e0b; }
.prv-node-study-note { color: #9ca3af; }
.prv-node-study-btn { flex-shrink: 0; }

/* 外部学习弹窗 */
.prv-study-form { margin-top: 4px; }
.prv-study-form .el-form-item { margin-bottom: 14px; }
.prv-form-unit { font-size: 12px; color: #9ca3af; margin-left: 8px; }
</style>
