<template>
  <el-dialog
    :model-value="modelValue"
    :close-on-click-modal="false"
    width="440px"
    align-center
    class="ob-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="ob-dialog-title">
        <div>
          <div class="ob-dialog-h1">三步开启个性化学习</div>
          <div class="ob-dialog-sub">先画像 → 再路径 → 自由使用资源</div>
        </div>
      </div>
    </template>

    <div class="ob-steps">
      <div
        v-for="(step, i) in steps"
        :key="step.key"
        class="ob-step"
        :class="`ob-${step.status}`"
      >
        <span class="ob-step-num">{{ i + 1 }}</span>
        <div class="ob-step-main">
          <div class="ob-step-label">{{ step.label }}</div>
          <div class="ob-step-desc">{{ step.desc }}</div>
        </div>
        <div class="ob-step-actions">
          <span v-if="step.status === 'done'" class="ob-tag ob-tag-done">✅ 已完成</span>
          <span v-else-if="step.status === 'skipped'" class="ob-tag ob-tag-skip">⏭ 已跳过</span>
          <template v-else-if="step.status === 'active'">
            <button class="ob-btn ob-btn-start" @click="startStep(step)">{{ step.startLabel }}</button>
            <button class="ob-btn ob-btn-skip" @click="emit('skip', step.key)">跳过</button>
          </template>
          <span v-else class="ob-tag ob-tag-todo">待开始</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button text size="small" @click="emit('skip-all')">全部跳过</el-button>
      <el-button type="primary" size="small" @click="emit('update:modelValue', false)">知道了</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** 弹窗是否显示（v-model） */
  modelValue: { type: Boolean, default: false },
  /** GET /onboarding/{student_id} 返回的完整状态对象 */
  onboarding: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue', 'start-profile', 'start-path', 'start-resource', 'skip', 'skip-all'])

/** 三步状态（与引导口径一致：done/skipped 优先，其次 active=当前步，其余 todo） */
const steps = computed(() => {
  const ob = props.onboarding || {}
  const profile = ob.profile || {}
  const path = ob.path || {}
  const current = ob.current_step || 'profile'

  function statusOf(done, skipped, activeKey) {
    if (done) return 'done'
    if (skipped) return 'skipped'
    if (current === activeKey) return 'active'
    return 'todo'
  }

  const profileStatus = statusOf(profile.done, profile.skipped, 'profile')
  const pathStatus = statusOf(path.done, path.skipped, 'path')

  return [
    {
      key: 'profile', label: '学习画像',
      desc: '聊聊基础情况，AI 个性化推荐', startLabel: '去构建',
      status: profileStatus,
    },
    {
      key: 'path', label: '学习路径',
      desc: '宏观阶段 + 每日计划，含官方练习', startLabel: '去规划',
      status: pathStatus,
    },
    {
      key: 'resource', label: '学习资源',
      desc: '讲义 / 思维导图 / 练习题 / 视频', startLabel: '去使用',
      status: (profileStatus === 'done' || profileStatus === 'skipped') && (pathStatus === 'done' || pathStatus === 'skipped')
        ? 'done' : 'todo',
    },
  ]
})

function startStep(step) {
  if (step.key === 'profile') emit('start-profile')
  else if (step.key === 'path') emit('start-path')
  else if (step.key === 'resource') emit('start-resource')
}
</script>

<style scoped>
.ob-dialog :deep(.el-dialog__header) { padding-bottom: 8px; }
.ob-dialog :deep(.el-dialog__body) { padding-top: 4px; }

.ob-dialog-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ob-dialog-emoji { font-size: 26px; }
.ob-dialog-h1 { font-size: 17px; font-weight: 700; color: #1f2937; }
.ob-dialog-sub { font-size: 12px; color: #9ca3af; margin-top: 2px; }

.ob-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ob-step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid #eef0f4;
  background: #fafbfc;
  transition: all 0.15s ease;
}
.ob-step-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ob-step-main { flex: 1; min-width: 0; }
.ob-step-label { font-size: 14px; font-weight: 600; color: #1f2937; }
.ob-step-desc { font-size: 12px; color: #9ca3af; margin-top: 2px; }
.ob-step-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

/* 状态配色 */
.ob-step.ob-active {
  background: #eef2ff;
  border-color: #c7d2fe;
}
.ob-step.ob-active .ob-step-num { background: #4f46e5; color: #fff; }
.ob-step.ob-active .ob-step-label { color: #4338ca; }
.ob-step.ob-done { background: #ecfdf5; border-color: #a7f3d0; }
.ob-step.ob-done .ob-step-num { background: #10b981; color: #fff; }
.ob-step.ob-done .ob-step-label { color: #065f46; }
.ob-step.ob-skipped { opacity: 0.7; }
.ob-step.ob-skipped .ob-step-num { background: #e2e8f0; color: #94a3b8; }
.ob-step.ob-skipped .ob-step-label { text-decoration: line-through; color: #94a3b8; }

.ob-tag { font-size: 12px; color: #64748b; white-space: nowrap; }
.ob-tag-done { color: #059669; }
.ob-tag-skip { color: #94a3b8; }
.ob-tag-todo { color: #9ca3af; }

.ob-btn {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}
.ob-btn-start { background: #4f46e5; color: #fff; border: 1px solid #4f46e5; }
.ob-btn-start:hover { background: #4338ca; }
.ob-btn-skip { background: transparent; color: #9ca3af; border: 1px solid #d1d5db; }
.ob-btn-skip:hover { background: #f3f4f6; color: #6b7280; }
</style>
