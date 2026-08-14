<template>
  <div class="msg-row" :class="[msg.role, { 'is-error': msg.isError }]">
    <!-- 气泡 -->
    <div class="msg-bubble" :class="{ streaming: isStreaming }">
      <!-- 🎬 豆包风格视频推荐卡片 -->
      <div v-if="videoCards.length" class="doubao-video-section">
        <div class="video-section-header">
          <el-icon :size="18" color="#f59e0b"><VideoCameraFilled /></el-icon>
          <span>为你精选的学习视频</span>
        </div>
        <div class="video-grid">
          <div
            v-for="(v, idx) in videoCards"
            :key="idx"
            class="doubao-video-card"
            @click="openVideo(v)"
          >
            <div class="video-cover" :style="{ background: getVideoCover(v, idx) ? undefined : coverGradient(idx, v.platform) }">
              <img
                v-if="getVideoCover(v, idx)"
                :src="getVideoCover(v, idx)"
                class="video-cover-img"
                loading="lazy"
                referrerpolicy="no-referrer"
                @error="$event.target.style.display='none'"
              />
              <span class="video-platform-badge">{{ v.platform || '视频' }}</span>
              <div class="video-play-overlay">
                <el-icon :size="36"><VideoPlay /></el-icon>
              </div>
              <span v-if="v.duration" class="video-dur-tag">{{ v.duration }}</span>
            </div>
            <div class="video-info">
              <div class="video-card-title">{{ v.title }}</div>
              <div v-if="v.reason" class="video-card-desc">{{ v.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 交互式练习题（逐题模式） -->
      <div v-if="exercises.length > 0 && !isStreaming" class="exercise-section">
        <div class="exercise-section-header">
          <div class="exercise-section-title">
            <el-icon :size="20" color="#6366f1"><EditPen /></el-icon>
            <span>练习题</span>
          </div>
          <div class="exercise-header-right">
            <span class="exercise-count">共 {{ exercises.length }} 题</span>
            <el-button
              size="small"
              plain
              class="mode-toggle-btn"
              @click="exerciseDisplayMode = exerciseDisplayMode === 'flat' ? 'interactive' : 'flat'"
            >
              {{ exerciseDisplayMode === 'flat' ? '答题模式' : '预览模式' }}
            </el-button>
          </div>
        </div>

        <!-- 友好开场：模型只输出 JSON，开场白由前端补，省 token 且数字准确 -->
        <div class="ex-intro">已为您准备 {{ exercises.length }} 道练习题，现在开始作答</div>

        <!-- 平铺展示模式（纯白底纯文本，题目全前置→答案全后置） -->
        <div v-if="exerciseDisplayMode === 'flat'" class="ex-flat">
          <!-- 题目区 -->
          <div class="ex-flat-questions">
            <template v-for="(group, gIdx) in exerciseGroups" :key="gIdx">
              <div class="ex-flat-section-title">{{ group.title }}</div>
              <div v-for="(ex, i) in group.items" :key="ex.id" class="ex-flat-qblock">
                <div class="ex-flat-qline">{{ groupStartIndex(gIdx) + i + 1 }}. {{ ex.question }}</div>
                <!-- 单选题/多选题选项 -->
                <div v-if="['choice','multiple','multi','multiple_choice'].includes(ex.type) && ex.options" class="ex-flat-opts">
                  <div v-for="opt in ex.options" :key="opt.label" class="ex-flat-opt">
                    {{ opt.label }}. {{ opt.text }}
                  </div>
                </div>
                <!-- 填空题：平铺模式也提供输入框，方便直接作答 -->
                <div v-if="ex.type === 'fill'" class="ex-flat-fill-row">
                  <input
                    v-model="flatFillAnswers[ex.id]"
                    class="flat-fill-input"
                    :placeholder="'输入答案...'"
                    @keyup.enter="submitFlatFill(ex)"
                  />
                </div>
              </div>
            </template>
          </div>

          <!-- 答案+统一解析区 -->
          <div class="ex-flat-answers">
            <div class="ex-flat-ans-title">答案与简要解析</div>
            <template v-for="(group, gIdx) in exerciseGroups" :key="'ag-'+gIdx">
              <div v-for="(ex, i) in group.items" :key="'a-'+ex.id" class="ex-flat-ans-row">
                {{ groupStartIndex(gIdx) + i + 1 }} 答案：{{ formatAnswer(ex) }} 解析：{{ ex.explanation || '' }}
              </div>
            </template>
            <!-- 平铺模式也提供提交批改按钮 -->
            <el-button
              size="small"
              type="primary"
              class="summarize-btn flat-summarize-btn"
              @click="emitSummary"
            >
              <el-icon><DataAnalysis /></el-icon> 提交批改
            </el-button>
          </div>
        </div>

        <!-- 交互逐题模式 -->
        <template v-if="exerciseDisplayMode === 'interactive'">
          <!-- 答题进度统计（答完部分题目后显示） -->
          <div v-if="exerciseAnswersCount > 0" class="answer-stats-compact">
            <span class="mini-stat correct">✅ {{ correctCount }} 正确</span>
            <span class="mini-stat wrong">❌ {{ wrongCount }} 错误</span>
            <span class="mini-stat pending">⏳ {{ pendingCount }} 待答</span>
          </div>

          <!-- 题目区域（同一时间只显示一题） -->
          <ExerciseCard
            v-for="(ex, i) in exercises"
            :key="ex.id"
            :exercise="ex"
            :currentIndex="i"
            :totalExercises="exercises.length"
            v-show="i === currentExerciseIndex"
            :show-save="exerciseDisplayMode === 'interactive'"
            @answer="onExerciseAnswer"
            @next="goToNextExercise"
            @prev="goToPrevExercise"
            @finish="finishExercise"
            @save="onSaveExercise"
          />

          <!-- 导航点 -->
          <div class="exercise-dots">
            <span
              v-for="(ex, i) in exercises"
              :key="i"
              class="dot"
              :class="{ active: i === currentExerciseIndex, done: exerciseAnswers[ex.id], correct: exerciseAnswers[ex.id]?.correct === true, wrong: exerciseAnswers[ex.id]?.correct === false }"
              @click="currentExerciseIndex = i"
            ></span>
          </div>

          <!-- 底部操作栏 -->
          <div class="exercise-actions-bar">
            <el-button size="small" plain @click="$emit('action', 'exercise_modify', '修改题目')">
              <el-icon><Refresh /></el-icon> 修改
            </el-button>
            <el-button size="small" plain @click="$emit('action', 'exercise_more', '更多题目')">
              <el-icon><Plus /></el-icon> 追加
            </el-button>
            <el-button
              v-if="allAnswered"
              size="small"
              type="primary"
              class="summarize-btn"
              @click="emitSummary"
            >
              <el-icon><DataAnalysis /></el-icon> 提交批改
            </el-button>
          </div>
        </template>
      </div>

      <!-- Markdown 内容（排除 JSON 和已渲染的练习部分） -->
      <div class="msg-content-wrapper">
        <div class="msg-content" v-html="renderedContent"></div>

        <!-- 语音朗读按钮 -->
        <button
          v-if="msg.role === 'assistant' && msg.content && !isStreaming"
          class="speech-btn"
          :class="{ playing: isPlaying }"
          @click.stop="toggleSpeech"
          :title="isPlaying ? '暂停朗读' : '朗读内容'"
        >
          <svg v-if="!isPlaying" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="4" width="4" height="16"></rect>
            <rect x="14" y="4" width="4" height="16"></rect>
          </svg>
          <span>{{ isPlaying ? '停止' : '朗读' }}</span>
        </button>
      </div>

      <!-- 流式光标 -->
      <span v-if="isStreaming" class="cursor-blink">|</span>

      <!-- 学习路径向导（聊天内交互：提问 → 草案确认） -->
      <div v-if="msg.intent === 'path' && msg.pathWizard" class="path-wizard-section">
        <PathWizardChat :msg="msg" />
      </div>

      <!-- 意图标签 -->
      <div v-if="msg.intent && msg.intent !== 'unknown'" class="msg-intent">
        <el-tag size="small" effect="plain" :type="intentTagType">
          {{ intentLabel }}
        </el-tag>
      </div>

      <!-- 建议操作按钮 -->
      <div v-if="msg.suggestions && msg.suggestions.length" class="msg-suggestions">
        <div class="suggestions-label">接下来你可以：</div>
        <div class="suggestions-list">
          <el-button
            v-for="s in msg.suggestions"
            :key="s.type"
            size="small"
            plain
            class="suggestion-btn"
            @click="$emit('action', s.type, s.label)"
          >
            {{ s.label }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- 收藏题目到「我的题目」 -->
    <SaveExerciseDialog
      v-model="saveDialogVisible"
      :exercise="saveExercise"
      :topic="saveTopic"
    />
  </div>
</template>

<script setup>
import { computed, ref, onUnmounted, reactive, watch } from 'vue'
import { marked } from 'marked'
import { useChatStore } from '@/stores/chat'
import { VideoPlay, VideoCameraFilled, EditPen, Refresh, Plus, DataAnalysis } from '@element-plus/icons-vue'
import ExerciseCard from './ExerciseCard.vue'
import PathWizardChat from './PathWizardChat.vue'
import SaveExerciseDialog from './SaveExerciseDialog.vue'

const props = defineProps({
  msg: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false },
})

const emit = defineEmits(['action'])

const chatStore = useChatStore()
const isPlaying = ref(false)
// 收藏题目到「我的题目」的弹窗状态
const saveDialogVisible = ref(false)
const saveExercise = ref(null)
const saveTopic = ref('')
const utterance = ref(null)
const speechSynth = window.speechSynthesis

onUnmounted(() => {
  if (speechSynth.speaking) speechSynth.cancel()
})

function toggleSpeech() {
  if (!props.msg.content || props.isStreaming) return
  if (speechSynth.speaking) { speechSynth.cancel(); isPlaying.value = false; return }
  const text = stripHtml(props.msg.content)
  if (!text.trim()) return
  utterance.value = new SpeechSynthesisUtterance(text)
  utterance.value.lang = chatStore.speechLanguage || 'zh-CN'
  utterance.value.rate = 1.0; utterance.value.pitch = 1.0; utterance.value.volume = 1.0
  utterance.value.onstart = () => { isPlaying.value = true }
  utterance.value.onend = () => { isPlaying.value = false }
  utterance.value.onerror = () => { isPlaying.value = false }
  speechSynth.speak(utterance.value)
  isPlaying.value = true
}

function stripHtml(html) {
  const temp = document.createElement('div')
  temp.innerHTML = html
  return temp.textContent || temp.innerText || ''
}

// ========== 练习 JSON 解析 ==========
/** 提取候选 JSON 字符串：优先 ```json 代码块；模型漏写围栏时，遍历所有平衡的 { ... }，
 *  取第一个含 exercises 数组的那个（JSON 可能在正文前或正文后）。 */
function pickExerciseJson(text) {
  if (!text) return ''
  const fenced = text.match(/```json\s*\n?([\s\S]*?)```/)
  if (fenced) return fenced[1].trim()
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== '{') continue
    let depth = 0
    for (let j = i; j < text.length; j++) {
      const ch = text[j]
      if (ch === '{') depth++
      else if (ch === '}') {
        depth--
        if (depth === 0) {
          const cand = text.slice(i, j + 1)
          try {
            const d = JSON.parse(cand)
            if (Array.isArray(d.exercises) && d.exercises.length) return cand
          } catch { /* 非 JSON 或结构不对，跳过 */ }
          i = j
          break
        }
      }
    }
  }
  return ''
}

