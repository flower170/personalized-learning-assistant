<template>
  <div class="report-view">
    <div class="report-header">
      <div class="header-left">
        <h1>学习数据报告</h1>
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
          <h2>学生基本信息</h2>
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
          <h2>能力雷达图</h2>
          <span class="radar-scale-note">满分：10分</span>
        </div>
        <div v-if="radarDims.length" class="radar-container">
          <div class="radar-chart">
            <svg viewBox="0 0 300 300" class="radar-svg">
              <!-- 网格（每圈 2 分刻度） -->
              <polygon
                v-for="level in [0.2, 0.4, 0.6, 0.8, 1]"
                :key="'grid-' + level"
                :points="getPolygonPoints(level)"
                class="radar-grid"
              />
              <!-- 刻度数值（沿顶部轴） -->
              <text
                v-for="(lv, i) in [2, 4, 6, 8, 10]"
                :key="'scale-' + lv"
                :x="getScaleLabelX()"
                :y="getScaleLabelY(i)"
                class="radar-scale"
              >{{ lv }}</text>
              <!-- 轴线 -->
              <line
                v-for="(dim, idx) in radarDims"
                :key="'axis-' + idx"
                x1="150"
                y1="150"
                :x2="getPointX(idx, 1)"
                :y2="getPointY(idx, 1)"
                class="radar-axis"
              />
              <!-- 数据多边形 -->
              <polygon
                :points="getDataPoints()"
                class="radar-data"
              />
              <!-- 顶点 -->
              <circle
                v-for="(dim, idx) in radarDims"
                :key="'point-' + idx"
                :cx="getPointX(idx, dim.score / 10)"
                :cy="getPointY(idx, dim.score / 10)"
                :r="hoveredKey === dim.key ? 6 : 4"
                :fill="dim.color"
                class="radar-point"
                :class="{ 'is-hover': hoveredKey === dim.key }"
                @mouseenter="hoveredKey = dim.key"
                @mouseleave="hoveredKey = ''"
              />
              <!-- 维度标签 -->
              <text
                v-for="(dim, idx) in radarDims"
                :key="'label-' + idx"
                :x="getLabelX(idx)"
                :y="getLabelY(idx)"
                :text-anchor="getLabelAnchor(idx)"
                :fill="hoveredKey === dim.key ? dim.color : undefined"
                class="radar-label"
                :class="{ 'is-hover': hoveredKey === dim.key }"
                @mouseenter="hoveredKey = dim.key"
                @mouseleave="hoveredKey = ''"
              >{{ dim.name }}</text>
            </svg>
          </div>
          <div class="radar-scores">
            <div
              v-for="dim in sortedDims"
              :key="dim.key"
              class="score-item"
              :class="{ 'is-hover': hoveredKey === dim.key }"
              @mouseenter="hoveredKey = dim.key"
              @mouseleave="hoveredKey = ''"
            >
              <span class="score-dot" :style="{ background: dim.color }"></span>
              <span class="score-name">{{ dim.name }}</span>
              <div class="score-bar">
                <div
                  class="score-fill"
                  :style="{ width: (dim.score / 10) * 100 + '%', background: dim.color }"
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
          <h2>知识掌握情况</h2>
        </div>
        <div v-if="reportData.profile?.knowledge_base" class="knowledge-section">
          <div class="knowledge-block mastered">
            <h3>已掌握知识点</h3>
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
            <h3>需要加强</h3>
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
            <h3>待学习内容</h3>
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
          <h2>学习路径进度</h2>
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
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Printer, Back } from '@element-plus/icons-vue'
import { reportApi } from '@/api'

const route = useRoute()
const loading = ref(true)

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

function handlePrint() {
  window.print()
}

// ==================== 能力雷达图 ====================
// 展示层维度元信息：名称替换 + 主题色；「高频易错短板」为负向属性，反向映射为正向「知识掌握扎实度」
const DIM_META = {
  '知识基础水平': { label: '知识基础', color: '#6366f1' },
  '认知学习风格': { label: '学习风格', color: '#8b5cf6' },
  '高频易错短板': { label: '知识掌握扎实度', color: '#7c3aed', reverse: true },
  '个人兴趣方向': { label: '兴趣方向', color: '#4f46e5' },
  '学习目标': { label: '学习目标', color: '#a855f7' },
  '目标属性': { label: '目标属性', color: '#d946ef' },
}

