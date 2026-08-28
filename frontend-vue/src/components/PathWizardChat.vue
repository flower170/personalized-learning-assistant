<template>
  <div class="pw-chat">
    <!-- 加载中 -->
    <div v-if="w.status === 'loading'" class="pw-loading">
      <el-icon class="is-loading" :size="18"><Loading /></el-icon>
      <span>{{ w.topic ? `正在规划「${w.topic}」的学习路径…` : '正在规划学习路径…' }}</span>
    </div>

    <!-- 生成中（流式进度） -->
    <div v-else-if="w.status === 'generating'" class="pw-loading">
      <el-icon class="is-loading" :size="18"><Loading /></el-icon>
      <span>{{ w.progress || '正在生成学习路径草案…' }}</span>
    </div>

    <!-- 提问补充 -->
    <div v-else-if="w.status === 'ask'" class="pw-step">
      <div class="pw-head">学习路径规划</div>

      <!-- 画像已识别科目 → 让用户确认（不用开放提问） -->
      <template v-if="w.confirmSubject">
        <div class="pw-desc">
          我会结合你的画像 + 市场需求 + 官方练习资源，生成宏观（阶段）+ 微观（每日）两级学习路径。
        </div>
        <div class="pw-confirm">
          <div class="pw-confirm-q">{{ (w.questions || [])[0] || `根据你的画像，你想学的科目是「${w.confirmSubject}」，确认吗？` }}</div>
          <div class="pw-confirm-actions">
            <el-button type="primary" :loading="submitting" @click="confirmSubject(w.confirmSubject)">
              ✅ 确认「{{ w.confirmSubject }}」，开始规划
            </el-button>
          </div>
          <div class="pw-confirm-replace">
            <el-input
              v-model="replaceSubject"
              placeholder="想换个科目？直接写（如：Excel 数据分析）"
              clearable
              size="default"
              @keyup.enter="confirmSubject(replaceSubject.trim())"
            />
            <el-button :loading="submitting" @click="confirmSubject(replaceSubject.trim())">
              用这个科目
            </el-button>
          </div>
        </div>
      </template>

      <!-- 推不出科目 → 开放提问 -->
      <template v-else>
        <div class="pw-desc">
          我会结合你的画像 + 市场需求 + 官方练习资源，生成宏观（阶段）+ 微观（每日）两级学习路径。
          信息不够，先问你几个问题：
        </div>
        <div v-for="(q, i) in w.questions" :key="i" class="pw-question">
          <div class="pw-q-label">{{ i + 1 }}. {{ q }}</div>
          <!-- 时间/基础这类枚举问题给 chips 一键选，其余保持文本输入 -->
          <div v-if="chipOptions[w.missingKeys[i]]" class="pw-q-chips">
            <button
              v-for="c in chipOptions[w.missingKeys[i]]"
              :key="c.value"
              type="button"
              class="pw-q-chip"
              :class="{ 'is-active': answers[w.missingKeys[i]] === c.value }"
              @click="onChipPick(w.missingKeys[i], c.value)"
            >{{ c.label }}</button>
          </div>
          <el-input
            v-model="answers[w.missingKeys[i]]"
            placeholder="请输入"
            clearable
            size="default"
          />
        </div>
        <el-button type="primary" class="pw-submit" :loading="submitting" @click="submitAnswers">
          继续 →
        </el-button>
      </template>
    </div>

    <!-- 草案预览 -->
    <div v-else-if="w.status === 'draft'" class="pw-step">
      <div class="pw-head">路径草案</div>
      <div v-if="w.revised && w.draft.revision_reason" class="pw-revision">
        🔄 已按你的意见修改：<b>{{ w.draft.revision_reason }}</b>
      </div>
      <div class="pw-meta">
        <span class="pw-tag">总周期 {{ w.draft.total_duration_days }} 天</span>
        <span class="pw-tag">每日 {{ w.draft.daily_minutes }} 分钟</span>
        <span v-if="w.draft.collected?.foundation" class="pw-tag">基础：{{ w.draft.collected.foundation }}</span>
        <span v-if="w.draft.goal" class="pw-tag">{{ w.draft.goal }}</span>
      </div>
      <div v-if="w.draft.market_demand" class="pw-demand">{{ w.draft.market_demand }}</div>

      <!-- 路径级推荐视频（整个路径只推一个，B站播放量最高，点击直达） -->
      <div v-if="w.draft.recommended_video" class="pw-rec-video">
        <span class="pw-rec-label">推荐视频</span>
        <a
          :href="w.draft.recommended_video.url"
          target="_blank"
          rel="noopener"
          class="pw-res-link"
          :title="w.draft.recommended_video.url"
        >
          <span class="pw-res-plat">{{ w.draft.recommended_video.platform }}</span>
          <span class="pw-res-title">{{ w.draft.recommended_video.title }}</span>
          <span class="pw-res-ext">↗</span>
        </a>
      </div>

      <el-timeline class="pw-timeline">
        <el-timeline-item
          v-for="stage in w.draft.stages"
          :key="stage.stage"
          :timestamp="`第${stage.stage}阶段 · ${stage.estimated_days}天`"
          placement="top"
        >
          <div class="pw-stage">
            <div class="pw-stage-title">{{ stage.title }}</div>
            <div class="pw-stage-desc">{{ stage.description }}</div>
            <div v-if="stage.focus_points?.length" class="pw-stage-points">
              <span v-for="p in stage.focus_points" :key="p" class="pw-point">{{ p }}</span>
            </div>
            <!-- 阶段配套资源（标准模板：视频/练习网站/数据集，点击直达） -->
            <div v-if="stage.resources?.length" class="pw-stage-res">
              <a
                v-for="r in stage.resources"
                :key="r.url + r.title"
                :href="r.url"
                target="_blank"
                rel="noopener"
                class="pw-res-link"
                :title="r.url"
              >
                <span class="pw-res-plat">{{ r.platform }}</span>
                <span class="pw-res-title">{{ r.title }}</span>
                <span class="pw-res-ext">↗</span>
              </a>
            </div>
            <div v-if="stage.practice_cards?.length" class="pw-cards">
              <a
                v-for="c in stage.practice_cards"
                :key="c.card_id"
                :href="c.link"
                target="_blank"
                rel="noopener"
                class="pw-card-link"
              >
                <span class="pw-card-plat">{{ c.platform }}</span>
                <span class="pw-card-title">{{ c.title || c.knowledge_point }}</span>
                <span class="pw-card-diff">{{ c.difficulty }}</span>
              </a>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>

      <div class="pw-actions">
        <el-button type="success" :loading="submitting" @click="doConfirm">
          确认采用
        </el-button>
        <el-input
          v-model="feedback"
          class="pw-feedback"
          placeholder="输入修改意见（如：第一阶段再基础些）"
          clearable
          @keyup.enter="doRevise"
        />
        <el-button :loading="submitting" @click="doRevise">按意见重新生成</el-button>
      </div>
    </div>

    <!-- 完成 -->
    <div v-else-if="w.status === 'done'" class="pw-step pw-done">
      <div class="pw-head">学习路径已保存</div>
      <div class="pw-desc">你可以在左侧「我的练习」页面查看路径、打卡和进度。</div>
    </div>

    <!-- 错误 -->
    <div v-else-if="w.status === 'error'" class="pw-step pw-error">
      <div class="pw-error-text">❌ {{ w.error }}</div>
      <el-button size="small" type="primary" plain @click="retry">重试</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'

