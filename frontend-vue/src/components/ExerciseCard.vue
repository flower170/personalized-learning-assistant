<template>
  <div class="exercise-card" :class="[`difficulty-${exercise.difficulty}`, { 'answered': isAnswered }]">
    <!-- 进度条（standalone 隐藏） -->
    <div v-if="!standalone" class="exercise-progress">
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: progressPercent + '%' }"
        ></div>
      </div>
      <span class="progress-text">{{ currentIndex + 1 }} / {{ totalExercises }}</span>
    </div>

    <!-- 题目标题行 -->
    <div class="exercise-header">
      <span class="exercise-number">#{{ exercise.id }}</span>
      <span class="exercise-type-badge" :class="typeBadgeClass">{{ typeLabel }}</span>
      <span v-if="isMulti" class="multi-badge">📌 多选题</span>
      <span class="difficulty-badge" :class="`diff-${exercise.difficulty}`">{{ difficultyLabel }}</span>
      <span v-if="exercise.topic" class="exercise-topic">{{ exercise.topic }}</span>
    </div>

    <!-- 题目内容 -->
    <div class="exercise-question">
      <div class="question-text" v-html="renderedQuestion"></div>
    </div>

    <!-- 选择题选项（支持单选/多选） -->
    <div v-if="exercise.type === 'choice'" class="choice-options">
      <div
        v-for="opt in exercise.options || []"
        :key="opt.label"
        class="choice-option"
        :class="{
          'selected': isMulti ? selectedOptions.includes(opt.label) : selectedOption === opt.label,
          'correct': showResult && isCorrectOption(opt.label),
          'wrong': showResult && isWrongOption(opt.label),
          'disabled': showResult,
          'multi-select': isMulti
        }"
        @click="selectOption(opt.label)"
      >
        <span class="option-label">{{ opt.label }}</span>
        <span class="option-text">{{ opt.text }}</span>
        <span v-if="showResult && isCorrectOption(opt.label)" class="option-icon correct-icon">✓</span>
        <span v-if="showResult && isWrongOption(opt.label)" class="option-icon wrong-icon">✗</span>
      </div>
      <!-- 多选提交按钮 -->
      <el-button
        v-if="isMulti && !showResult && selectedOptions.length > 0"
        size="small"
        type="primary"
        class="multi-submit-btn"
        @click="submitMulti"
      >
        提交选择
      </el-button>
    </div>

    <!-- 判断题选项 -->
    <div v-if="exercise.type === 'judge'" class="judge-options">
      <div
        class="judge-option"
        :class="{
          'selected': selectedOption === 'true',
          'correct': showResult && exercise.answer === true,
          'wrong': showResult && selectedOption === 'true' && exercise.answer !== true,
          'disabled': showResult
        }"
        @click="selectOption('true')"
      >
        <span class="judge-icon">✓</span>
        <span>正确</span>
      </div>
      <div
        class="judge-option"
        :class="{
          'selected': selectedOption === 'false',
          'correct': showResult && exercise.answer === false,
          'wrong': showResult && selectedOption === 'false' && exercise.answer !== false,
          'disabled': showResult
        }"
        @click="selectOption('false')"
      >
        <span class="judge-icon">✗</span>
        <span>错误</span>
      </div>
    </div>

    <!-- 填空题 -->
    <div v-if="exercise.type === 'fill'" class="fill-blank">
      <input
        v-model="fillAnswer"
        class="fill-input"
        :class="{ 'correct': showResult && isCorrect, 'wrong': showResult && !isCorrect }"
        :placeholder="showResult ? '' : '输入答案...'"
        :disabled="showResult"
        @keyup.enter="submitFill"
      />
    </div>

    <!-- 简答题/应用题 -->
    <div v-if="exercise.type === 'essay' || exercise.type === 'application'" class="essay-area">
      <textarea
        v-model="essayAnswer"
        class="essay-input"
        :placeholder="showResult ? '' : '输入你的回答...'"
        :disabled="showResult"
        rows="3"
      ></textarea>
    </div>

    <!-- 操作按钮 -->
    <div class="exercise-footer">
      <!-- 收藏到我的题目（showSave 时显示，如聊天答题模式） -->
      <el-button
        v-if="showSave"
        size="small"
        plain
        class="save-btn"
        @click="$emit('save', exercise)"
      >
        📥 加入错题集
      </el-button>

      <!-- 交答案按钮（填空/简答需要主动提交） -->
      <el-button
        v-if="!isAnswered && needsSubmit"
        size="small"
        type="primary"
        @click="submitAnswer"
        :disabled="!canSubmit"
      >
        <el-icon><Select /></el-icon> 提交答案
      </el-button>

      <!-- 上一题按钮（standalone 隐藏） -->
      <el-button
        v-if="!standalone && showResult && currentIndex > 0"
        size="small"
        plain
        @click="$emit('prev')"
      >
        <el-icon><ArrowLeft /></el-icon> 上一题
      </el-button>

      <!-- 下一题按钮（答完后显示，standalone 隐藏） -->
      <el-button
        v-if="!standalone && showResult && !isLast"
        size="small"
        plain
        @click="$emit('next')"
      >
        下一题 <el-icon><ArrowRight /></el-icon>
      </el-button>

      <!-- 完成按钮（最后一题答完后，standalone 隐藏） -->
      <el-button
        v-if="!standalone && showResult && isLast"
        size="small"
        type="success"
        @click="$emit('finish')"
      >
        <el-icon><Check /></el-icon> 完成所有题目
      </el-button>
    </div>

    <!-- 答案与解析（答后显示） -->
    <transition name="fade">
      <div v-if="showResult" class="exercise-feedback">
        <div class="feedback-result" :class="isCorrect ? 'correct' : 'wrong'">
          <span class="result-icon">{{ isCorrect ? '✅ 回答正确！' : '❌ 回答错误' }}</span>
        </div>
        <div class="exercise-answer">
          <span class="answer-label">正确答案：</span>
          <span class="answer-value">{{ formattedAnswer }}</span>
        </div>
        <div class="exercise-explanation">
          <span class="explanation-label">💡 解析：</span>
          <span class="explanation-text">{{ exercise.explanation }}</span>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Select, ArrowRight, ArrowLeft, Check } from '@element-plus/icons-vue'

