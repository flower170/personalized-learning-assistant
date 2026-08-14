<template>
  <div class="practice-cards">
    <div v-if="cards.length === 0 && !loading" class="pc-empty">
      <template v-if="canSearch">还没有练习卡。点击「去官方找题」按当前知识点搜索官方 OJ 题目～</template>
      <template v-else>该科目没有对应的官方 OJ 题库，直接用课本/真题练习就好。</template>
    </div>

    <div v-for="card in cards" :key="card.card_id" class="pc-card">
      <div class="pc-head">
        <span class="pc-platform" :style="{ color: platformColor(card.platform) }">
          {{ card.platform }}
        </span>
        <span v-if="card.problem_no" class="pc-no">{{ card.problem_no }}</span>
        <span class="pc-diff" :class="`diff-${card.difficulty}`">{{ card.difficulty }}</span>
      </div>

      <div class="pc-title">{{ card.title }}</div>
      <div v-if="card.knowledge_point" class="pc-kp">📌 {{ card.knowledge_point }}</div>

      <div class="pc-body">
        <el-select
          :model-value="card.status"
          size="small"
          class="pc-status"
          @update:model-value="v => setStatus(card, v)"
        >
          <el-option label="未做" value="undone" />
          <el-option label="已做" value="done" />
          <el-option label="做对" value="correct" />
          <el-option label="做错" value="wrong" />
        </el-select>
        <el-input
          :model-value="card.note"
          size="small"
          class="pc-note"
          placeholder="学习笔记"
          @blur="e => saveNote(card, e.target.value)"
        />
        <a :href="card.link" target="_blank" rel="noopener" class="pc-link">
          <el-button size="small" type="primary" text>去做题 →</el-button>
        </a>
      </div>
    </div>

    <div class="pc-footer">
      <el-button v-if="canSearch" size="small" :loading="loading" @click="$emit('find')">🔍 去官方找题</el-button>
      <span v-if="updatedCardId" class="pc-saved">✓ 已保存</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { practiceApi } from '@/api'

const props = defineProps({
  studentId: { type: String, required: true },
  nodeId: { type: String, required: true },
  cards: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  canSearch: { type: Boolean, default: true },
})
const emit = defineEmits(['find', 'updated'])

const updatedCardId = ref('')

function platformColor(p) {
  return { LeetCode: '#f59e0b', 牛客: '#00a1e9', 洛谷: '#16a34a', AcWing: '#6366f1', PTA: '#dc2626' }[p] || '#6b7280'
}

async function setStatus(card, status) {
  try {
    const res = await practiceApi.update(props.studentId, card.card_id, { status })
    if (res.ok) {
      Object.assign(card, res.card)
      updatedCardId.value = card.card_id
      setTimeout(() => (updatedCardId.value = ''), 1500)
      emit('updated')
    }
  } catch (err) {
    ElMessage.error(`更新失败: ${err.message}`)
  }
}

async function saveNote(card, note) {
  if (note === card.note) return
  try {
    const res = await practiceApi.update(props.studentId, card.card_id, { note })
    if (res.ok) Object.assign(card, res.card)
  } catch (err) {
    ElMessage.error(`笔记保存失败: ${err.message}`)
  }
}
</script>

<style scoped>
.practice-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pc-empty {
  font-size: 13px;
  color: var(--text-muted, #9ca3af);
  padding: 12px 4px;
  text-align: center;
}
.pc-card {
  border: 1px solid var(--border-primary, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--bg-primary, #fff);
  transition: box-shadow 0.15s;
}
.pc-card:hover {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}
.pc-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.pc-platform {
  font-size: 12px;
  font-weight: 700;
}
.pc-no {
  font-size: 11px;
  color: var(--text-muted, #9ca3af);
  background: var(--bg-tertiary, #f3f4f6);
  padding: 1px 6px;
  border-radius: 4px;
}
.pc-diff {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
}
.diff-入门 { background: #dcfce7; color: #166534; }
.diff-简单 { background: #dbeafe; color: #1d4ed8; }
.diff-中等 { background: #fef3c7; color: #92400e; }
.diff-困难 { background: #fee2e2; color: #b91c1c; }
.pc-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary, #1f2937);
  margin-bottom: 2px;
}
.pc-kp {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  margin-bottom: 8px;
}
.pc-body {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pc-status {
  width: 92px;
  flex-shrink: 0;
}
.pc-note {
  flex: 1;
  min-width: 120px;
}
.pc-link { text-decoration: none; flex-shrink: 0; }
.pc-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 2px;
}
.pc-saved {
  font-size: 12px;
  color: #16a34a;
}
</style>
