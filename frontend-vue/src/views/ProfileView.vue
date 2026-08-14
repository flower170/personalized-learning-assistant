<template>
  <div class="profile-view">
    <!-- 头部 -->
    <div class="pv-header">
      <div class="pv-title-row">
        <h2><el-icon><User /></el-icon> 我的学习画像</h2>
        <div class="pv-actions">
          <el-button size="small" plain @click="startChat" :disabled="chatStore.loading">
            <el-icon><ChatDotSquare /></el-icon> 对话完善
          </el-button>
          <el-button size="small" @click="toggleEdit">
            <el-icon><Edit /></el-icon> {{ isEditing ? '取消' : '编辑' }}
          </el-button>
          <el-button size="small" @click="$router.push('/')">
            <el-icon><Back /></el-icon> 返回聊天
          </el-button>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!chatStore.profile" class="pv-empty">
      <el-icon :size="56" color="#c7d2fe"><User /></el-icon>
      <h3>暂未完成画像采集</h3>
      <p>开始对话即可自动构建你的多维度学习画像</p>
      <el-button type="primary" @click="startChat">开始构建画像</el-button>
    </div>

    <!-- 画像内容（可滚动） -->
    <div v-else class="pv-body">
      <!-- 基本信息行 -->
      <div class="pv-section">
        <div class="pv-info-grid">
          <div class="pv-info-item">
            <span class="pv-label">学号</span>
            <span class="pv-value">{{ chatStore.profile.student_id }}</span>
          </div>
          <div class="pv-info-item">
            <span class="pv-label">姓名</span>
            <template v-if="isEditing">
              <el-input v-model="editForm.name" size="small" class="pv-input" />
            </template>
            <span v-else class="pv-value">{{ chatStore.profile.name || '-' }}</span>
          </div>
          <div class="pv-info-item">
            <span class="pv-label">年级</span>
            <template v-if="isEditing">
              <el-select v-model="editForm.grade" size="small" class="pv-input" placeholder="选择年级">
                <el-option label="大一" value="大一" />
                <el-option label="大二" value="大二" />
                <el-option label="大三" value="大三" />
                <el-option label="大四" value="大四" />
                <el-option label="研究生" value="研究生" />
              </el-select>
            </template>
            <span v-else class="pv-value">{{ chatStore.profile.grade || '-' }}</span>
          </div>
          <div class="pv-info-item">
            <span class="pv-label">专业</span>
            <template v-if="isEditing">
              <el-input v-model="editForm.major" size="small" class="pv-input" />
            </template>
            <span v-else class="pv-value">{{ chatStore.profile.major || '-' }}</span>
          </div>
          <div class="pv-info-item">
            <span class="pv-label">认知风格</span>
            <template v-if="isEditing">
              <el-select v-model="editForm.cognitive_style" size="small" class="pv-input" placeholder="选择认知风格">
                <el-option label="视觉型" value="视觉型" />
                <el-option label="听觉型" value="听觉型" />
                <el-option label="读写型" value="读写型" />
                <el-option label="动觉型" value="动觉型" />
              </el-select>
            </template>
            <span v-else class="pv-value">{{ chatStore.profile.cognitive_style || '-' }}</span>
          </div>
          <div class="pv-info-item">
            <span class="pv-label">学习节奏</span>
            <template v-if="isEditing">
              <el-select v-model="editForm.preferred_pace" size="small" class="pv-input" placeholder="选择学习节奏">
                <el-option label="慢速细学" value="慢速细学" />
                <el-option label="适中" value="适中" />
                <el-option label="快速速成" value="快速速成" />
              </el-select>
            </template>
            <span v-else class="pv-value">{{ chatStore.profile.preferred_pace || '-' }}</span>
          </div>
        </div>
        <div v-if="isEditing" class="pv-edit-actions">
          <el-button size="small" type="primary" @click="saveProfile">保存</el-button>
          <el-button size="small" @click="toggleEdit">取消</el-button>
        </div>
      </div>

      <div class="pv-divider"></div>

      <!-- 雷达图（ECharts） -->
      <div class="pv-section">
        <h3 class="pv-section-title">维度评分</h3>
        <div v-if="chatStore.radarData.length" class="pv-radar-row">
          <RadarChart :data="chatStore.radarData" :size="400" />
          <div class="pv-legend-list">
            <div v-for="(dim, i) in chatStore.radarData" :key="dim.name" class="pv-legend-item">
              <span class="pv-legend-dot" :style="{ background: legendColors[i] }"></span>
              <span class="pv-legend-name">{{ dim.name }}</span>
              <span class="pv-legend-score">{{ dim.score.toFixed(1) }}</span>
              <span class="pv-legend-desc">{{ dim.description }}</span>
            </div>
          </div>
        </div>
        <div v-else class="pv-empty-small">暂未收集到维度数据</div>
      </div>

      <div class="pv-divider"></div>

      <!-- 知识基础 -->
      <div class="pv-section">
        <h3 class="pv-section-title">知识基础</h3>
        <div class="pv-kb-row">
          <div class="pv-kb-col">
            <div class="pv-kb-head mastered">✅ 已掌握</div>
            <div v-if="chatStore.profile.knowledge_base?.mastered?.length" class="pv-tags">
              <el-tag v-for="k in chatStore.profile.knowledge_base.mastered" :key="k" size="small" type="success" effect="plain">{{ k }}</el-tag>
            </div>
            <span v-else class="pv-empty-small">暂无</span>
          </div>
          <div class="pv-kb-col">
            <div class="pv-kb-head weak">⚠️ 薄弱</div>
            <div v-if="chatStore.profile.knowledge_base?.weak?.length" class="pv-tags">
              <el-tag v-for="k in chatStore.profile.knowledge_base.weak" :key="k" size="small" type="warning" effect="plain">{{ k }}</el-tag>
            </div>
            <span v-else class="pv-empty-small">暂无</span>
          </div>
          <div class="pv-kb-col">
            <div class="pv-kb-head untouched">未接触</div>
            <div v-if="chatStore.profile.knowledge_base?.untouched?.length" class="pv-tags">
              <el-tag v-for="k in chatStore.profile.knowledge_base.untouched" :key="k" size="small" type="info" effect="plain">{{ k }}</el-tag>
            </div>
            <span v-else class="pv-empty-small">暂无</span>
          </div>
        </div>
      </div>

      <div class="pv-divider"></div>

      <!-- 兴趣方向 -->
      <div class="pv-section" v-if="chatStore.profile.interests?.length">
        <h3 class="pv-section-title">兴趣方向</h3>
        <div class="pv-tags">
          <el-tag v-for="int in chatStore.profile.interests" :key="int" style="margin:0 6px 6px 0" type="primary" effect="plain">{{ int }}</el-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import RadarChart from '@/components/RadarChart.vue'
