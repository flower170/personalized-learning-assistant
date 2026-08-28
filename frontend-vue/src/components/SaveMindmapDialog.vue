<template>
  <el-dialog
    :model-value="modelValue"
    title="🗒️ 保存到我的笔记"
    width="420px"
    append-to-body
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <div class="smd-tip">把这张思维导图图片存到「我的练习 → 我的笔记」，随时回来查看、下载。</div>
    <el-input
      v-model="title"
      placeholder="笔记标题，如：SQL 子查询思维导图"
      maxlength="40"
      show-word-limit
      @keyup.enter="onSave"
    />
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!title.trim()" :loading="saving" @click="onSave">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { practiceApi } from '@/api'
import { useChatStore } from '@/stores/chat'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 默认标题（聊天里通常传最近一条用户消息） */
  defaultTitle: { type: String, default: '' },
  /** 知识点主题 */
  topic: { type: String, default: '' },
  /** 思维导图 PNG 图片文件（由 MindmapBlock 导出后传入） */
  imageFile: { type: File, default: null },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const chatStore = useChatStore()
const title = ref('')
const saving = ref(false)

async function onSave() {
  const t = title.value.trim()
  if (!t) return
  saving.value = true
  try {
    const res = await practiceApi.addNote(chatStore.userId, t, props.topic, props.imageFile)
    if (res.ok) {
      ElMessage.success('已保存到我的笔记')
      emit('saved', res.note)
      emit('update:modelValue', false)
    } else {
      ElMessage.error(res.detail || '保存失败，请重试')
    }
  } catch (e) {
    console.error('[save-note] 失败', e)
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.smd-tip {
  font-size: 12.5px;
  color: #6b7280;
  margin-bottom: 12px;
  line-height: 1.6;
}
</style>