const props = defineProps({
  exercise: { type: Object, required: true },
  currentIndex: { type: Number, default: 0 },
  totalExercises: { type: Number, default: 1 },
  /** 单题独立模式（错题重做等场景）：隐藏进度条与上一题/下一题/完成按钮，答题后只留解析反馈 */
  standalone: { type: Boolean, default: false },
  /** 显示「📥 加入错题集」收藏按钮（聊天答题模式用） */
  showSave: { type: Boolean, default: false },
})

const emit = defineEmits(['answer', 'next', 'finish', 'save'])

const selectedOption = ref('')
const selectedOptions = ref([])   // 多选
const fillAnswer = ref('')
const essayAnswer = ref('')
const isAnswered = ref(false)
const isCorrect = ref(false)
const showResult = ref(false)

/** 判断是否为多选（答案含多个字母如 "ABCDE"） */
const isMulti = computed(() => {
  if (props.exercise.type !== 'choice') return false
  const ans = String(props.exercise.answer || '')
  return ans.length > 1 && /^[A-F]+$/.test(ans)
})

/** 某选项是否为正确答案 */
function isCorrectOption(label) {
  if (!showResult.value) return false
  if (isMulti.value) {
    return String(props.exercise.answer || '').includes(label)
  }
  return label === props.exercise.answer
}

/** 某选项是否为错误选择（用户选了但不对） */
function isWrongOption(label) {
  if (!showResult.value) return false
  if (isMulti.value) {
    return selectedOptions.value.includes(label) && !String(props.exercise.answer || '').includes(label)
  }
  return selectedOption.value === label && label !== props.exercise.answer
}

// 切换题目时重置状态
watch(() => props.exercise.id, () => {
  selectedOption.value = ''
  selectedOptions.value = []
  fillAnswer.value = ''
  essayAnswer.value = ''
  isAnswered.value = false
  isCorrect.value = false
  showResult.value = false
})

const typeLabel = computed(() => {
  const map = { choice: '选择题', fill: '填空题', judge: '判断题', essay: '简答题', application: '应用题' }
  return map[props.exercise.type] || props.exercise.type
})

const typeBadgeClass = computed(() => {
  const map = { choice: 'type-choice', fill: 'type-fill', judge: 'type-judge', essay: 'type-essay', application: 'type-app' }
  return map[props.exercise.type] || ''
})

const difficultyLabel = computed(() => {
  const map = { basic: '⭐ 基础', intermediate: '⭐⭐ 进阶', advanced: '⭐⭐⭐ 挑战' }
  return map[props.exercise.difficulty] || props.exercise.difficulty
})

const needsSubmit = computed(() => ['essay', 'application', 'fill'].includes(props.exercise.type))
const canSubmit = computed(() => {
  if (props.exercise.type === 'fill') return fillAnswer.value.trim().length > 0
  if (props.exercise.type === 'essay' || props.exercise.type === 'application') return essayAnswer.value.trim().length > 0
  return false
})

