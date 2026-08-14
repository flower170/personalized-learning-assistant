<template>
  <div class="agents-view">
    <div class="page-header">
      <h2><el-icon><Connection /></el-icon> 我的智能体</h2>
      <el-button size="small" @click="$router.push('/')">
        <el-icon><Back /></el-icon> 返回聊天
      </el-button>
    </div>

    <div class="agents-grid">
      <el-card
        v-for="agent in agents"
        :key="agent.name"
        shadow="never"
        class="agent-card"
        @click="useAgent(agent)"
      >
        <div class="agent-icon" :style="{ background: agent.color + '18' }">
          <el-icon :size="28" :color="agent.color"><component :is="agent.icon" /></el-icon>
        </div>
        <h3 class="agent-name">{{ agent.label }}</h3>
        <p class="agent-desc">{{ agent.desc }}</p>
        <div class="agent-stages" v-if="agent.stages">
          <el-tag v-for="s in agent.stages" :key="s" size="small" effect="plain" type="info">{{ s }}</el-tag>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { User, Reading, MapLocation, ChatLineSquare, Connection, Back } from '@element-plus/icons-vue'

const router = useRouter()
const chatStore = useChatStore()

const agents = [
  { name: 'profile', label: '学习画像助手', icon: User, color: '#6366f1',
    desc: '通过自然对话采集你的学习信息，构建≥6维度的动态学生画像',
    stages: ['基础信息', '学情问询', '维度采集', '画像生成'] },
  { name: 'resource', label: '学习资源助手', icon: Reading, color: '#10b981',
    desc: '多智能体协同生成课程讲解、思维导图、练习题、代码案例等',
    stages: ['画像分析', '知识检索', '逐类生成', '后处理'] },
  { name: 'plan', label: '路径规划助手', icon: MapLocation, color: '#f59e0b',
    desc: '基于你的画像和时间约束，制定个性化分阶段学习路径',
    stages: ['画像分析', '路径生成', '任务拆分'] },
  { name: 'tutor', label: '智能辅导助手', icon: ChatLineSquare, color: '#ec4899',
    desc: '即时答疑解惑，结合RAG知识库提供多模态解答',
    stages: ['问题分析', '知识检索', '解答生成'] },
]

function useAgent(agent) {
  const prompts = {
    profile: '我想完善我的学习画像',
    resource: '帮我生成学习资料',
    plan: '帮我制定学习路径',
    tutor: '你好，我有一个问题想请教',
  }
  chatStore.sendMessage(prompts[agent.name], agent.name)
  router.push('/')
}
</script>

<style scoped>
.agents-view {
  padding: 24px 32px;
  overflow-y: auto;
  height: 100%;
  background: #f5f6fa;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.page-header h2 {
  font-size: 20px;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.agent-card {
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #eef0f4;
}
.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.06);
  border-color: #c7d2fe;
}
.agent-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.agent-name { font-size: 16px; font-weight: 600; color: #1f2937; margin-bottom: 6px; }
.agent-desc { font-size: 13px; color: #6b7280; line-height: 1.5; margin-bottom: 10px; }
.agent-stages { display: flex; gap: 4px; flex-wrap: wrap; }
</style>