function extractExercises(text) {
  if (!text) return []
  try {
    const jsonStr = pickExerciseJson(text)
    if (!jsonStr) return []
    const data = JSON.parse(jsonStr)
    const exercises = data.exercises || []
    // 标准化选项 + 答案格式，并为每个题目补充唯一 id（LLM 输出的 JSON 通常不含 id）
    for (let i = 0; i < exercises.length; i++) {
      const ex = exercises[i]
      // 补充唯一 id（LLM 输出的 JSON 通常不含 id），使用索引确保稳定
      if (ex.id === undefined || ex.id === null || ex.id === '') {
        ex.id = 'ex_' + i
      }
      // 标准化 type：'multiple' / 'multi' / 'multiple_choice' → 按 'choice' 渲染
      if (['multiple', 'multi', 'multiple_choice'].includes(ex.type)) {
        ex.type = 'choice'
      }
      if (ex.type === 'choice' && Array.isArray(ex.options)) {
        ex.options = ex.options.map((opt, idx) => {
          if (typeof opt === 'string') {
            // 纯字符串数组 ["选项A", "选项B"] → 转为 {label, text}
            const labels = ['A', 'B', 'C', 'D', 'E', 'F']
            return { label: labels[idx] || String(idx), text: opt }
          }
          if (typeof opt === 'object' && opt !== null) {
            // 已有 {label, text} 格式，但 text 可能为空
            return {
              label: opt.label || ['A', 'B', 'C', 'D', 'E', 'F'][idx] || String(idx),
              text: opt.text || opt.content || opt.value || '',
            }
          }
          return { label: String.fromCharCode(65 + idx), text: String(opt) }
        })
        // 标准化答案字段：如果 answer 是选项文本（如 "128MB"）而非标签（如 "B"），
        // 则自动映射为对应选项的 label
        if (ex.answer && typeof ex.answer === 'string') {
          const ansStr = ex.answer.trim()
          // 检查 answer 是否匹配某个选项的 label（单个字母 A/B/C/D）
          if (!/^[A-F]$/i.test(ansStr)) {
            // answer 不是单字母标签 → 尝试在 options 中查找匹配的 text
            const matched = ex.options.find(o =>
              o.text === ansStr ||
              o.text.includes(ansStr) ||
              ansStr.includes(o.text) ||
              // 处理 "B. 128MB" 或 "B.128MB" 格式
              ansStr.startsWith(o.label + '.') ||
              ansStr.startsWith(o.label + '．')
            )
            if (matched) {
              ex.answer = matched.label
            }
          }
        }
      }
    }
    return exercises
  } catch { return [] }
}

