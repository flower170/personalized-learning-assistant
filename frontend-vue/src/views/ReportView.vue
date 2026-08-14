<template>
  <div class="report-view">
    <div class="report-header">
      <div class="header-left">
        <h1>📊 学习数据报告</h1>
        <p class="subtitle">生成时间: {{ reportData.generatedAt }}</p>
      </div>
      <div class="header-actions">
        <el-button @click="handlePrint" type="primary">
          <el-icon><Printer /></el-icon> 打印报告
        </el-button>
        <el-button @click="$router.back()">
          <el-icon><Back /></el-icon> 返回
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>正在生成报告...</p>
    </div>

    <div v-else class="report-content" id="report-print-area">
      <div class="report-card info-card">
        <div class="card-header">
          <h2>👤 学生基本信息</h2>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="label">学号</span>
            <span class="value">{{ reportData.profile?.student_id || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="label">姓名</span>
            <span class="value">{{ reportData.profile?.name || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="label">年级</span>
            <span class="value">{{ reportData.profile?.grade || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="label">专业</span>
            <span class="value">{{ reportData.profile?.major || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="label">学习风格</span>
            <span class="value">{{ reportData.profile?.cognitive_style || '-' }}</span>
          </div>
          <div class="info-item">
            <span class="label">学习节奏</span>
            <span class="value">{{ reportData.profile?.preferred_pace || '-' }}</span>
          </div>
        </div>
      </div>

      <div class="report-card">
        <div class="card-header">
          <h2>🎯 能力雷达图</h2>
        </div>
        <div v-if="reportData.radar?.dimensions?.length" class="radar-container">
          <div class="radar-chart">
            <svg viewBox="0 0 200 200" class="radar-svg">
              <polygon
                v-for="level in [1, 0.8, 0.6, 0.4, 0.2]"
                :key="level"
                :points="getPolygonPoints(level)"
                class="radar-grid"
              />
              <line
                v-for="(dim, idx) in reportData.radar.dimensions"
                :key="'axis-' + idx"
                x1="100"
                y1="100"
                :x2="getPointX(idx, 1)"
                :y2="getPointY(idx, 1)"
                class="radar-axis"
              />
              <polygon
                :points="getDataPoints()"
                class="radar-data"
              />
              <circle
                v-for="(dim, idx) in reportData.radar.dimensions"
                :key="'point-' + idx"
                :cx="getPointX(idx, dim.score / 10)"
                :cy="getPointY(idx, dim.score / 10)"
                r="4"
                class="radar-point"
              />
              <text
                v-for="(dim, idx) in reportData.radar.dimensions"
                :key="'label-' + idx"
                :x="getLabelX(idx)"
                :y="getLabelY(idx)"
                class="radar-label"
              >
                {{ dim.name }}
              </text>
            </svg>
          </div>
          <div class="radar-scores">
            <div
              v-for="dim in reportData.radar.dimensions"
              :key="dim.name"
              class="score-item"
            >
              <span class="score-name">{{ dim.name }}</span>
              <div class="score-bar">
                <div
                  class="score-fill"
                  :style="{ width: (dim.score / 10) * 100 + '%' }"
                ></div>
              </div>
              <span class="score-value">{{ dim.score.toFixed(1) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>暂无雷达图数据，请先构建学习画像</p>
        </div>
      </div>

      <div class="report-card">
        <div class="card-header">
          <h2>📚 知识掌握情况</h2>
        </div>
        <div v-if="reportData.profile?.knowledge_base" class="knowledge-section">
          <div class="knowledge-block mastered">
            <h3>✅ 已掌握知识点</h3>
            <div class="knowledge-tags">
              <span
                v-for="(item, idx) in reportData.profile.knowledge_base.mastered"
                :key="'mastered-' + idx"
                class="tag"
              >
                {{ item }}
              </span>
              <span v-if="!reportData.profile.knowledge_base.mastered?.length" class="empty-tag">
                暂无
              </span>
            </div>
          </div>
          <div class="knowledge-block weak">
            <h3>⚠️ 需要加强</h3>
            <div class="knowledge-tags">
              <span
                v-for="(item, idx) in reportData.profile.knowledge_base.weak"
                :key="'weak-' + idx"
                class="tag"
              >
                {{ item }}
              </span>
              <span v-if="!reportData.profile.knowledge_base.weak?.length" class="empty-tag">
                暂无
              </span>
            </div>
          </div>
          <div class="knowledge-block untouched">
            <h3>🔄 待学习内容</h3>
            <div class="knowledge-tags">
              <span
                v-for="(item, idx) in reportData.profile.knowledge_base.untouched"
                :key="'untouched-' + idx"
                class="tag"
              >
                {{ item }}
              </span>
              <span v-if="!reportData.profile.knowledge_base.untouched?.length" class="empty-tag">
                暂无
              </span>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>暂无知识掌握数据</p>
        </div>
      </div>

      <div class="report-card">
        <div class="card-header">
          <h2>🗺️ 学习路径进度</h2>
        </div>
        <div v-if="reportData.learningPath" class="learning-path-section">
          <div class="path-info">
            <span class="path-name">{{ reportData.learningPath.path?.path_name || '默认学习路径' }}</span>
            <span class="path-progress">
              完成度: {{ reportData.learningPath.progress?.overall_percentage || 0 }}%
            </span>
          </div>
          <div class="progress-bar-large">
            <div
              class="progress-fill"
              :style="{ width: (reportData.learningPath.progress?.overall_percentage || 0) + '%' }"
            ></div>
          </div>
          <div class="path-stages">
            <div
              v-for="(stage, idx) in reportData.learningPath.path?.stages"
              :key="idx"
              class="stage-item"
            >
              <div class="stage-num">{{ idx + 1 }}</div>
              <div class="stage-info">
                <span class="stage-title">{{ stage.title }}</span>
                <span class="stage-desc">{{ stage.description }}</span>
              </div>
              <div class="stage-status">
                <el-tag
                  :type="stage.status === 'completed' ? 'success' : stage.status === 'in_progress' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ stage.status === 'completed' ? '已完成' : stage.status === 'in_progress' ? '进行中' : '待开始' }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>暂无学习路径数据，请先生成学习路径</p>
        </div>
      </div>

      <div class="report-card">
        <div class="card-header">
          <h2>💬 近期会话记录</h2>
        </div>
        <div v-if="reportData.chatHistory?.length" class="chat-history">
          <div
            v-for="chat in reportData.chatHistory"
            :key="chat.sessionId"
            class="chat-item"
          >
            <div class="chat-title">{{ chat.title }}</div>
            <div class="chat-meta">
              <span>{{ chat.time }}</span>
              <span>{{ chat.messageCount }} 条消息</span>
            </div>
            <div class="chat-preview">{{ chat.lastMessage }}</div>
          </div>
        </div>
        <div v-else class="empty-state">
          <p>暂无会话记录</p>
        </div>
      </div>

      <div class="report-card suggestion-card">
        <div class="card-header">
          <h2>💡 AI 学习建议</h2>
        </div>
        <div v-if="suggestion" class="suggestion-content">
          <p>{{ suggestion }}</p>
        </div>
        <div v-else-if="suggestionLoading" class="suggestion-loading">
          <div class="spinner small"></div>
          <span>正在生成建议...</span>
        </div>
        <div v-else class="empty-state">
          <el-button @click="generateSuggestion" size="small" type="primary">
            生成学习建议
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Printer, Back } from '@element-plus/icons-vue'
import { reportApi, chatApi } from '@/api'

const route = useRoute()
const loading = ref(true)
const suggestionLoading = ref(false)
const suggestion = ref('')

const reportData = ref({
  profile: null,
  radar: null,
  learningPath: null,
  chatHistory: [],
  generatedAt: '',
})

const userId = route.params.userId || 'stu_001'

onMounted(async () => {
  await loadReport()
})

async function loadReport() {
  loading.value = true
  try {
    reportData.value = await reportApi.generate(userId)
  } catch (e) {
    console.error('Failed to generate report:', e)
  } finally {
    loading.value = false
  }
}

async function generateSuggestion() {
  suggestionLoading.value = true
  try {
    const profile = reportData.value.profile
    const prompt = `基于以下学生画像生成一份学习建议报告：
学号：${profile?.student_id || ''}
姓名：${profile?.name || ''}
年级：${profile?.grade || ''}
专业：${profile?.major || ''}
学习风格：${profile?.cognitive_style || ''}
学习节奏：${profile?.preferred_pace || ''}
已掌握知识点：${profile?.knowledge_base?.mastered?.join(', ') || ''}
薄弱知识点：${profile?.knowledge_base?.weak?.join(', ') || ''}
兴趣：${profile?.interests?.join(', ') || ''}
学习目标：${profile?.learning_goals?.short_term || ''}

请给出针对性的学习建议，包括：
1. 当前知识薄弱环节的改进方法
2. 学习计划建议
3. 资源推荐方向
4. 学习方法建议

输出格式：分点列出，语言简洁明了。`

    const res = await chatApi.send(userId, prompt)
    suggestion.value = res.reply || '暂无建议'
  } catch (e) {
    suggestion.value = '生成建议失败，请稍后重试'
  } finally {
    suggestionLoading.value = false
  }
}

function handlePrint() {
  window.print()
}

function getPolygonPoints(level) {
  const dims = reportData.value.radar?.dimensions || []
  const count = dims.length || 6
  const points = []
  for (let i = 0; i < count; i++) {
    points.push(`${getPointX(i, level)},${getPointY(i, level)}`)
  }
  return points.join(' ')
}

function getDataPoints() {
  const dims = reportData.value.radar?.dimensions || []
  const points = []
  for (let i = 0; i < dims.length; i++) {
    const score = dims[i].score / 10
    points.push(`${getPointX(i, score)},${getPointY(i, score)}`)
  }
  return points.join(' ')
}

function getPointX(index, level) {
  const dims = reportData.value.radar?.dimensions || []
  const count = dims.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return 100 + 80 * level * Math.cos(angle)
}

function getPointY(index, level) {
  const dims = reportData.value.radar?.dimensions || []
  const count = dims.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return 100 + 80 * level * Math.sin(angle)
}

function getLabelX(index) {
  const dims = reportData.value.radar?.dimensions || []
  const count = dims.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return 100 + 95 * Math.cos(angle)
}

function getLabelY(index) {
  const dims = reportData.value.radar?.dimensions || []
  const count = dims.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return 100 + 95 * Math.sin(angle)
}
</script>

<style scoped>
.report-view {
  padding: 24px;
  background: var(--bg-secondary);
  min-height: 100vh;
}
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.report-header h1 {
  font-size: 24px;
  color: var(--text-primary);
}
.subtitle {
  color: var(--text-muted);
  font-size: 14px;
  margin-top: 4px;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  gap: 16px;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--border-secondary);
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.spinner.small {
  width: 24px;
  height: 24px;
  border-width: 3px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.report-content {
  max-width: 900px;
  margin: 0 auto;
}
.report-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid var(--border-primary);
}
.card-header {
  margin-bottom: 16px;
}
.card-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.info-item .label {
  font-size: 12px;
  color: var(--text-muted);
}
.info-item .value {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}

.radar-container {
  display: flex;
  gap: 32px;
  align-items: center;
}
.radar-chart {
  flex-shrink: 0;
}
.radar-svg {
  width: 220px;
  height: 220px;
}
.radar-grid {
  fill: none;
  stroke: var(--border-secondary);
  stroke-width: 1;
}
.radar-axis {
  stroke: var(--border-secondary);
  stroke-width: 1;
}
.radar-data {
  fill: rgba(99, 102, 241, 0.2);
  stroke: #6366f1;
  stroke-width: 2;
}
.radar-point {
  fill: #6366f1;
}
.radar-label {
  font-size: 11px;
  fill: var(--text-secondary);
  text-anchor: middle;
  dominant-baseline: middle;
}
.radar-scores {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.score-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.score-name {
  font-size: 13px;
  color: var(--text-secondary);
  width: 70px;
  flex-shrink: 0;
}
.score-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}
.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 4px;
}
.score-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  width: 40px;
  text-align: right;
}

.knowledge-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.knowledge-block {
  padding: 12px;
  border-radius: 8px;
}
.knowledge-block h3 {
  font-size: 14px;
  margin-bottom: 8px;
}
.knowledge-block.mastered {
  background: rgba(34, 197, 94, 0.08);
}
.knowledge-block.mastered h3 {
  color: #22c55e;
}
.knowledge-block.mastered .tag {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.knowledge-block.weak {
  background: rgba(234, 179, 8, 0.08);
}
.knowledge-block.weak h3 {
  color: #eab308;
}
.knowledge-block.weak .tag {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}
.knowledge-block.untouched {
  background: rgba(59, 130, 246, 0.08);
}
.knowledge-block.untouched h3 {
  color: #3b82f6;
}
.knowledge-block.untouched .tag {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}
.knowledge-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
}
.empty-tag {
  color: var(--text-muted);
  font-size: 12px;
}

.path-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.path-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.path-progress {
  font-size: 13px;
  color: #6366f1;
  font-weight: 500;
}
.progress-bar-large {
  height: 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  overflow: hidden;
  margin-bottom: 16px;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 6px;
  transition: width 0.3s;
}
.path-stages {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.stage-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}
.stage-num {
  width: 28px;
  height: 28px;
  background: #6366f1;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.stage-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stage-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.stage-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.stage-status {
  flex-shrink: 0;
}

.chat-history {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-item {
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}
.chat-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.chat-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.chat-preview {
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.suggestion-card {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
  border-color: rgba(99, 102, 241, 0.2);
}
.suggestion-content p {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.8;
  white-space: pre-wrap;
}
.suggestion-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  justify-content: center;
}
.suggestion-loading span {
  font-size: 13px;
  color: var(--text-muted);
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

@media print {
  body {
    background: white;
  }
  .report-header {
    display: none;
  }
  .report-view {
    padding: 0;
    background: white;
  }
  .report-card {
    break-inside: avoid;
    border: 1px solid #e5e7eb;
    box-shadow: none;
  }
  .radar-svg {
    width: 180px;
    height: 180px;
  }
}
</style>