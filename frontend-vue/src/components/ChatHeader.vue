<template>
  <header class="chat-header">
    <div class="header-left">
      <img src="/logo.jpg" class="header-icon" alt="彩迹熊" />
      <div class="header-info">
        <span class="header-title">彩迹熊 AI 学习助手</span>
      </div>
      <el-tag v-if="chatStore.loading" size="small" type="warning" effect="light" class="loading-tag">
        <span class="loading-dot"></span>
        处理中
      </el-tag>
    </div>
    <div class="header-right">
      <button class="header-action-btn" @click="quickAction('profile')" title="完善学习画像">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        <span>画像</span>
      </button>
      <button class="header-action-btn" @click="quickAction('resource')" title="生成学习资料">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
        </svg>
        <span>资料</span>
      </button>
      <button class="header-action-btn" @click="quickAction('plan')" title="制定学习路径">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
          <line x1="8" y1="2" x2="8" y2="18"></line>
          <line x1="16" y1="6" x2="16" y2="22"></line>
        </svg>
        <span>路径</span>
      </button>
      <div class="header-divider"></div>
      <el-select
        v-model="chatStore.userId"
        size="small"
        class="user-select"
        @change="chatStore.switchUser"
        placeholder="选择用户"
      >
        <el-option value="stu_001" label="学生 stu_001" />
        <el-option value="demo" label="学生 demo" />
      </el-select>
    </div>
  </header>
</template>

<script setup>
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

async function quickAction(type) {
  if (type === 'resource') {
    // 点击"资料"不再自动发送"帮我生成学习资料"，改为大模型自我介绍 + 能力说明
    await chatStore.fetchAssistantIntro()
    return
  }
  const prompts = {
    profile: '我想完善我的学习画像',
    plan: '帮我制定学习路径',
  }
  chatStore.sendMessage(prompts[type], type)
}
</script>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 24px;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-primary);
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex-shrink: 1;
  overflow: hidden;
}
.header-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  object-fit: contain;
}
.header-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.header-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.header-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.2;
}
.loading-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  animation: pulse 1.5s ease-in-out infinite;
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f59e0b;
  animation: pulse 1s ease-in-out infinite;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.header-action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  background: #fff;
  color: #1f2937;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s ease;
  white-space: nowrap;
  flex-shrink: 0;
}
.header-action-btn:hover {
  background: #f5f5f5;
  border-color: #d0d0d0;
}
.header-divider {
  width: 1px;
  height: 20px;
  background: var(--border-primary);
  margin: 0 6px;
}
.user-select {
  width: 130px;
}
.user-select :deep(.el-select__wrapper) {
  border: none;
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 2px 8px;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>
