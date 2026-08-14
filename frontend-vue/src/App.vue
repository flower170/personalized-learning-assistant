<template>
  <div v-if="isLoginPage" class="login-layout">
    <router-view />
  </div>
  <div v-else class="app-layout" :style="appStyle">
    <SideNav />
    <div class="main-area">
      <router-view class="router-view" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import SideNav from '@/components/SideNav.vue'

const route = useRoute()
const chatStore = useChatStore()

const isLoginPage = computed(() => route.path === '/login')

const appStyle = computed(() => ({
  background: 'var(--bg-secondary)',
}))
</script>

<style scoped>
.login-layout {
  width: 100vw;
  min-height: 100vh;
  min-height: 100dvh;
}
.app-layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
  width: 100vw;
  overflow: hidden;
}
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.router-view {
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>