const props = defineProps({
  msg: { type: Object, required: true },
})

const chatStore = useChatStore()
const w = computed(() => props.msg.pathWizard || {})

const answers = ref({})
const feedback = ref('')
const replaceSubject = ref('')
const submitting = ref(false)

/** 枚举类问题给 chips：每天时间 / 基础水平（值与后端 INFO_LABELS / _parse_hours 对齐） */
const chipOptions = {
  daily_hours: [
    { label: '30分钟', value: '30分钟' },
    { label: '1小时', value: '1小时' },
    { label: '2小时', value: '2小时' },
    { label: '3小时+', value: '3小时' },
  ],
  foundation: [
    { label: '零基础', value: '零基础' },
    { label: '入门', value: '入门' },
    { label: '进阶', value: '进阶' },
    { label: '已会大部分', value: '已会大部分' },
  ],
}

function onChipPick(key, val) {
  answers.value[key] = val
  // 所有缺失项都已填 → 自动提交，少点一次「继续」
  const allFilled = (w.value.missingKeys || []).every((k) => {
    const v = answers.value[k]
    return v !== undefined && v !== null && v !== ''
  })
  if (allFilled) submitAnswers()
}

/** 画像已识别科目 → 确认或换科目，带着 subject 直接进 Stage 2 → 出草案 */
async function confirmSubject(subject) {
  const s = (subject || '').trim()
  if (!s) {
    ElMessage.info('请填写要学的科目')
    return
  }
  submitting.value = true
  try {
    await chatStore.pathAnswer(props.msg, { subject: s }, `确认科目：${s}`)
  } finally {
    submitting.value = false
    replaceSubject.value = ''
  }
}

function buildAnswers() {
  const filled = {}
  ;(w.value.missingKeys || []).forEach((k) => {
    const v = answers.value[k]
    if (v !== undefined && v !== null && v !== '') filled[k] = v
  })
  return filled
}

async function submitAnswers() {
  const filled = buildAnswers()
  if (!Object.keys(filled).length) {
    ElMessage.info('请先填写至少一个问题的回答')
    return
  }
  const keys = w.value.missingKeys || []
  const text = (w.value.questions || [])
    .map((q, i) => (filled[keys[i]] ? `${q} → ${filled[keys[i]]}` : ''))
    .filter(Boolean)
    .join('；')
  submitting.value = true
  try {
    await chatStore.pathAnswer(props.msg, filled, text ? `我的补充：${text}` : '')
  } finally {
    submitting.value = false
  }
}

