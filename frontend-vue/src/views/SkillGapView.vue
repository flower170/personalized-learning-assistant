<template>
  <div class="skill-gap-view">
    <!-- 头部 -->
    <div class="sgv-header">
      <div class="sgv-title-row">
        <h2><el-icon><TrendCharts /></el-icon> 技能 vs 市场需求差距雷达</h2>
        <div class="sgv-actions">
          <el-button size="small" @click="$router.push('/')">
            <el-icon><Back /></el-icon> 返回聊天
          </el-button>
        </div>
      </div>
      <p class="sgv-sub">联网聚合招聘信息里的高频技能词，与你的学习画像对比，找出最值得补的差距</p>
    </div>

    <!-- 分析输入行 -->
    <div class="sgv-toolbar">
      <el-input
        v-model="role"
        class="sgv-role-input"
        placeholder="目标岗位，如：后端开发工程师 / 数据分析师 / 前端工程师"
        clearable
        @keyup.enter="doAnalyze"
      />
      <el-button type="primary" :loading="loading" @click="doAnalyze">
        <el-icon><Search /></el-icon> {{ loading ? '分析中…' : '开始分析' }}
      </el-button>
    </div>

    <!-- 分析结果 -->
    <div v-if="result" class="sgv-body">
      <!-- 雷达图 + 维度列表 -->
      <div class="sgv-section">
        <div class="sgv-radar-row">
          <RadarChart v-if="result.dimensions?.length" :data="result.dimensions" :size="420" mode="dual" />
          <div class="sgv-legend-list">
            <div class="sgv-legend-title">
              <span class="sgv-legend-head" style="color:#6366f1">我的技能</span>
              <span style="color:#9ca3af">vs</span>
              <span class="sgv-legend-head" style="color:#f59e0b">市场需求</span>
              <el-tag size="small" effect="plain" class="sgv-source-tag">
                来源: {{ result.source === 'search' ? '实时搜索' : '模型' }}
              </el-tag>
            </div>
            <div v-for="(dim, i) in result.dimensions" :key="dim.name" class="sgv-legend-item">
              <span class="sgv-legend-dot" :style="{ background: legendColors[i % legendColors.length] }"></span>
              <span class="sgv-legend-name">{{ dim.name }}</span>
              <div class="sgv-legend-bar-row">
                <div class="sgv-legend-bar" :style="{ width: (dim.skill_score ?? 0) * 10 + '%' }"></div>
              </div>
              <span class="sgv-legend-score" style="color:#6366f1">{{ (dim.skill_score ?? 0).toFixed(1) }}</span>
              <div class="sgv-legend-bar-row">
                <div class="sgv-legend-bar amber" :style="{ width: (dim.market_score ?? 0) * 10 + '%' }"></div>
              </div>
              <span class="sgv-legend-score" style="color:#f59e0b">{{ (dim.market_score ?? 0).toFixed(1) }}</span>
              <span v-if="gapOf(dim) > 0" class="sgv-gap-badge">+{{ gapOf(dim).toFixed(1) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 优先补齐建议 -->
      <div class="sgv-section" v-if="result.top_priority">
        <h3 class="sgv-section-title">最值得优先补齐</h3>
        <div class="sgv-priority">
          <template v-if="Array.isArray(result.top_priority)">
            <el-tag
              v-for="(p, i) in result.top_priority"
              :key="i"
              size="large"
              effect="dark"
              class="sgv-priority-tag"
            >{{ p }}</el-tag>
          </template>
          <template v-else>
            <el-tag size="large" effect="dark" class="sgv-priority-tag">{{ result.top_priority }}</el-tag>
          </template>
        </div>
      </div>

      <!-- 市场需求摘要 -->
      <div class="sgv-section" v-if="result.market_summary">
        <h3 class="sgv-section-title">市场怎么说</h3>
        <p class="sgv-summary">{{ result.market_summary }}</p>
      </div>

      <div class="sgv-foot" v-if="result.updated_at">
        <span>分析时间：{{ result.updated_at }}</span>
        <el-button size="small" text @click="toProfile">去画像看看我的基础 →</el-button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="sgv-empty">
      <el-icon :size="56" color="#c7d2fe"><TrendCharts /></el-icon>
      <h3>输入一个目标岗位</h3>
      <p>我会联网搜 JD 里的技能要求，对比你的画像，画出差距雷达</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import RadarChart from '@/components/RadarChart.vue'
import { TrendCharts, Search, Back } from '@element-plus/icons-vue'
import { skillGapApi } from '@/api'

const router = useRouter()
const chatStore = useChatStore()

const role = ref('后端开发工程师')
const loading = ref(false)
const result = ref(null)

const legendColors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6', '#f97316']

function gapOf(dim) {
  return Math.round(((dim.market_score ?? 0) - (dim.skill_score ?? 0)) * 10) / 10
}

async function doAnalyze() {
  const r = role.value.trim()
  if (!r) return
  loading.value = true
  try {
    const res = await skillGapApi.analyze(chatStore.userId, r, 6)
    result.value = res
  } catch (err) {
    console.error('技能差距分析失败:', err)
    result.value = null
    alert('分析失败，请重试（可能是联网搜索超时）')
  } finally {
    loading.value = false
  }
}

function toProfile() {
  router.push('/profile')
}
</script>

<style scoped>
.skill-gap-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6fa;
}
.sgv-header {
  padding: 20px 28px 0;
  flex-shrink: 0;
}
.sgv-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sgv-title-row h2 {
  font-size: 18px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.sgv-sub { font-size: 13px; color: #9ca3af; margin-top: 4px; }
.sgv-actions { display: flex; gap: 8px; }

.sgv-toolbar {
  padding: 16px 28px;
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}
.sgv-role-input { max-width: 420px; }

.sgv-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 28px 32px;
}

/* 雷达图行 */
.sgv-radar-row {
  display: flex;
  gap: 24px;
  align-items: center;
  flex-wrap: wrap;
}
.sgv-legend-list { flex: 1; min-width: 280px; display: flex; flex-direction: column; gap: 6px; }
.sgv-legend-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.sgv-legend-head { font-weight: 700; }
.sgv-source-tag { margin-left: auto; }
.sgv-legend-item {
  display: grid;
  grid-template-columns: 6px 70px 1fr 34px 1fr 34px 40px;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.sgv-legend-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.sgv-legend-name { color: #374151; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sgv-legend-bar-row { height: 7px; background: #eef0f4; border-radius: 4px; overflow: hidden; }
.sgv-legend-bar { height: 100%; background: #6366f1; border-radius: 4px; transition: width 0.4s; }
.sgv-legend-bar.amber { background: #f59e0b; }
.sgv-legend-score { font-weight: 700; font-size: 11px; text-align: right; }
.sgv-gap-badge {
  font-size: 10px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 8px;
  padding: 1px 5px;
  text-align: center;
  font-weight: 700;
}

/* 分区 */
.sgv-section { padding: 14px 0; }
.sgv-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 10px;
}
.sgv-priority { display: flex; flex-wrap: wrap; gap: 8px; }
.sgv-priority-tag { font-size: 13px; }
.sgv-summary {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.7;
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 12px 16px;
  white-space: pre-line;
}
.sgv-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
  padding-top: 12px;
}

/* 空状态 */
.sgv-empty {
  flex: 1;
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}
.sgv-empty h3 { margin: 12px 0 6px; color: #374151; }
.sgv-empty p { font-size: 14px; }
</style>
