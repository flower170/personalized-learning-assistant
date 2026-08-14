<template>
  <div class="chat-messages" ref="msgContainer">
    <!-- 空状态欢迎页 -->
    <div v-if="chatStore.messages.length === 0" class="welcome">
      <div class="welcome-icon">
        <el-icon :size="48" color="#c7d2fe"><MagicStick /></el-icon>
      </div>
      <h2 class="welcome-title">你好！我是你的 AI 学习助手</h2>
      <p class="welcome-desc">
        我可以帮你构建学习画像、生成学习资料、制定学习路径
      </p>
      <div class="welcome-suggestions">
        <button
          v-for="tip in welcomeTips"
          :key="tip.label"
          class="suggestion-btn"
          @click="handleTipClick(tip)"
        >
          <el-icon :size="16" style="margin-right:4px">
            <component :is="tip.icon" />
          </el-icon>
          {{ tip.label }}
        </button>
      </div>
    </div>

    <!-- 消息列表 -->
    <template v-for="(msg, i) in chatStore.messages" :key="i">
      <!-- 只有正在生成的那条消息视为 streaming（隐藏答题卡预显/朗读按钮） -->
      <ChatBubble
        :msg="msg"
        :is-streaming="!!chatStore.streamingText && i === chatStore.messages.length - 1"
        @action="onExerciseAction"
      />
    </template>

    <!-- 【删减】移除流式输出气泡（ChatBubble），避免生成过程中渲染标题卡片/朗读按钮等冗余内容 -->
    <!-- 改为统一由下方加载提示框展示生成状态 -->

    <!-- 生成中占位（统一替代原流式输出气泡 + 加载提示） -->
    <div v-if="chatStore.loading || chatStore.streamingText" class="loading-indicator">
      <div class="msg-row assistant">
        <!-- 如果 streamingText 包含实际内容（非状态提示），直接展示内容 -->
        <div v-if="isRealContent" class="msg-bubble streaming-content">
          <div class="msg-content" v-html="renderedStreaming"></div>
          <span class="cursor-blink">|</span>
        </div>
        <!-- 否则显示加载动画 -->
        <div v-else class="msg-bubble generating">
          <span class="generating-text">
            <span v-for="(char, i) in generatingChars" :key="i" class="bounce-char" :style="{ animationDelay: (i * 0.08) + 's' }">{{ char }}</span>
          </span>
          <span class="cursor-blink">|</span>
        </div>
      </div>
    </div>

    <div ref="bottomRef" />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import { marked } from 'marked'
import ChatBubble from './ChatBubble.vue'
import { MagicStick, User, Reading, MapLocation, EditPen, DataAnalysis } from '@element-plus/icons-vue'

const emit = defineEmits(['send', 'open-path-wizard', 'open-skill-gap'])

const chatStore = useChatStore()
const msgContainer = ref(null)
const bottomRef = ref(null)

const welcomeTips = [
  { text: '我想完善我的学习画像', label: '📋 学习画像', icon: User, explicitType: 'profile' },
  // "学习资料"按钮行为同顶部"资料"按钮：触发大模型自我介绍 + 能力说明，而非自动生成资源
  { text: '', label: '📚 学习资料', icon: Reading, intro: true },
  // 学习路径统一走交互式向导：画像起步 → 信息不足提问 → 草案确认
  { text: '', label: '🗺️ 学习路径', icon: MapLocation, action: 'path-wizard' },
  { text: '', label: '📡 技能差距', icon: DataAnalysis, action: 'skill-gap' },
]

function handleTipClick(tip) {
  if (tip.intro) {
    chatStore.fetchAssistantIntro()
    return
  }
  if (tip.action === 'path-wizard') {
    emit('open-path-wizard')
    return
  }
  if (tip.action === 'skill-gap') {
    emit('open-skill-gap')
    return
  }
  emit('send', tip.text, tip.explicitType)
}

/** 加载动画文字拆分为逐字数组 */
const generatingChars = '正在生成内容中'.split('')