function clearExerciseJson(text) {
  if (!text) return ''
  // 移除完整的 ```json ... ``` 块
  let cleaned = text.replace(/```json[\s\S]*?```/g, '')
  // 模型漏写围栏的裸 JSON：若正好能被识别为练习题，一并移除，避免正文残留原始 JSON
  const bare = pickExerciseJson(cleaned)
  if (bare && extractExercises(cleaned).length > 0) {
    const idx = cleaned.indexOf(bare)
    if (idx !== -1) cleaned = cleaned.slice(0, idx) + cleaned.slice(idx + bare.length)
  }
  // 截断兜底：```json 只开不闭（JSON 生成到一半被 max_tokens 截断）→ 从 ```json 删到文末，
  // 避免正文残留一段无法解析的半截 JSON
  cleaned = cleaned.replace(/```json[\s\S]*$/, '')
  return cleaned.trim()
}

const exercises = computed(() => {
  if (props.isStreaming) return []  // 流式时不解析
  return extractExercises(props.msg.content)
})

const nonJsonContent = computed(() => {
  // 练习流式中 store 会写 displayContent（只含中文正文，无 JSON）；其余回落到完整 content
  return clearExerciseJson(props.msg.displayContent || props.msg.content)
})

// ========== 逐题状态管理 ==========
const currentExerciseIndex = ref(0)
const exerciseAnswers = reactive({})
const exerciseDisplayMode = ref('interactive')  // 'flat' | 'interactive' 平铺展示 / 逐题答题（默认直接进答题模式）
// 平铺模式下填空题答案存储
const flatFillAnswers = reactive({})

function typeLabel(type) {
  const map = { choice: '选择题', fill: '填空题', judge: '判断题', essay: '简答题', application: '应用题' }
  return map[type] || type
}
function diffLabel(diff) {
  const map = { basic: '基础', intermediate: '进阶', advanced: '挑战' }
  return map[diff] || diff
}
function formatAnswer(ex) {
  if (!ex.answer && ex.answer !== true && ex.answer !== false) {
    return '(等待批改)'
  }
  if (ex.type === 'choice') {
    const opt = (ex.options || []).find(o => o.label === ex.answer)
    return opt ? `${ex.answer}. ${opt.text}` : `${ex.answer}`
  }
  if (ex.type === 'judge') return ex.answer === true ? '正确 ✓' : '错误 ✗'
  return ex.answer || ''
}

const TYPE_ORDER = { choice: 1, fill: 2 }
const TYPE_LABELS = {
  choice: (n) => `一、单选题（共${n}题）`,
  fill: (n) => `二、填空题（共${n}题）`,
}

const exerciseGroups = computed(() => {
  const sorted = [...exercises.value].sort((a, b) => (TYPE_ORDER[a.type] || 99) - (TYPE_ORDER[b.type] || 99))
  const groups = []
  for (const ex of sorted) {
    const key = ex.type || 'other'
    let group = groups.find(g => g.key === key)
    if (!group) {
      group = { key, title: TYPE_LABELS[key] ? TYPE_LABELS[key](0) : key, items: [] }
      groups.push(group)
    }
    group.items.push(ex)
  }
  groups.forEach(g => {
    g.title = TYPE_LABELS[g.key] ? TYPE_LABELS[g.key](g.items.length) : g.title
  })
  return groups
})

function groupStartIndex(gIdx) {
  let idx = 0
  for (let i = 0; i < gIdx; i++) {
    idx += (exerciseGroups.value[i]?.items.length || 0)
  }
  return idx
}

function onExerciseAnswer(result) {
  exerciseAnswers[result.id] = result
}

/** 平铺模式下填空题提交 */
function submitFlatFill(ex) {
  const userAns = (flatFillAnswers[ex.id] || '').trim()
  if (!userAns) return
  const correctAns = String(ex.answer || '').trim()
  const isCorrect = userAns === correctAns
  exerciseAnswers[ex.id] = { id: ex.id, userAnswer: userAns, correct: isCorrect, type: 'fill' }
  // 提交后清空输入框，显示已答状态
  flatFillAnswers[ex.id] = '✅ 已提交'
  setTimeout(() => { flatFillAnswers[ex.id] = '' }, 2000)
}

function goToNextExercise() {
  if (currentExerciseIndex.value < exercises.value.length - 1) {
    currentExerciseIndex.value++
  }
}

function goToPrevExercise() {
  if (currentExerciseIndex.value > 0) {
    currentExerciseIndex.value--
  }
}

function finishExercise() {
  // 全部答完，高亮"提交批改"按钮（用户手动点击）
}

/** 从消息历史取最近一条用户消息作为知识点 topic */
function getConversationTopic() {
  const msgs = chatStore.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === 'user' && msgs[i].content) return msgs[i].content.slice(0, 50)
  }
  return '这个知识点'
}

function emitSummary() {
  // 收集答题数据
  const summaryData = {
    exercises: exercises.value,
    answers: { ...exerciseAnswers },
    correctCount: correctCount.value,
    wrongCount: wrongCount.value,
    totalCount: exercises.value.length,
  }
  // 直接从当前 ChatBubble 获取 topic（从消息列表往前找用户消息）
  // 直接调用 store 方法（绕过 emit 事件链，更可靠）
  chatStore.sendExerciseSummary(getConversationTopic(), summaryData)
}

/** 「加入错题集」：把当前题收藏进「我的题目」命名题目集 */
function onSaveExercise(ex) {
  saveExercise.value = ex
  saveTopic.value = getConversationTopic()
  saveDialogVisible.value = true
}

// 计算统计
const exerciseAnswersCount = computed(() => Object.keys(exerciseAnswers).length)
const correctCount = computed(() => Object.values(exerciseAnswers).filter(a => a.correct === true).length)
const wrongCount = computed(() => Object.values(exerciseAnswers).filter(a => a.correct === false).length)
const pendingCount = computed(() => exercises.value.length - exerciseAnswersCount.value)

const allAnswered = computed(() => {
  return exercises.value.length > 0 && exerciseAnswersCount.value >= exercises.value.length
})

// 切换消息时重置状态
watch(() => props.msg.content, () => {
  currentExerciseIndex.value = 0
  // 不重置 exerciseAnswers，保留已答记录
})

// ========== 视频解析 ==========
function extractVideoId(url) {
  if (!url) return null
  const bv = url.match(/BV([A-Za-z0-9]{10})/)
  if (bv) return 'BV' + bv[1]
  const av = url.match(/[Aa][Vv](\d+)/)
  if (av) return 'av' + av[1]
  const yt = url.match(/(?:v=|youtu\.be\/|embed\/)([A-Za-z0-9_-]{11})/)
  if (yt) return yt[1]
  return url.replace(/^https?:\/\//, '').split('?')[0]
}

function getVideoCover(v, idx) {
  const covers = props.msg.videoCovers || {}
  if (!Object.keys(covers).length) return null
  const vId = extractVideoId(v.url)
  if (!vId) return null
  for (const [url, cover] of Object.entries(covers)) {
    const cId = extractVideoId(url)
    if (cId && vId === cId) return cover
  }
  for (const [url, cover] of Object.entries(covers)) {
    if (v.url && (v.url.includes(url.split('?')[0]) || url.includes(v.url.split('?')[0]))) return cover
  }
  return null
}

const PLATFORM_GRADIENTS = {
  bilibili: 'linear-gradient(135deg, #fb7299 0%, #fc8bab 50%, #ffaec5 100%)',
  youtube: 'linear-gradient(135deg, #ff0000 0%, #e53935 50%, #ff5252 100%)',
  '中国大学mooc': 'linear-gradient(135deg, #1e88e5 0%, #42a5f5 50%, #64b5f6 100%)',
  '网易公开课': 'linear-gradient(135deg, #43a047 0%, #66bb6a 50%, #81c784 100%)',
  default: 'linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #a5b4fc 100%)',
}

function coverGradient(idx, platform) {
  const key = (platform || '').toLowerCase()
  for (const [kw, grad] of Object.entries(PLATFORM_GRADIENTS)) {
    if (key.includes(kw)) return grad
  }
  const altGradients = [
    'linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #a5b4fc 100%)',
    'linear-gradient(135deg, #10b981 0%, #34d399 50%, #6ee7b7 100%)',
    'linear-gradient(135deg, #f59e0b 0%, #fbbf24 50%, #fcd34d 100%)',
    'linear-gradient(135deg, #ef4444 0%, #f87171 50%, #fca5a5 100%)',
    'linear-gradient(135deg, #8b5cf6 0%, #a78bfa 50%, #c4b5fd 100%)',
  ]
  return altGradients[idx % altGradients.length]
}

const videoCards = computed(() => {
  try {
    if (!props.msg.content) return []
    const cards = []
    const text = props.msg.content
    const h2Match = text.match(/##\s*🎬\s*视频教程推荐\s*\n([\s\S]*?)(?=\n##\s+(?!🎬)|$)/)
    if (!h2Match) return []
    const sourceText = h2Match[1]
    const blocks = sourceText.split(/\n(?=###\s+(?:\d+[\.\、]\s*)?(?:🎬\s*)?)/)
    for (const block of blocks) {
      if (!block.trim() || block.trim().startsWith('## ')) continue
      const titleLinkMatch = block.match(/^###\s+(?:\d+[\.\、]\s*)?(?:🎬\s*)?(?:\[([^\]]+)\]\(([^)]+)\)|(.+?))(?:\n|$)/)
      if (!titleLinkMatch) continue
      const title = (titleLinkMatch[1] || titleLinkMatch[3] || '').trim()
      const linkUrl = (titleLinkMatch[2] || '').trim()
      const platform = (block.match(/(?:\*\*平台\*\*|平台)[：:]\s*(.+)/) || [])[1]?.trim() || ''
      const duration = (block.match(/(?:\*\*时长\*\*|时长)[：:]\s*(.+)/) || [])[1]?.trim() || ''
      const reasonLine = (block.match(/(?:\*\*推荐理由\*\*|推荐理由)[：:]\s*(.+)/) || [])[1]?.trim() || ''
      const keyword = (block.match(/(?:\*\*搜索关键词\*\*|搜索关键词)[：:]\s*(.+)/) || [])[1]?.trim() || ''
      let finalUrl = linkUrl
      if (!finalUrl && keyword) finalUrl = `https://search.bilibili.com/all?keyword=${encodeURIComponent(keyword)}`
      else if (!finalUrl) finalUrl = `https://search.bilibili.com/all?keyword=${encodeURIComponent(title)}`
      cards.push({
        title: title.replace(/^🎬\s*/, ''),
        url: finalUrl,
        platform: platform.replace(/^[-–—\s]+/, ''),
        duration: duration.replace(/^[-–—\s]+/, '') || '',
        reason: reasonLine || '',
      })
    }
    let count = cards.length
    if (count % 2 !== 0) count = Math.max(2, count - 1)
    if (count > 8) count = 8
    return cards.slice(0, count)
  } catch {
    return []
  }
})

