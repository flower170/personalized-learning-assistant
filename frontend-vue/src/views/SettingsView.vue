<template>
  <div class="settings-view">
    <div class="page-header">
      <h2><el-icon><Setting /></el-icon> {{ t('settings.title') }}</h2>
      <el-button size="small" @click="$router.push('/')">
        <el-icon><Back /></el-icon> {{ t('settings.back_to_chat') }}
      </el-button>
    </div>

    <div class="setting-section">
      <h3 class="section-title">🌐 {{ t('settings.language') }}</h3>
      <p class="section-desc">{{ t('settings.language_description') }}</p>
      <div class="language-card">
        <div class="language-label">
          <span class="label-title">{{ t('settings.interface_language') }}</span>
          <span class="label-desc">{{ t('settings.language_hint') }}</span>
        </div>
        <div class="language-selector">
          <button
            v-for="lang in chatStore.languageOptions"
            :key="lang.value"
            class="lang-btn"
            :class="{ active: chatStore.language === lang.value }"
            @click="changeLanguage(lang.value)"
          >
            {{ lang.label }}
          </button>
        </div>
      </div>
    </div>

    <div class="setting-section">
      <h3 class="section-title">🎨 {{ t('settings.theme') }}</h3>
      <p class="section-desc">{{ t('settings.theme_description') }}</p>
      <div class="theme-grid">
        <div
          v-for="theme in chatStore.themeOptions"
          :key="theme.value"
          class="theme-card"
          :class="{ active: chatStore.theme === theme.value }"
          @click="changeTheme(theme.value)"
        >
          <div class="theme-preview" :class="theme.value">
            <div class="preview-header">
              <div class="preview-dot"></div>
              <div class="preview-dot"></div>
              <div class="preview-dot"></div>
            </div>
            <div class="preview-body">
              <div class="preview-line line-1"></div>
              <div class="preview-line line-2"></div>
              <div class="preview-line line-3"></div>
              <div class="preview-line line-4"></div>
              <div class="preview-bar"></div>
            </div>
          </div>
          <div class="theme-info">
            <span class="theme-name">{{ getThemeLabel(theme.value) }}</span>
            <span v-if="chatStore.theme === theme.value" class="check-icon">✓</span>
          </div>
        </div>
      </div>
    </div>

    <div class="setting-section">
      <h3 class="section-title">{{ t('settings.personal_info') }}</h3>
      <div class="info-form">
        <el-form label-width="100px" size="small" class="form-section">
          <el-form-item :label="t('settings.student_id')">
            <el-input v-model="chatStore.userId" disabled style="width:200px" />
          </el-form-item>
          <el-form-item :label="t('settings.name')">
            <el-input v-model="localName" :placeholder="t('settings.name')" style="width:200px" />
          </el-form-item>
          <el-form-item :label="t('settings.grade')">
            <el-select v-model="localGrade" style="width:200px">
              <el-option label="大一" value="大一" />
              <el-option label="大二" value="大二" />
              <el-option label="大三" value="大三" />
              <el-option label="大四" value="大四" />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('settings.major')">
            <el-input v-model="localMajor" :placeholder="t('settings.major')" style="width:200px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveSettings">{{ t('settings.save_settings') }}</el-button>
          </el-form-item>
        </el-form>

        <div class="form-divider"></div>

        <el-form label-width="100px" size="small" class="form-section">
          <div class="section-header">
            <span class="section-icon">🔐</span>
            <span class="section-label">密码修改</span>
          </div>
          <el-form-item label="原密码">
            <el-input v-model="oldPassword" type="password" placeholder="原密码" style="width:200px" />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input v-model="newPassword" type="password" placeholder="新密码（至少6位）" style="width:200px" />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input v-model="confirmPassword" type="password" placeholder="确认新密码" style="width:200px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleChangePassword">修改密码</el-button>
          </el-form-item>
        </el-form>

        <div class="form-divider"></div>

        <el-form label-width="100px" size="small" class="form-section">
          <div class="section-header">
            <span class="section-icon">🗑️</span>
            <span class="section-label" style="color:var(--accent-danger)">用户注销</span>
          </div>
          <p class="delete-warning">⚠️ 注销账号将永久删除所有数据，包括学习记录、会话历史和个人画像，请谨慎操作</p>
          <el-form-item label="密码">
            <el-input v-model="deletePassword" type="password" placeholder="请输入密码以确认" style="width:200px" />
          </el-form-item>
          <el-form-item>
            <el-button type="danger" @click="handleDeleteAccount">确认注销账号</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <div class="setting-section">
      <h3 class="section-title">数据报告</h3>
      <p class="section-desc">生成并导出学习数据报告，包含画像、学习进度和会话记录</p>
      <div class="report-card">
        <div class="report-info">
          <div class="report-icon"></div>
          <div class="report-text">
            <span class="report-title">学习数据报告</span>
            <span class="report-desc">包含学生画像、能力雷达图、知识掌握情况、学习路径进度和近期会话记录</span>
          </div>
        </div>
        <el-button type="primary" @click="goToReport">
          <el-icon><Document /></el-icon> 生成报告
        </el-button>
      </div>
    </div>

    <div class="setting-section">
      <h3 class="section-title">⚙️ {{ t('settings.system_info') }}</h3>
      <el-descriptions :column="1" border size="small" class="system-info">
        <el-descriptions-item :label="t('settings.version')">2.0.0</el-descriptions-item>
        <el-descriptions-item :label="t('settings.backend_url')">{{ backendUrl }}</el-descriptions-item>
        <el-descriptions-item :label="t('settings.cache_status')">
          <el-tag size="small" type="success" effect="plain">{{ t('common.running') }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { Setting, Back, Document } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const chatStore = useChatStore()
const backendUrl = window.location.protocol + '//' + window.location.hostname + ':8000'

const localName = ref(chatStore.userName || '')
const localGrade = ref(chatStore.userGrade || '大一')
const localMajor = ref(chatStore.userMajor || '')

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const deletePassword = ref('')

function t(path) {
  return chatStore.getLocale(path)
}

function changeLanguage(lang) {
  chatStore.setLanguage(lang)
  ElMessage.success(`语言已切换为 ${lang === 'zh-CN' ? '中文' : 'English'}`)
}

function changeTheme(theme) {
  chatStore.setTheme(theme)
  const labels = {
    default: '默认主题',
    cream: '奶油主题',
    dark: '深色主题',
    glass: '琉璃主题',
  }
  ElMessage.success(`主题已切换为 ${labels[theme] || theme}`)
}

function getThemeLabel(value) {
  const labels = {
    default: '默认',
    cream: '奶油',
    dark: '深色',
    glass: '琉璃',
  }
  return labels[value] || value
}

function saveSettings() {
  chatStore.userName = localName.value
  chatStore.userGrade = localGrade.value
  chatStore.userMajor = localMajor.value
  ElMessage.success(t('common.success') || '设置已保存')
}

function goToReport() {
  router.push(`/report/${chatStore.userId}`)
}

function handleChangePassword() {
  if (!oldPassword.value) {
    ElMessage.warning('请输入原密码')
    return
  }
  if (!newPassword.value) {
    ElMessage.warning('请输入新密码')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  const result = chatStore.changePassword(oldPassword.value, newPassword.value)
  if (result.success) {
    ElMessage.success(result.message)
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } else {
    ElMessage.error(result.message)
  }
}

function handleDeleteAccount() {
  if (!deletePassword.value) {
    ElMessage.warning('请输入密码以确认注销')
    return
  }
  ElMessageBox.confirm(
    '⚠️ 警告：注销账号将永久删除所有学习数据，此操作不可撤销！',
    '确认注销',
    {
      confirmButtonText: '确认注销',
      cancelButtonText: '取消',
      type: 'warning',
      danger: true,
    }
  ).then(() => {
    const result = chatStore.deleteAccount(deletePassword.value)
    if (result.success) {
      ElMessage.success(result.message)
      router.push('/login')
    } else {
      ElMessage.error(result.message)
    }
  }).catch(() => {})
}
</script>

<style scoped>
.settings-view {
  padding: 24px 32px;
  overflow-y: auto;
  height: 100%;
  background: var(--bg-secondary);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.page-header h2 {
  font-size: 20px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.setting-section {
  margin-bottom: 28px;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.section-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 16px;
}

.language-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
}
.language-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.label-title {
  font-size: 14px;
  color: var(--text-primary);
  font-weight: 500;
}
.label-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.language-selector {
  display: flex;
  gap: 6px;
}
.lang-btn {
  padding: 6px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-primary);
  background: transparent;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.lang-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.lang-btn.active {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}

.theme-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.theme-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: var(--bg-card);
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.theme-card:hover {
  border-color: var(--accent-primary);
}
.theme-card.active {
  border-color: var(--accent-primary);
}
.theme-preview {
  width: 100%;
  height: 100px;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 12px;
  box-sizing: border-box;
}
.theme-preview.default {
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}
.theme-preview.default .preview-header { background: #fff; }
.theme-preview.default .preview-dot:nth-child(1) { background: #ef4444; }
.theme-preview.default .preview-dot:nth-child(2) { background: #eab308; }
.theme-preview.default .preview-dot:nth-child(3) { background: #22c55e; }
.theme-preview.default .preview-line { background: #e2e8f0; }
.theme-preview.default .preview-bar { background: #3b82f6; }

.theme-preview.cream {
  background: linear-gradient(180deg, #fefcf6 0%, #fdf8ed 100%);
}
.theme-preview.cream .preview-header { background: #fff; }
.theme-preview.cream .preview-dot:nth-child(1) { background: #ef4444; }
.theme-preview.cream .preview-dot:nth-child(2) { background: #eab308; }
.theme-preview.cream .preview-dot:nth-child(3) { background: #22c55e; }
.theme-preview.cream .preview-line { background: #f5e6c8; }
.theme-preview.cream .preview-bar { background: #d97706; }

.theme-preview.dark {
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
}
.theme-preview.dark .preview-header { background: #374151; }
.theme-preview.dark .preview-dot:nth-child(1) { background: #ef4444; }
.theme-preview.dark .preview-dot:nth-child(2) { background: #eab308; }
.theme-preview.dark .preview-dot:nth-child(3) { background: #22c55e; }
.theme-preview.dark .preview-line { background: #4b5563; }
.theme-preview.dark .preview-bar { background: #d97706; }

.theme-preview.glass {
  background: linear-gradient(180deg, #1e1b4b 0%, #0f0d24 100%);
}
.theme-preview.glass .preview-header { background: #312e81; }
.theme-preview.glass .preview-dot:nth-child(1) { background: #ef4444; }
.theme-preview.glass .preview-dot:nth-child(2) { background: #eab308; }
.theme-preview.glass .preview-dot:nth-child(3) { background: #22c55e; }
.theme-preview.glass .preview-line { background: #4c1d95; }
.theme-preview.glass .preview-bar { background: #a855f7; }

.preview-header {
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 10px;
}
.preview-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.preview-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.preview-line {
  height: 6px;
  border-radius: 3px;
}
.preview-line.line-1 { width: 100%; }
.preview-line.line-2 { width: 85%; }
.preview-line.line-3 { width: 70%; }
.preview-line.line-4 { width: 90%; }
.preview-bar {
  height: 4px;
  width: 30%;
  border-radius: 2px;
  margin-top: 8px;
}
.theme-info {
  display: flex;
  align-items: center;
  gap: 6px;
}
.theme-name {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}
.check-icon {
  font-size: 12px;
  color: var(--accent-primary);
  font-weight: bold;
}

.info-form {
  padding: 14px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
}
.form-section {
  margin-bottom: 0;
}
.form-section :deep(.el-form-item) {
  margin-bottom: 10px;
}
.form-section :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}
.form-divider {
  height: 1px;
  background: var(--border-primary);
  margin: 12px 0;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.section-icon {
  font-size: 15px;
}
.delete-warning {
  font-size: 11px;
  color: var(--accent-danger);
  margin-bottom: 8px;
  padding: 6px 10px;
  background: rgba(239, 68, 68, 0.05);
  border-radius: 6px;
}
.system-info {
  background: var(--bg-card);
  border-radius: 12px;
}

.report-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--bg-card);
  border: 1px solid var(--border-primary);
  border-radius: 12px;
}
.report-info {
  display: flex;
  align-items: center;
  gap: 12px;
}
.report-icon {
  font-size: 28px;
}
.report-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.report-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.report-desc {
  font-size: 12px;
  color: var(--text-muted);
}

</style>