async function doConfirm() {
  submitting.value = true
  try {
    await chatStore.pathConfirm(props.msg)
  } finally {
    submitting.value = false
  }
}

async function doRevise() {
  if (!feedback.value.trim()) {
    ElMessage.info('请先输入修改意见，或直接点「确认采用」')
    return
  }
  submitting.value = true
  try {
    await chatStore.pathRevise(props.msg, feedback.value.trim())
  } finally {
    submitting.value = false
    feedback.value = ''
  }
}

function retry() {
  chatStore.pathStart(w.value.topic, w.value.startOpts || {})
}
</script>

<style scoped>
.pw-chat {
  margin-top: 8px;
}
.pw-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary, #4b5563);
  padding: 6px 0;
}
.pw-step {
  padding: 2px 0;
}
.pw-head {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #1f2937);
  margin-bottom: 8px;
}
.pw-desc {
  font-size: 12.5px;
  color: var(--text-secondary, #4b5563);
  line-height: 1.6;
  margin-bottom: 12px;
}
.pw-question {
  margin-bottom: 10px;
}
.pw-q-label {
  font-size: 13px;
  color: var(--text-primary, #1f2937);
  margin-bottom: 5px;
  font-weight: 500;
}
.pw-submit {
  margin-top: 6px;
  width: 100%;
}
.pw-q-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.pw-q-chip {
  padding: 5px 14px;
  border-radius: 16px;
  border: 1px solid var(--border-primary, #e5e7eb);
  background: #fff;
  font-size: 13px;
  color: var(--text-secondary, #4b5563);
  cursor: pointer;
  transition: all 0.15s;
}
.pw-q-chip:hover {
  border-color: var(--accent-primary, #6366f1);
  color: var(--accent-primary, #6366f1);
}
.pw-q-chip.is-active {
  background: var(--accent-primary, #6366f1);
  border-color: var(--accent-primary, #6366f1);
  color: #fff;
}
.pw-confirm {
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  border-radius: 10px;
  padding: 12px 14px;
}
.pw-confirm-q {
  font-size: 13px;
  color: var(--text-primary, #1f2937);
  line-height: 1.7;
  margin-bottom: 10px;
}
.pw-confirm-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.pw-confirm-replace {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  align-items: center;
}
.pw-revision {
  background: #fef3c7;
  border: 1px solid #fbbf24;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12.5px;
  color: #92400e;
  margin-bottom: 12px;
}
.pw-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.pw-tag {
  background: var(--accent-primary-light, #eef2ff);
  color: var(--accent-primary, #6366f1);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 500;
}
.pw-demand {
  font-size: 12.5px;
  color: #92400e;
  background: #fffbeb;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 12px;
  line-height: 1.5;
}
.pw-rec-video {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.pw-rec-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-primary, #6366f1);
  white-space: nowrap;
}
.pw-timeline {
  margin-top: 4px;
}
.pw-stage-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
}
.pw-stage-desc {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  margin: 4px 0;
  line-height: 1.5;
}
.pw-stage-points {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pw-point {
  font-size: 11px;
  background: var(--bg-tertiary, #f3f4f6);
  color: var(--text-secondary, #4b5563);
  padding: 2px 8px;
  border-radius: 999px;
}
.pw-stage-res {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.pw-res-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 11.5px;
  text-decoration: none;
  color: var(--text-primary, #1f2937);
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pw-res-link:hover {
  border-color: var(--accent-primary, #6366f1);
  box-shadow: 0 1px 4px rgba(99, 102, 241, 0.15);
}
.pw-res-plat {
  font-weight: 600;
  color: var(--accent-primary, #6366f1);
}
.pw-res-title {
  color: var(--text-secondary, #4b5563);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}
.pw-res-ext {
  font-size: 10px;
  color: var(--text-tertiary, #9ca3af);
}
.pw-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.pw-card-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 11.5px;
  text-decoration: none;
  color: var(--text-primary, #1f2937);
  background: #fff;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pw-card-link:hover {
  border-color: var(--accent-primary, #6366f1);
  box-shadow: 0 1px 4px rgba(99, 102, 241, 0.15);
}
.pw-card-plat {
  font-weight: 600;
  color: var(--accent-primary, #6366f1);
}
.pw-card-title {
  color: var(--text-secondary, #4b5563);
}
.pw-card-diff {
  font-size: 10.5px;
  color: #f59e0b;
}
.pw-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.pw-feedback {
  flex: 1;
  min-width: 180px;
}
.pw-done {
  text-align: center;
  padding: 20px 10px;
}
.pw-done-icon {
  font-size: 38px;
  margin-bottom: 8px;
}
.pw-error-text {
  font-size: 13px;
  color: #dc2626;
  margin-bottom: 10px;
}
</style>