const renderedContent = computed(() => {
  if (!props.msg.content) return ''
  try {
    let content = nonJsonContent.value
    // 移除视频 section
    const h2Idx = content.search(/##\s*🎬\s*视频教程推荐/)
    if (h2Idx !== -1) {
      const afterH2 = content.slice(h2Idx + content.slice(h2Idx).indexOf('\n') + 1)
      const nextH2Idx = afterH2.search(/\n##\s+(?!🎬)/)
      if (nextH2Idx !== -1) content = content.slice(0, h2Idx) + afterH2.slice(nextH2Idx)
      else content = content.slice(0, h2Idx)
    }
    // 移除以 ### 开头的视频条目（如果被错留在content里）
    content = content.replace(/###\s+\d+\.\s*\[.*?\]\(.*?\).*?\n/g, '')
    // 只要有 JSON 解析出的练习题数据，就剥离纯文本练习题避免重复
    // LLM 输出的是纯文本标题（一、二、三...），不是 Markdown ## 标题
    if (exercises.value.length > 0) {
      // 剥离从 "一、单选题" / "一、 单选题" 到 "答案与简要解析" 及其后的内容
      content = content.replace(/[一二三四五六七八九十]+[、.．\s]*(?:单选|多选|填空|判断|简答|应用)题[\s\S]*?(?:答案与简要解析[\s\S]*)?$/, '')
      // 兼容旧格式：## ✏️ 练习题 标题
      content = content.replace(/## ✏️ 练习题[\s\S]*?(?=\n## |$)/, '')
      // 如果还有残留的 "答案与简要解析" 行，也移除
      content = content.replace(/答案与简要解析[\s\S]*$/, '')
    }
    if (!content.trim()) return ''
    return marked(content)
  } catch {
    return props.msg.content
  }
})

const intentLabel = computed(() => {
  const map = { profile: '画像', resource: '资源', plan: '路径', tutor: '辅导', path: '路径' }
  return map[props.msg.intent] || props.msg.intent
})

const intentTagType = computed(() => {
  const map = { profile: 'warning', resource: 'success', plan: 'primary', tutor: 'info', path: 'primary' }
  return map[props.msg.intent] || 'info'
})

function openVideo(v) {
  window.open(v.url, '_blank', 'noopener')
}
</script>

<style scoped>
.msg-row {
  margin-bottom: 18px;
  max-width: 100%;
}
.msg-row.user { display: flex; justify-content: flex-end; }
.msg-row.assistant { display: flex; justify-content: flex-start; }

.msg-bubble {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  position: relative;
  max-width: 680px;
  width: fit-content;
  overflow: hidden;
}
.msg-row.user .msg-bubble {
  background: linear-gradient(135deg, #eef0ff 0%, #e0e7ff 100%);
  color: #1a1a1a;
  font-weight: 400;
  border-bottom-right-radius: 4px;
  border: 1px solid #c7d2fe;
}
.msg-row.assistant .msg-bubble {
  background: #f5f7fa;
  color: #374151;
  border-bottom-left-radius: 4px;
}
.msg-bubble.streaming {
  border: 1px solid #c7d2fe;
  box-shadow: 0 0 0 1px rgba(99,102,241,0.08);
}

/* Message content */
.msg-content-wrapper {
  display: flex;
  flex-direction: column;
}

/* Speech button */
.speech-btn {
  margin-top: 6px;
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  color: #6b7280;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  font-size: 12px;
  transition: all 0.2s ease;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  align-self: flex-end;
}
.speech-btn:hover {
  border-color: #c7d2fe;
  background: #f8fafc;
  color: #6366f1;
  box-shadow: 0 1px 3px rgba(99,102,241,0.1);
}
.speech-btn.playing {
  border-color: #6366f1;
  background: rgba(99,102,241,0.06);
  color: #6366f1;
}

.msg-bubble.is-error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
}

/* Markdown */
.msg-content :deep(p) { margin: 6px 0; }
.msg-content :deep(p:first-child) { margin-top: 0; }
.msg-content :deep(p:last-child) { margin-bottom: 0; }
.msg-content :deep(pre) {
  background: #f8f9fa;
  color: #374151;
  padding: 14px 16px;
  border-radius: 0;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  margin: 10px 0;
  border: none;
}
.msg-content :deep(pre code) { background: transparent; padding: 0; color: inherit; }
.msg-content :deep(code) {
  background: #f3f4f6;
  color: #dc2626;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
}
.msg-content :deep(h1), .msg-content :deep(h2), .msg-content :deep(h3) {
  margin: 12px 0 6px;
  color: #1f2937;
  font-weight: 600;
}
.msg-content :deep(h1) { font-size: 18px; border: none; }
.msg-content :deep(h2) { font-size: 16px; border: none; padding-bottom: 0; }
.msg-content :deep(h3) { font-size: 15px; border: none; }
.msg-row.user .msg-content :deep(h1),
.msg-row.user .msg-content :deep(h2),
.msg-row.user .msg-content :deep(h3) { color: inherit; }
.msg-content :deep(blockquote) {
  border-left: 3px solid #6366f1;
  padding-left: 12px;
  color: #6b7280;
  margin: 8px 0;
  background: #f8f9ff;
  padding: 8px 12px;
  border-radius: 0 8px 8px 0;
}
.msg-content :deep(ul), .msg-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.msg-content :deep(li) { margin: 3px 0; }
.msg-content :deep(img) { max-width: 100%; border-radius: 8px; }
.msg-content :deep(a) { color: #6366f1; text-decoration: none; font-weight: 500; }
.msg-content :deep(hr) { border: none; border-top: 1px solid #eef0f4; margin: 16px 0; }
.msg-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 13px;
}
.msg-content :deep(th) {
  background: #f3f4f6;
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  border: 1px solid #e5e7eb;
}
.msg-content :deep(td) {
  padding: 8px 12px;
  border: 1px solid #e5e7eb;
}

.cursor-blink {
  animation: blink 0.8s infinite;
  color: #6366f1;
  margin-left: 2px;
  font-weight: bold;
}
@keyframes blink { 50% { opacity: 0; } }

.msg-intent { margin-top: 6px; display: flex; justify-content: flex-end; }

/* Suggestions */
.msg-suggestions {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
}
.suggestions-label { font-size: 12px; color: #9ca3af; margin-bottom: 6px; }
.suggestions-list { display: flex; gap: 6px; flex-wrap: wrap; }
.suggestion-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 16px !important;
  transition: all 0.15s;
}
.suggestion-btn:hover {
  background: #eef0ff;
  border-color: #6366f1;
  color: #6366f1;
}

/* ===== 学习路径向导卡片 ===== */
.path-wizard-section {
  margin-bottom: 12px;
  border: 1px solid var(--border-primary, #e5e7eb);
  background: #fff;
  border-radius: 10px;
  padding: 12px 14px;
}

/* ===== 练习区域（逐题模式） ===== */
.exercise-section {
  margin-bottom: 16px;
}
.exercise-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.ex-intro {
  font-size: 12.5px;
  color: #6b7280;
  margin-bottom: 12px;
}
.exercise-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
}
.exercise-count {
  font-size: 12px;
  color: #9ca3af;
}

/* 紧凑型答题统计 */
.answer-stats-compact {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  padding: 8px 14px;
  background: #f8f9ff;
  border-radius: 10px;
}
.mini-stat {
  font-size: 13px;
  font-weight: 500;
}
.mini-stat.correct { color: #10b981; }
.mini-stat.wrong { color: #ef4444; }
.mini-stat.pending { color: #9ca3af; }

/* 导航点 */
.exercise-dots {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #e5e7eb;
  cursor: pointer;
  transition: all 0.2s ease;
}
.dot.active {
  background: #6366f1;
  transform: scale(1.3);
}
.dot.done {
  background: #9ca3af;
}
.dot.correct {
  background: #10b981;
}
.dot.wrong {
  background: #ef4444;
}
.dot:hover {
  transform: scale(1.2);
}

/* 操作按钮 */
.exercise-actions-bar {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
  justify-content: center;
}
.exercise-actions-bar .el-button {
  font-size: 12px;
  padding: 4px 14px;
  border-radius: 16px !important;
}
.summarize-btn {
  animation: pulse 1.5s ease-in-out infinite;
}
.flat-summarize-btn {
  margin-top: 16px;
  display: block;
  width: fit-content;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(99,102,241,0); }
}

/* Video section */
.doubao-video-section {
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid #f3f4f6;
}
.video-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}
.video-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.doubao-video-card {
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.doubao-video-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
  border-color: #e0e0e0;
}
.video-cover {
  position: relative;
  width: 100%;
  padding-top: 56.25%;
  overflow: hidden;
  background: #f3f4f6;
}
.video-cover-img {
  position: absolute;
  inset: 0; width: 100%; height: 100%;
  object-fit: cover; z-index: 0;
}
.video-platform-badge {
  position: absolute;
  top: 8px; left: 8px;
  font-size: 10px; color: #fff;
  background: rgba(0,0,0,0.45);
  backdrop-filter: blur(4px);
  padding: 2px 8px; border-radius: 10px;
  font-weight: 500; z-index: 2;
}
.video-play-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,0.9); z-index: 1;
  transition: all 0.2s;
}
.doubao-video-card:hover .video-play-overlay { transform: scale(1.12); color: #fff; }
.video-dur-tag {
  position: absolute; bottom: 8px; right: 8px;
  font-size: 10px; color: #fff;
  background: rgba(0,0,0,0.55);
  backdrop-filter: blur(4px);
  padding: 2px 6px; border-radius: 4px; z-index: 2;
}
.video-info { padding: 10px 12px; }
.video-card-title {
  font-size: 13px; font-weight: 600; color: #1f2937;
  line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-bottom: 4px;
}
.video-card-desc {
  font-size: 11px; color: #9ca3af;
  line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
@media (max-width: 500px) {
  .video-grid { grid-template-columns: 1fr; }
}

/* ===== 平铺展示模式 — 纯白底纯文本（无卡片、无边框、无深色块） ===== */
.exercise-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mode-toggle-btn {
  font-size: 12px !important;
  padding: 3px 12px !important;
  border-radius: 14px !important;
  color: #6366f1 !important;
  border-color: #c7d2fe !important;
}
.mode-toggle-btn:hover {
  background: #eef0ff !important;
  border-color: #6366f1 !important;
}

/* 平铺展示 — 纯白底纯文本，无分割线无装饰 */
.ex-flat-questions {
  margin: 4px 0;
}
.ex-flat-section-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  margin: 12px 0 4px 0;
}
.ex-flat-qblock {
  margin: 8px 0;
  line-height: 1.8;
}
.ex-flat-qline {
  font-size: 14px;
  color: #1f2937;
}
.ex-flat-opts {
  padding-left: 22px;
  margin: 2px 0;
}
.ex-flat-opt {
  font-size: 14px;
  color: #4b5563;
  line-height: 1.7;
}
.ex-flat-fill {
  padding-left: 22px;
  font-size: 14px;
  color: #9ca3af;
  letter-spacing: 4px;
  margin: 2px 0;
}
/* 平铺模式填空题输入框 */
.ex-flat-fill-row {
  padding-left: 22px;
  margin: 6px 0;
}
.flat-fill-input {
  width: 280px;
  padding: 6px 12px;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  font-family: inherit;
  transition: border-color 0.2s;
}
.flat-fill-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
}
/* 答案+解析区 — 无分割线无装饰 */
.ex-flat-answers {
  margin-top: 16px;
}
.ex-flat-ans-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  margin-bottom: 6px;
}
.ex-flat-ans-row {
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}
</style>