const hoveredKey = ref('')

// 正向化的维度列表（保持后端原始顺序，供雷达图绘制）
const radarDims = computed(() => {
  const raw = reportData.value.radar?.dimensions || []
  return raw.map((d) => {
    const meta = DIM_META[d.name] || { label: d.name, color: '#6366f1' }
    const score = meta.reverse ? Math.max(0, Math.min(10, 10 - d.score)) : d.score
    return { key: d.name, name: meta.label, score, color: meta.color, description: d.description }
  })
})

// 右侧进度条按分值从高到低降序
const sortedDims = computed(() => [...radarDims.value].sort((a, b) => b.score - a.score))

const CENTER = 150
const DATA_RADIUS = 62
const LABEL_RADIUS = 88

function getPolygonPoints(level) {
  const count = radarDims.value.length || 6
  const points = []
  for (let i = 0; i < count; i++) {
    points.push(`${getPointX(i, level)},${getPointY(i, level)}`)
  }
  return points.join(' ')
}

function getDataPoints() {
  const points = []
  for (let i = 0; i < radarDims.value.length; i++) {
    const score = radarDims.value[i].score / 10
    points.push(`${getPointX(i, score)},${getPointY(i, score)}`)
  }
  return points.join(' ')
}

function getPointX(index, level) {
  const count = radarDims.value.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return CENTER + DATA_RADIUS * level * Math.cos(angle)
}

function getPointY(index, level) {
  const count = radarDims.value.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return CENTER + DATA_RADIUS * level * Math.sin(angle)
}

function getLabelX(index) {
  const count = radarDims.value.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return CENTER + LABEL_RADIUS * Math.cos(angle)
}

function getLabelY(index) {
  const count = radarDims.value.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return CENTER + LABEL_RADIUS * Math.sin(angle)
}

function getLabelAnchor(index) {
  const count = radarDims.value.length || 6
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  const cos = Math.cos(angle)
  if (Math.abs(cos) < 0.35) return 'middle'
  return cos > 0 ? 'start' : 'end'
}

function getScaleLabelX() {
  return CENTER + 6
}

function getScaleLabelY(levelIndex) {
  const level = (levelIndex + 1) * 0.2
  return CENTER - DATA_RADIUS * level + 3
}
</script>

<style scoped>
.report-view {
  padding: 24px;
  background: var(--bg-secondary);
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
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
  max-width: 1200px;
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
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 16px;
}
.card-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.radar-scale-note {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 400;
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
  gap: 24px;
  align-items: center;
}
.radar-chart {
  flex-shrink: 0;
  min-width: 0;
  display: flex;
  justify-content: flex-start;
}
.radar-svg {
  width: 240px;
  height: auto;
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
  fill: rgba(99, 102, 241, 0.18);
  stroke: #6366f1;
  stroke-width: 2;
}
.radar-point {
  stroke: #fff;
  stroke-width: 1.5;
  cursor: pointer;
  transition: r 0.15s ease, filter 0.15s ease;
}
.radar-point.is-hover {
  filter: drop-shadow(0 0 4px rgba(99, 102, 241, 0.65));
}
.radar-label {
  font-size: 10px;
  fill: var(--text-secondary);
  cursor: pointer;
  dominant-baseline: middle;
  transition: fill 0.15s ease;
}
.radar-label.is-hover {
  font-weight: 700;
}
.radar-scale {
  font-size: 8px;
  fill: #b0b5c0;
  text-anchor: start;
}
.radar-scores {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.score-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  transition: background 0.15s ease;
}
.score-item.is-hover {
  background: rgba(99, 102, 241, 0.06);
}
.score-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.score-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  flex-shrink: 0;
}
.score-bar {
  flex: 1;
  min-width: 0;
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}
.score-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}
.score-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  width: 36px;
  text-align: right;
  flex-shrink: 0;
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

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
}

/* 窄屏：雷达图在上、进度条在下，优先保证维度名称单行完整可读 */
@media (max-width: 720px) {
  .radar-container {
    flex-direction: column;
    gap: 16px;
  }
  .radar-chart {
    flex: none;
    width: 100%;
  }
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
    overflow-y: visible;
    height: auto;
    flex: none;
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