/** 判断 streamingText 是否为实际内容（而非状态提示） */
const isRealContent = computed(() => {
  const text = chatStore.streamingText
  if (!text) return false
  // 状态提示通常较短，包含"正在"/"已完成"等关键词
  const statusKeywords = ['正在', '已完成', '生成完成', '完成', '检索', '搜索', '加载', '规划']
  const isStatus = statusKeywords.some(kw => text.includes(kw)) && text.length < 60
  return !isStatus && text.length > 20
})

/** 渲染 streamingText 为 Markdown */
const renderedStreaming = computed(() => {
  const text = chatStore.streamingText
  if (!text) return ''
  try {
    return marked(text)
  } catch {
    return text
  }
})

/** 处理练习相关操作 */
function onExerciseAction(type, label, data) {
  const topic = getConversationTopic()

  if (type === 'exercise_modify') {
    // 修改题目 → 重新生成并替换
    chatStore.sendMessage(`我需要关于「${topic}」的练习题，稍微调整一下`, 'resource', 'exercise')
  } else if (type === 'exercise_more') {
    // 更多题目 → 追加生成
    chatStore.sendMessage(`继续出一些关于「${topic}」的练习题，不要重复`, 'resource', 'exercise')
  } else if (type === 'exercise_summary') {
    // 批改总结 → 直接调用批改接口，不发送用户消息
    chatStore.sendExerciseSummary(topic, data)
  }
}

/** 从对话历史提取知识点 */
function getConversationTopic() {
  for (let i = chatStore.messages.length - 1; i >= 0; i--) {
    const m = chatStore.messages[i]
    if (m.role === 'user' && m.content) return m.content.slice(0, 50)
  }
  return '这个知识点'
}

function scrollToBottom() {
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

watch(() => chatStore.messages.length, () => {
  window.speechSynthesis.cancel()
  nextTick(scrollToBottom)
})
watch(() => chatStore.streamingText, () => nextTick(scrollToBottom))
</script>

<style scoped>
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #fafbfc;
}
.welcome {
  text-align: center;
  padding: 80px 20px 40px;
}
.welcome-icon { margin-bottom: 16px; }
.welcome-title {
  font-size: 22px;
  color: #1f2937;
  margin-bottom: 8px;
  font-weight: 600;
}
.welcome-desc {
  font-size: 14px;
  color: #9ca3af;
  margin-bottom: 24px;
}
.welcome-suggestions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}
.suggestion-btn {
  display: inline-flex;
  align-items: center;
  padding: 10px 22px;
  font-size: 14px;
  border-radius: 20px;
  border: 1px solid #e0e0e0;
  background: #fff;
  color: #1f2937;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
  font-weight: 500;
}
.suggestion-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  background: #fafafa;
  border-color: #d0d0d0;
}
.loading-indicator { padding: 4px 0; }

/* 流式内容气泡 — 展示实际打字内容 */
.msg-bubble.streaming-content {
  background: #f5f7fa;
  color: #374151;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  padding: 12px 16px;
  max-width: 680px;
  width: fit-content;
  border: 1px solid #c7d2fe;
  line-height: 1.7;
  font-size: 14px;
}
.streaming-content .msg-content {
  display: inline;
}
.streaming-content .msg-content :deep(p) { margin: 0; display: inline; }
.streaming-content .cursor-blink {
  display: inline;
  margin-left: 1px;
}

/* 生成中气泡 — 保留原有消息气泡圆角、浅底色样式 */
.msg-bubble.generating {
  background: #f5f7fa;
  color: #374151;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 2px;
  border: 1px solid #eef0f4;
}
.generating-text {
  display: inline-flex;
  gap: 1px;
}
.bounce-char {
  display: inline-block;
  animation: charBounce 1.4s ease-in-out infinite;
}
.bounce-char:nth-child(7) { /* "中" 字节奏微调 */
  animation-delay: 0.48s !important;
}
@keyframes charBounce {
  0%, 40%, 100% { transform: translateY(0); }
  20% { transform: translateY(-4px); }
}

/* 光标闪烁 */
.cursor-blink {
  animation: blink 0.8s infinite;
  color: #6366f1;
  font-weight: bold;
  margin-left: 2px;
  font-size: 15px;
}
@keyframes blink { 50% { opacity: 0; } }
</style>