import { User, ChatDotSquare, Back, Edit } from '@element-plus/icons-vue'
import { profileApi } from '@/api'

const router = useRouter()
const chatStore = useChatStore()

const legendColors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6', '#f97316']

const isEditing = ref(false)
const editForm = ref({
  name: '',
  grade: '',
  major: '',
  cognitive_style: '',
  preferred_pace: '',
})

watch(() => chatStore.profile, (profile) => {
  if (profile) {
    editForm.value = {
      name: profile.name || '',
      grade: profile.grade || '',
      major: profile.major || '',
      cognitive_style: profile.cognitive_style || '',
      preferred_pace: profile.preferred_pace || '',
    }
  }
}, { immediate: true })

onMounted(() => { chatStore.fetchProfile() })

function startChat() {
  chatStore.sendMessage('我想完善我的学习画像', 'profile')
  router.push('/')
}

function toggleEdit() {
  isEditing.value = !isEditing.value
  if (isEditing.value && chatStore.profile) {
    editForm.value = {
      name: chatStore.profile.name || '',
      grade: chatStore.profile.grade || '',
      major: chatStore.profile.major || '',
      cognitive_style: chatStore.profile.cognitive_style || '',
      preferred_pace: chatStore.profile.preferred_pace || '',
    }
  }
}

async function saveProfile() {
  try {
    await profileApi.updateProfile(chatStore.userId, editForm.value)
    await chatStore.fetchProfile()
    isEditing.value = false
    alert('保存成功！')
  } catch (err) {
    console.error('保存失败:', err)
    alert('保存失败，请重试')
  }
}
</script>

<style scoped>
.profile-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f6fa;
}
.pv-header {
  padding: 20px 28px 0;
  flex-shrink: 0;
}
.pv-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pv-title-row h2 {
  font-size: 18px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pv-actions { display: flex; gap: 8px; }

/* 可滚动主体 */
.pv-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 28px 32px;
}

/* 空状态 */
.pv-empty {
  text-align: center;
  padding: 80px 20px;
  color: #9ca3af;
  flex: 1;
}
.pv-empty h3 { margin: 12px 0 6px; color: #374151; }
.pv-empty p { margin-bottom: 20px; font-size: 14px; }
.pv-empty-small { font-size: 13px; color: #d1d5db; }

/* 分区 */
.pv-section { padding: 4px 0; }
.pv-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 12px;
}
.pv-divider {
  height: 1px;
  background: #e5e7eb;
  margin: 16px 0;
}

/* 基本信息网格 */
.pv-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}
.pv-info-item {
  background: #fff;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #eef0f4;
}
.pv-label { font-size: 11px; color: #9ca3af; display: block; margin-bottom: 2px; }
.pv-value { font-size: 14px; color: #1f2937; font-weight: 500; }
.pv-input { width: 100%; }
.pv-edit-actions { display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end; }

/* 雷达图行 */
.pv-radar-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.pv-legend-list { flex: 1; min-width: 140px; display: flex; flex-direction: column; gap: 4px; }
.pv-legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; }
.pv-legend-dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.pv-legend-name { color: #374151; min-width: 52px; font-size: 11px; flex-shrink: 0; }
.pv-legend-score { color: #6366f1; font-weight: 700; font-size: 12px; min-width: 20px; text-align: right; flex-shrink: 0; }
.pv-legend-desc { color: #9ca3af; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 知识基础 */
.pv-kb-row { display: flex; gap: 16px; flex-wrap: wrap; }
.pv-kb-col { flex: 1; min-width: 140px; }
.pv-kb-head { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.pv-kb-head.mastered { color: #10b981; }
.pv-kb-head.weak { color: #f59e0b; }
.pv-kb-head.untouched { color: #6b7280; }
.pv-tags { display: flex; flex-wrap: wrap; gap: 4px; }
</style>
