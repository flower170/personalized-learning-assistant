<template>
  <div class="chat-view">
    <div class="chat-content-wrapper">
      <!-- 顶部标题栏 -->
      <ChatHeader />
      <!-- 消息区域 -->
      <ChatMessages @send="onQuickSend" @open-path-wizard="openPathWizard" @open-skill-gap="openSkillGap" />
      <!-- 输入区域 -->
      <ChatInput ref="chatInputRef" />

      <!-- 悬浮「引导」入口：未全部完成时可重开引导弹窗 -->
      <button
        v-if="chatStore.onboarding && !chatStore.onboarding.all_done && !showOnboarding"
        class="ob-fab"
        title="新手引导"
        @click="showOnboarding = true"
      >
        <span class="ob-fab-text">引导</span>
      </button>

      <!-- 首次登录引导弹窗：账号未全部完成时弹出一次，点步骤→交接给聊天/画像页 -->
      <OnboardingDialog
        v-model="showOnboarding"
        :onboarding="chatStore.onboarding"
        @start-profile="onStartProfile"
        @start-path="onStartPath"
        @start-resource="onStartResource"
        @skip="chatStore.skipOnboarding"
        @skip-all="onSkipAll"
      />

      <!-- 路径规划弹窗：先问科目 + 每天时间 + 期望周期，再交给聊天内向导 -->
      <PathStartDialog
        v-model="showPathStart"
        :pre-topic="pathPreTopic"
        @start="onPathStartConfirm"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import ChatHeader from '@/components/ChatHeader.vue'
import ChatMessages from '@/components/ChatMessages.vue'
import ChatInput from '@/components/ChatInput.vue'
import OnboardingDialog from '@/components/OnboardingDialog.vue'
import PathStartDialog from '@/components/PathStartDialog.vue'

const router = useRouter()
const chatStore = useChatStore()
const chatInputRef = ref(null)
const showOnboarding = ref(false)
const showPathStart = ref(false)
const pathPreTopic = ref('')

function onQuickSend(text, type) {
  chatStore.sendMessage(text, type)
}

/** 路径弹窗防重入锁：openPathWizard 有 3 个触发源（欢迎页芯片 / 引导弹窗 / pathWizardRequest watch），
 *  叠加触发会弹两个窗。已有弹窗打开时忽略一切重复触发，保证只弹一次。 */
let pathPopupOpening = false

/** 学习路径入口：打开 PathStartDialog（先问科目 + 每天时间 + 期望周期）→ 拿到结果交给聊天内向导 */
function openPathWizard(preTopic = '') {
  if (pathPopupOpening) return
  pathPopupOpening = true
  pathPreTopic.value = (preTopic || '').trim()
  showPathStart.value = true
  // 弹窗关闭（确认/取消）后放锁，避免 v-model 关闭时序抢锁
  setTimeout(() => { pathPopupOpening = false }, 300)
}

/** PathStartDialog 确认：带上时间投入发起路径规划 */
function onPathStartConfirm({ topic, dailyHours, cycle }) {
  if (!topic) return
  chatStore.pathStart(topic, { dailyHours, cycle })
}

function openSkillGap() {
  router.push('/skill-gap')
}

/** ===== 引导弹窗交接：关闭弹窗 → 对应功能在聊天/画像页接手 ===== */
function onStartProfile() {
  // 画像也在聊天框完成，保持「三大功能都在聊天框」的体验（不跳独立画像页）
  showOnboarding.value = false
  chatStore.sendMessage('我想完善我的学习画像', 'profile')
}
function onStartPath() {
  showOnboarding.value = false
  openPathWizard()
}
function onStartResource() {
  // 学习资源 = 聊天自由使用：关弹窗，直接跟 AI 说要什么资料即可
  showOnboarding.value = false
}
async function onSkipAll() {
  const ob = chatStore.onboarding || {}
  if (!(ob.profile?.done)) await chatStore.skipOnboarding('profile')
  if (!(ob.path?.done)) await chatStore.skipOnboarding('path')
}

/** 聊天里发起学习路径（打字 / 按钮）→ 统一走聊天内向导 */
watch(() => chatStore.pathWizardRequest, (req) => {
  if (!req) return
  chatStore.pathWizardRequest = null
  openPathWizard(req.topic)
})

/** 全部完成（含全部跳过）→ 自动关掉引导弹窗 */
watch(() => chatStore.onboarding?.all_done, (done) => {
  if (done) showOnboarding.value = false
})

/** 页面刷新/初次进入且保持登录 → 拉引导状态；账号未全部完成则弹窗一次 */
onMounted(async () => {
  if (!chatStore.isLoggedIn) return
  await chatStore.fetchOnboarding()
  if (chatStore.onboarding && !chatStore.onboarding.all_done) {
    showOnboarding.value = true
  }
})
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: 0;
}
.chat-content-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  position: relative;
}

/* 悬浮引导按钮 */
.ob-fab {
  position: absolute;
  right: 18px;
  bottom: 92px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 9px 14px;
  border: 1px solid #c7d2fe;
  border-radius: 24px;
  background: #fff;
  box-shadow: 0 3px 10px rgba(79, 70, 229, 0.18);
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  color: #4338ca;
  z-index: 20;
  transition: all 0.15s ease;
}
.ob-fab:hover { background: #eef2ff; transform: translateY(-1px); }
.ob-fab-text { font-weight: 600; }
</style>
