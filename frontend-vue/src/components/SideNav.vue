<template>
  <aside class="side-nav" :class="{ collapsed: chatStore.sidebarCollapsed }">
    <div class="logo-area">
      <img src="/logo.jpg" class="logo-icon" alt="彩迹熊" />
      <transition name="fade">
        <span v-show="!chatStore.sidebarCollapsed" class="logo-text">彩迹熊</span>
      </transition>
    </div>

    <div class="new-chat-btn" v-show="!chatStore.sidebarCollapsed">
      <el-button type="primary" round size="small" style="width:100%" @click="chatStore.newSession(); $router.push('/')">
        <el-icon><Plus /></el-icon> {{ t('nav.new_chat') }}
      </el-button>
    </div>

    <el-menu
      :default-active="activeMenu"
      class="nav-menu"
      :collapse="chatStore.sidebarCollapsed"
      @select="onMenuSelect"
    >
      <el-menu-item index="home">
        <el-icon><ChatDotSquare /></el-icon>
        <template #title>{{ t('nav.home') }}</template>
      </el-menu-item>
      <el-menu-item index="profile">
        <el-icon><User /></el-icon>
        <template #title>{{ t('nav.profile') }}</template>
      </el-menu-item>
      <el-menu-item index="agents">
        <el-icon><Connection /></el-icon>
        <template #title>{{ t('nav.agents') }}</template>
      </el-menu-item>
      <el-menu-item index="knowledge">
        <el-icon><Reading /></el-icon>
        <template #title>{{ t('nav.knowledge') }}</template>
      </el-menu-item>
      <el-menu-item index="practice">
        <el-icon><Notebook /></el-icon>
        <template #title>{{ t('nav.practice') }}</template>
      </el-menu-item>
      <el-menu-item index="skill-gap">
        <el-icon><TrendCharts /></el-icon>
        <template #title>{{ t('nav.skill_gap') }}</template>
      </el-menu-item>
      <el-menu-item index="settings">
        <el-icon><Setting /></el-icon>
        <template #title>{{ t('nav.settings') }}</template>
      </el-menu-item>
    </el-menu>

    <div class="section-divider" v-show="!chatStore.sidebarCollapsed">
      <span class="divider-label">{{ t('nav.recent_sessions') }}</span>
    </div>
    <div class="session-list" v-show="!chatStore.sidebarCollapsed">
      <div
        v-for="sess in chatStore.sessions"
        :key="sess.id"
        class="session-item"
        :class="{ active: sess.id === chatStore.sessionId && $route.path === '/' }"
        @click="chatStore.switchSession(sess.id); $router.push('/')"
      >
        <el-icon class="sess-icon"><ChatLineSquare /></el-icon>
        <div class="sess-info">
          <span class="sess-title">{{ sess.title }}</span>
          <span class="sess-time">{{ sess.time }}</span>
        </div>
        <el-icon class="sess-delete" @click.stop="chatStore.removeSession(sess.id)">
          <Close />
        </el-icon>
      </div>
      <div v-if="chatStore.sessions.length === 0" class="no-sessions">
        {{ t('nav.no_sessions') }}
      </div>
    </div>

    <div class="user-area">
      <div class="user-main">
        <el-avatar :size="36" icon="User" class="user-avatar" />
        <transition name="fade">
          <div v-show="!chatStore.sidebarCollapsed" class="user-info">
            <div class="user-header">
              <span class="user-name">{{ chatStore.usernameDisplay }}</span>
              <el-select
                v-model="chatStore.userId"
                size="small"
                class="user-select"
                @change="chatStore.switchUser"
              >
                <el-option value="stu_001" label="stu_001" />
                <el-option value="demo" label="demo" />
              </el-select>
            </div>
            <div class="user-actions">
              <el-button text size="small" class="logout-btn" @click="handleLogout">
                <el-icon size="14"><SwitchButton /></el-icon>
                退出登录
              </el-button>
            </div>
          </div>
        </transition>
      </div>
      <el-button text class="collapse-btn" @click="chatStore.sidebarCollapsed = !chatStore.sidebarCollapsed">
        <el-icon><Fold /></el-icon>
      </el-button>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import {
  MagicStick, Plus, ChatDotSquare, User, Connection,
  Reading, Setting, ChatLineSquare, Close, Fold,
  SwitchButton, Notebook, TrendCharts,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const chatStore = useChatStore()

function t(path) {
  return chatStore.getLocale(path)
}

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/') return 'home'
  if (path.startsWith('/profile')) return 'profile'
  if (path.startsWith('/agents')) return 'agents'
  if (path.startsWith('/knowledge')) return 'knowledge'
  if (path.startsWith('/practice')) return 'practice'
  if (path.startsWith('/skill-gap')) return 'skill-gap'
  if (path.startsWith('/settings')) return 'settings'
  return 'home'
})