const isLast = computed(() => props.currentIndex >= props.totalExercises - 1)

const progressPercent = computed(() => {
  // currentIndex 从0开始，所以 +1 才是当前题号
  return ((props.currentIndex + 1) / props.totalExercises) * 100
})

const renderedQuestion = computed(() => {
  if (!props.exercise.question) return ''
  return props.exercise.question.replace(/____/g, '<span class="blank-highlight">____</span>')
})

const formattedAnswer = computed(() => {
  const ex = props.exercise
  if (ex.type === 'choice') {
    if (isMulti.value) {
      // 多选：显示所有正确答案的文本
      const ansLabels = String(ex.answer || '').split('').filter(l => l.trim())
      const parts = ansLabels.map(l => {
        const opt = (ex.options || []).find(o => o.label === l)
        return `${l}. ${opt ? opt.text : ''}`
      })
      return parts.join('；')
    }
    const opt = (ex.options || []).find(o => o.label === ex.answer)
    return `${ex.answer}. ${opt ? opt.text : ''}`
  }
  if (ex.type === 'judge') return ex.answer === true ? '正确 ✓' : '错误 ✗'
  return ex.answer || ''
})

function selectOption(label) {
  if (showResult.value) return

  if (isMulti.value) {
    // 多选：切换选中状态（点击已选则取消）
    const idx = selectedOptions.value.indexOf(label)
    if (idx === -1) {
      selectedOptions.value = [...selectedOptions.value, label]
    } else {
      selectedOptions.value = selectedOptions.value.filter(l => l !== label)
    }
    return
  }

  // 单选：立即提交答案
  selectedOption.value = label
  isAnswered.value = true
  const exAnswer = String(props.exercise.answer || '').trim()
  const matchedOpt = (props.exercise.options || []).find(o => o.label === label)
  isCorrect.value = (
    label === exAnswer ||
    (matchedOpt && matchedOpt.text === exAnswer) ||
    (matchedOpt && exAnswer.startsWith(label + '.')) ||
    (matchedOpt && exAnswer.includes(matchedOpt.text))
  )
  showResult.value = true
  emit('answer', { id: props.exercise.id, userAnswer: label, correct: isCorrect.value, type: 'choice' })
}

/** 多选提交 */
function submitMulti() {
  if (showResult.value || selectedOptions.value.length === 0) return
  isAnswered.value = true
  showResult.value = true
  const userLabels = [...selectedOptions.value].sort().join('')
  const correctLabels = String(props.exercise.answer || '').split('').filter(l => l.trim()).sort().join('')
  isCorrect.value = userLabels === correctLabels
  emit('answer', {
    id: props.exercise.id,
    userAnswer: userLabels,
    correct: isCorrect.value,
    type: 'choice',
    isMulti: true,
  })
}

function submitFill() {
  if (!fillAnswer.value.trim() || showResult.value) return
  isAnswered.value = true
  showResult.value = true
  const userAns = fillAnswer.value.trim()
  const correctAns = String(props.exercise.answer || '').trim()
  isCorrect.value = userAns === correctAns
  emit('answer', { id: props.exercise.id, userAnswer: fillAnswer.value, correct: isCorrect.value, type: 'fill' })
}

function submitAnswer() {
  if (props.exercise.type === 'fill') submitFill()
  else submitEssay()
}

function submitEssay() {
  if (!essayAnswer.value.trim() || showResult.value) return
  isAnswered.value = true
  showResult.value = true
  // 简答题不自动判对错
  isCorrect.value = false
  emit('answer', { id: props.exercise.id, userAnswer: essayAnswer.value, correct: null, type: props.exercise.type })
}
</script>

