<template>
  <div class="chat-input-area">
    <div class="chat-input-wrapper">
      <!-- 输入行 -->
      <div class="input-row">
        <div class="input-container">
          <!-- 快捷操作按钮 -->
          <div class="input-actions-left">
            <el-tooltip content="上传文件" placement="top">
              <el-upload
                :show-file-list="false"
                :before-upload="handleUpload"
                accept=".pdf,.doc,.docx,.md,.txt"
                class="upload-btn-wrapper"
              >
                <button class="icon-btn upload-icon-btn">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                  </svg>
                </button>
              </el-upload>
            </el-tooltip>
          </div>

          <!-- 输入框 -->
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="1"
            :disabled="chatStore.loading"
            placeholder="输入你的学习需求..."
            @keydown.enter.prevent="handleSend"
            resize="none"
            class="chat-input"
            ref="inputRef"
            :autosize="{ minRows: 1, maxRows: 6 }"
          />

          <!-- 右侧操作 -->
          <div class="input-actions-right">
            <!-- 模式选择 -->
            <el-tooltip content="切换模式" placement="top">
              <button class="icon-btn mode-btn" @click="showModeMenu = !showModeMenu">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                </svg>
              </button>
            </el-tooltip>

            <!-- 发送按钮 -->
            <button
              class="send-btn"
              :class="{ active: inputText.trim() }"
              :disabled="!inputText.trim() || chatStore.loading"
              @click="handleSend"
            >
              <svg v-if="!chatStore.loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
              <svg v-else class="spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="32">
                  <animate attributeName="stroke-dashoffset" values="32;0" dur="0.8s" repeatCount="indefinite"/>
                </circle>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- 模式选择浮层 -->
      <transition name="slide-down">
        <div v-if="showModeMenu" class="mode-menu">
          <button
            v-for="m in modes"
            :key="m.key"
            class="mode-item"
            :class="{ active: currentMode === m.key }"
            @click="selectMode(m.key)"
          >
            <span class="mode-icon">{{ m.icon }}</span>
            <span class="mode-label">{{ m.label }}</span>
          </button>
        </div>
      </transition>

      <!-- 底部提示 -->
      <div class="input-footer">
        <span class="footer-text">{{ currentMode === 'auto' ? '智能模式 · 自动识别意图' : modeLabels[currentMode] }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const inputText = ref('')
const inputRef = ref(null)
const currentMode = ref('auto')
const showModeMenu = ref(false)

const modes = [
  { key: 'auto', icon: '🤖', label: '智能模式' },
  { key: 'profile', icon: '📋', label: '学习画像' },
  { key: 'resource', icon: '📚', label: '学习资料' },
  { key: 'plan', icon: '🗺️', label: '学习路径' },
  { key: 'tutor', icon: '💡', label: '辅导答疑' },
]

const modeLabels = {
  auto: '自动识别',
  profile: '完善画像',
  resource: '生成资料',
  plan: '规划路径',
  tutor: '答疑解惑',
}

function selectMode(key) {
  currentMode.value = key
  showModeMenu.value = false
  inputRef.value?.focus()
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.loading) return
  inputText.value = ''
  showModeMenu.value = false
  const explicitType = currentMode.value === 'auto' ? '' : currentMode.value
  chatStore.sendMessage(text, explicitType)
}

function handleUpload(file) {
  const formData = new FormData()
  formData.append('file', file)
  chatStore.setFileUploading(true)
  fetch('/api/file/upload', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(data => {
      chatStore.setFileUploading(false)
      if (data.success) {
        chatStore.setTempFileId(data.temp_file_id)
        chatStore.currentIntent = ''  // 清除之前的意图延续
        chatStore.addUploadedFile({
          id: data.temp_file_id,
          name: file.name,
          ext: file.name.split('.').pop(),
          size: (data.size / 1024).toFixed(1) + 'KB',
          status: 'vectored',
        })
        // ✅ 不上传后自动发送消息 — 只显示提示，让用户自己输入需求
        chatStore.addSystemMessage(`📎 已上传文件: **${file.name}**，上传成功。现在你可以告诉我需要基于这份文档生成什么学习资料。`)
      } else {
        chatStore.addSystemMessage(`❌ 文件上传失败: ${data.msg || '未知错误'}`)
      }
    })
    .catch((e) => {
      chatStore.setFileUploading(false)
      chatStore.addSystemMessage(`❌ 文件上传失败: ${e.message}`)
    })
  return false
}
</script>

<style scoped>
.chat-input-area {
  padding: 8px 24px 12px;
  border-top: 1px solid var(--border-primary);
  background: var(--bg-primary);
  flex-shrink: 0;
  position: relative;
}

.input-row {
  width: 100%;
}

.input-container {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  background: var(--bg-secondary);
  border: 1.5px solid var(--border-primary);
  border-radius: 16px;
  padding: 4px 4px 4px 8px;
  transition: all 0.2s ease;
}
.input-container:focus-within {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
  background: var(--bg-primary);
}

.chat-input {
  flex: 1;
}
.chat-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 10px 4px;
  font-size: 14px;
  line-height: 1.5;
  min-height: 24px;
  color: var(--text-primary);
}
.chat-input :deep(.el-textarea__inner::placeholder) {
  color: var(--text-muted);
}

/* Icon Buttons */
.icon-btn {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  flex-shrink: 0;
}
.icon-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.input-actions-left, .input-actions-right {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-bottom: 2px;
}

/* Send Button */
.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: none;
  background: var(--border-secondary);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.send-btn.active {
  background: var(--accent-primary);
  box-shadow: 0 4px 12px rgba(99,102,241,0.3);
}
.send-btn.active:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 16px rgba(99,102,241,0.4);
}
.send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.spinner { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Mode Menu */
.mode-menu {
  display: flex;
  gap: 4px;
  padding: 8px 0;
  margin-top: 4px;
}
.mode-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-primary);
  background: var(--bg-primary);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s ease;
}
.mode-item:hover {
  border-color: var(--accent-primary);
  background: var(--accent-primary-light);
}
.mode-item.active {
  border-color: var(--accent-primary);
  background: var(--accent-primary-light);
  color: var(--accent-primary);
  font-weight: 600;
}
.mode-icon { font-size: 15px; }

/* Slide Down */
.slide-down-enter-active { transition: all 0.2s ease-out; }
.slide-down-leave-active { transition: all 0.15s ease-in; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-8px); }

/* Footer */
.input-footer {
  display: flex;
  justify-content: center;
  margin-top: 6px;
}
.footer-text {
  font-size: 11px;
  color: var(--text-muted);
}
</style>