function onMenuSelect(index) {
  if (index === 'profile') router.push('/profile')
  else if (index === 'agents') router.push('/agents')
  else if (index === 'knowledge') router.push('/knowledge')
  else if (index === 'practice') router.push('/practice')
  else if (index === 'skill-gap') router.push('/skill-gap')
  else if (index === 'settings') router.push('/settings')
  else router.push('/')
}

function handleLogout() {
  chatStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.side-nav {
  width: 240px;
  min-width: 240px;
  height: 100%;
  flex-shrink: 0;
  background: var(--bg-primary);
  border-right: 1px solid var(--border-primary);
  display: flex;
  flex-direction: column;
  transition: width 0.25s ease, min-width 0.25s ease;
  overflow: hidden;
}
.side-nav.collapsed { width: 64px; min-width: 64px; }
.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 12px;
  border-bottom: 1px solid var(--border-primary);
}
.logo-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  object-fit: contain;
  flex-shrink: 0;
}
.logo-text { font-size: 16px; font-weight: 700; color: var(--text-primary); white-space: nowrap; }
.new-chat-btn { padding: 12px 14px 4px; }
.nav-menu { border-right: none !important; flex-shrink: 0; }
.nav-menu .el-menu-item {
  height: 42px; line-height: 42px; margin: 2px 8px;
  border-radius: 8px; font-size: 14px;
}
.nav-menu .el-menu-item.is-active { background: var(--accent-primary-light); color: var(--accent-primary); }
.nav-menu .el-menu-item:hover { background: var(--bg-tertiary); }
.section-divider { padding: 12px 16px 6px; }
.divider-label { font-size: 11px; color: var(--text-muted); font-weight: 500; letter-spacing: 0.5px; }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px; }
.session-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; margin: 2px 0; border-radius: 8px;
  cursor: pointer; transition: background 0.15s;
}
.session-item:hover { background: var(--bg-tertiary); }
.session-item.active { background: var(--accent-primary-light); }
.sess-icon { color: var(--text-muted); font-size: 16px; flex-shrink: 0; }
.sess-info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.sess-title { font-size: 13px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sess-time { font-size: 11px; color: var(--text-muted); }
.sess-delete { font-size: 13px; color: var(--border-secondary); opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.session-item:hover .sess-delete { opacity: 1; }
.sess-delete:hover { color: var(--accent-danger); }
.no-sessions { padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px; }
.user-area {
  display: flex; align-items: center; gap: 8px;
  padding: 14px; border-top: 1px solid var(--border-primary); flex-shrink: 0;
  background: var(--bg-primary);
}
.user-main {
  display: flex; align-items: center; gap: 10px;
  flex: 1; min-width: 0;
}
.user-avatar {
  background: var(--accent-primary) !important;
  flex-shrink: 0;
}
.user-info {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column; gap: 3px;
}
.user-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.user-name {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.user-select {
  flex-shrink: 0;
  .el-select__wrapper {
    border: none !important;
    background: var(--bg-tertiary) !important;
    border-radius: 6px !important;
    padding: 2px 8px !important;
  }
}
.collapse-btn { flex-shrink: 0; color: var(--text-muted); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>