<style scoped>
.exercise-card {
  background: #ffffff;
  border: 1.5px solid #eef0f4;
  border-radius: 16px;
  padding: 20px;
  margin-bottom: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  animation: slideUp 0.35s ease-out;
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Progress */
.exercise-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.progress-bar {
  flex: 1;
  height: 4px;
  background: #f3f4f6;
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 2px;
  transition: width 0.4s ease;
}
.progress-text {
  font-size: 12px;
  color: #9ca3af;
  font-weight: 500;
  white-space: nowrap;
}

/* Header */
.exercise-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.exercise-number {
  font-size: 13px;
  font-weight: 700;
  color: #6366f1;
  background: #eef0ff;
  padding: 2px 10px;
  border-radius: 6px;
}
.exercise-type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
  color: #fff;
}
.type-choice { background: #6366f1; }
.type-fill { background: #10b981; }
.type-judge { background: #f59e0b; }
.type-essay { background: #ec4899; }
.multi-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
  background: #8b5cf6;
  color: #fff;
}
.type-app { background: #8b5cf6; }

.difficulty-badge {
  font-size: 11px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Question */
.exercise-question { margin-bottom: 16px; }
.question-text {
  font-size: 15px;
  line-height: 1.7;
  color: #1f2937;
}
.question-text :deep(.blank-highlight) {
  color: #6366f1;
  font-weight: 700;
  background: #eef0ff;
  padding: 1px 8px;
  border-radius: 4px;
}

/* Choice */
.choice-options { display: flex; flex-direction: column; gap: 8px; }
.choice-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1.5px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}
.choice-option:hover:not(.disabled) { border-color: #a5b4fc; background: #f8f9ff; }
.choice-option.selected { border-color: #6366f1; background: #eef0ff; }
.choice-option.correct { border-color: #10b981; background: #ecfdf5; }
.choice-option.wrong { border-color: #ef4444; background: #fef2f2; }
.choice-option.disabled { cursor: default; }
.choice-option.multi-select.selected {
  border-color: #6366f1;
  background: #eef0ff;
  box-shadow: 0 0 0 2px rgba(99,102,241,0.15);
}
.multi-submit-btn {
  margin-top: 8px;
  align-self: flex-start;
  border-radius: 10px;
}

.option-label {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #f3f4f6;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: #6b7280;
  flex-shrink: 0;
}
.choice-option.selected .option-label { background: #6366f1; color: #fff; }
.choice-option.correct .option-label { background: #10b981; color: #fff; }
.choice-option.wrong .option-label { background: #ef4444; color: #fff; }

.option-text { font-size: 14px; color: #374151; flex: 1; }
.option-icon { font-size: 18px; font-weight: 700; }
.correct-icon { color: #10b981; }
.wrong-icon { color: #ef4444; }

/* Judge */
.judge-options { display: flex; gap: 12px; }
.judge-option {
  flex: 1;
  display: flex; align-items: center; justify-content: center;
  gap: 8px; padding: 14px;
  border: 1.5px solid #e5e7eb; border-radius: 12px;
  cursor: pointer; font-size: 15px; font-weight: 600;
  transition: all 0.2s;
}
.judge-option:hover:not(.disabled) { border-color: #a5b4fc; background: #f8f9ff; }
.judge-option.selected { border-color: #6366f1; background: #eef0ff; }
.judge-option.correct { border-color: #10b981; background: #ecfdf5; color: #10b981; }
.judge-option.wrong { border-color: #ef4444; background: #fef2f2; color: #ef4444; }
.judge-option.disabled { cursor: default; }
.judge-icon { font-size: 20px; }

/* Fill */
.fill-blank { display: flex; gap: 8px; }
.fill-input {
  flex: 1;
  padding: 12px 16px;
  border: 1.5px solid #e5e7eb;
  border-radius: 12px;
  font-size: 15px;
  outline: none;
  transition: all 0.2s;
  font-family: inherit;
}
.fill-input:focus:not(:disabled) { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.fill-input.correct { border-color: #10b981; background: #ecfdf5; }
.fill-input.wrong { border-color: #ef4444; background: #fef2f2; }

/* Essay */
.essay-area { display: flex; flex-direction: column; }
.essay-input {
  width: 100%;
  padding: 12px 16px;
  border: 1.5px solid #e5e7eb;
  border-radius: 12px;
  font-size: 14px;
  resize: vertical;
  outline: none;
  font-family: inherit;
  line-height: 1.6;
  transition: border-color 0.2s;
}
.essay-input:focus:not(:disabled) { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }

/* Footer */
.exercise-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #f3f4f6;
}
.exercise-footer .el-button { border-radius: 10px; font-size: 13px; }
.save-btn { color: #8b5cf6 !important; border-color: #ddd6fe !important; }
.save-btn:hover { background: #f5f3ff !important; border-color: #8b5cf6 !important; }

/* Feedback */
.exercise-feedback {
  margin-top: 14px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px solid #f3f4f6;
}
.feedback-result {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
}
.feedback-result.correct { color: #10b981; }
.feedback-result.wrong { color: #ef4444; }

.exercise-answer {
  margin-bottom: 10px;
  padding: 10px 14px;
  background: #eef0ff;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.5;
}
.answer-label { color: #6366f1; font-weight: 600; }
.answer-value { color: #374151; }

.exercise-explanation {
  font-size: 13px;
  line-height: 1.6;
  color: #6b7280;
}
.explanation-label { font-weight: 600; color: #f59e0b; }

.fade-enter-active { transition: all 0.3s ease; }
.fade-enter-from { opacity: 0; transform: translateY(-8px); }
</style>
