<template>
  <el-dialog
    :model-value="modelValue"
    :close-on-click-modal="false"
    width="440px"
    align-center
    class="ps-dialog"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <template #header>
      <div class="ps-title">
        <div class="ps-h1">学习路径规划</div>
        <div class="ps-sub">告诉我学什么、每天能投入多少时间，我来按你的情况定制</div>
      </div>
    </template>

    <div class="ps-body">
      <div class="ps-field">
        <div class="ps-label">你想学什么科目？</div>
        <el-input
          v-model="topic"
          placeholder="如：SQL / Python数据分析 / 统计学 / C语言 / 数学…"
          clearable
          @keyup.enter="onStart"
        />
      </div>

      <div class="ps-field">
        <div class="ps-label">每天打算花多少时间？</div>
        <div class="ps-chips">
          <button
            v-for="c in dailyOptions"
            :key="c.value"
            type="button"
            class="ps-chip"
            :class="{ 'is-active': dailySel === c.value }"
            @click="pickDaily(c)"
          >{{ c.label }}</button>
        </div>
        <el-input
          v-model="dailyCustom"
          class="ps-custom"
          placeholder="自定义，如：1.5小时 / 45分钟"
          size="small"
          @input="dailySel = null"
        />
      </div>

      <div class="ps-field">
        <div class="ps-label">大概要多长时间完成？</div>
        <div class="ps-chips">
          <button
            v-for="c in cycleOptions"
            :key="c.value"
            type="button"
            class="ps-chip"
            :class="{ 'is-active': cycleSel === c.value }"
            @click="pickCycle(c)"
          >{{ c.label }}</button>
        </div>
        <el-input
          v-model="cycleCustom"
          class="ps-custom"
          placeholder="自定义，如：45天 / 2个月"
          size="small"
          @input="cycleSel = null"
        />
      </div>
    </div>

    <template #footer>
      <el-button size="small" @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" size="small" :disabled="!topic.trim()" @click="onStart">开始规划</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  /** 弹窗是否显示（v-model） */
  modelValue: { type: Boolean, default: false },
  /** 预填科目（欢迎页/引导芯片直接点科目时带入） */
  preTopic: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'start'])

const topic = ref('')
const dailyOptions = [
  { label: '30分钟', value: 0.5 },
  { label: '1小时', value: 1 },
  { label: '2小时', value: 2 },
  { label: '3小时+', value: 3 },
]
const cycleOptions = [
  { label: '交给AI定', value: '' },
  { label: '2周', value: '2周' },
  { label: '1个月', value: '1个月' },
  { label: '2个月', value: '2个月' },
  { label: '3个月', value: '3个月' },
]
const dailySel = ref(2) // 默认 2 小时
const cycleSel = ref('') // 默认交给 AI 定周期
const dailyCustom = ref('')
const cycleCustom = ref('')

function pickDaily(c) {
  dailySel.value = c.value
  dailyCustom.value = ''
}
function pickCycle(c) {
  cycleSel.value = c.value
  cycleCustom.value = ''
}

/** 把「1.5小时 / 45分钟 / 2h」等解析成小时；解析失败返回 null */
function parseHours(text) {
  const s = (text || '').trim().toLowerCase()
  const m = s.match(/(\d+(?:\.\d+)?)/)
  if (!m) return null
  const num = parseFloat(m[1])
  if (s.includes('分钟') || s.includes('min')) return Math.round((num / 60) * 100) / 100
  return num
}

function onStart() {
  const t = topic.value.trim()
  if (!t) {
    ElMessage.warning('请先输入要学的科目')
    return
  }
  let dailyHours = null
  if (dailyCustom.value.trim()) {
    dailyHours = parseHours(dailyCustom.value) ?? dailySel.value
  } else if (dailySel.value != null) {
    dailyHours = dailySel.value
  }
  const cycle = cycleCustom.value.trim() || (cycleSel.value || null)
  emit('start', { topic: t, dailyHours, cycle })
  emit('update:modelValue', false)
}

function onOpen() {
  topic.value = props.preTopic || ''
  dailySel.value = 2
  cycleSel.value = ''
  dailyCustom.value = ''
  cycleCustom.value = ''
}
</script>

<style scoped>
.ps-title .ps-h1 {
  font-size: 17px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.ps-title .ps-sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
.ps-body {
  padding: 4px 0;
}
.ps-field {
  margin-bottom: 18px;
}
.ps-field:last-child {
  margin-bottom: 0;
}
.ps-label {
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
  margin-bottom: 8px;
}
.ps-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.ps-chip {
  padding: 5px 14px;
  border-radius: 16px;
  border: 1px solid var(--el-border-color, #dcdfe6);
  background: #fff;
  font-size: 13px;
  color: var(--el-text-color-regular, #606266);
  cursor: pointer;
  transition: all 0.15s;
}
.ps-chip:hover {
  border-color: var(--el-color-primary, #409eff);
  color: var(--el-color-primary, #409eff);
}
.ps-chip.is-active {
  background: var(--el-color-primary, #409eff);
  border-color: var(--el-color-primary, #409eff);
  color: #fff;
}
.ps-custom {
  width: 100%;
}
</style>
