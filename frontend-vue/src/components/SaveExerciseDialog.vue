<template>
  <el-dialog
    :model-value="modelValue"
    title="📥 加入错题集"
    width="440px"
    append-to-body
    @update:model-value="v => emit('update:modelValue', v)"
    @open="loadCollections"
  >
    <div v-if="loading" class="sav-loading">加载中…</div>
    <div v-else-if="!collections.length" class="sav-empty">
      <p class="sav-tip">还没有题目集，先创建一个，之后就能把题目收进去随时回来重做：</p>
      <el-input
        v-model="newName"
        placeholder="题目集名称，如：SQL 错题"
        maxlength="30"
        @keyup.enter="createAndAdd"
      />
      <div class="sav-actions">
        <el-button
          type="primary"
          :disabled="!newName.trim()"
          :loading="saving"
          @click="createAndAdd"
        >
          创建并加入
        </el-button>
      </div>
    </div>
    <div v-else>
      <p class="sav-tip">选择要加入的题目集：</p>
      <el-radio-group v-model="selectedId" class="sav-list">
        <el-radio
          v-for="c in collections"
          :key="c.collection_id"
          :value="c.collection_id"
          class="sav-item"
        >
          <span class="sav-name">📁 {{ c.name }}</span>
          <span class="sav-count">{{ c.questions.length }} 题</span>
        </el-radio>
      </el-radio-group>
      <el-divider style="margin: 12px 0" />
      <div class="sav-new-toggle" @click="showCreate = !showCreate">
        <el-icon><Plus /></el-icon>
        <span>{{ showCreate ? '收起' : '新建题目集' }}</span>
      </div>
      <el-input
        v-if="showCreate"
        v-model="newName"
        placeholder="题目集名称，如：SQL 错题"
        maxlength="30"
        class="sav-new-input"
        @keyup.enter="createAndAdd"
      />
      <div class="sav-actions">
        <el-button
          type="primary"
          :disabled="!selectedId"
          :loading="saving"
          @click="addToSelected"
        >
          加入「{{ selectedName }}」
        </el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { practiceApi } from '@/api'
import { useChatStore } from '@/stores/chat'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 要收藏的题目（含 question/type/options/answer/explanation/difficulty） */
  exercise: { type: Object, default: () => ({}) },
  /** 题目所属知识点（聊天里取最近一条用户消息） */
  topic: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'saved'])

const chatStore = useChatStore()

const collections = ref([])
const loading = ref(false)
const saving = ref(false)
const newName = ref('')
const selectedId = ref('')
const showCreate = ref(false)

const selectedName = computed(() => {
  return collections.value.find(c => c.collection_id === selectedId.value)?.name || ''
})

async function loadCollections() {
  loading.value = true
  try {
    const res = await practiceApi.listCollections(chatStore.userId)
    collections.value = res?.collections || []
    selectedId.value = collections.value[0]?.collection_id || ''
    showCreate.value = false
    newName.value = ''
  } catch (e) {
    ElMessage.error('加载题目集失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name) return
  saving.value = true
  try {
    const res = await practiceApi.createCollection(chatStore.userId, name)
    if (res.ok) {
      await doAdd(res.collection.collection_id, res.collection.name)
    } else {
      ElMessage.warning(res.detail || '创建失败，可能已存在同名题目集')
    }
  } catch (e) {
    ElMessage.error('创建题目集失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

async function addToSelected() {
  if (!selectedId.value) return
  saving.value = true
  try {
    await doAdd(selectedId.value, selectedName.value)
  } catch (e) {
    ElMessage.error('加入失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

async function doAdd(collectionId, name) {
  const res = await practiceApi.addToCollection(
    chatStore.userId, collectionId, props.topic, props.exercise)
  if (res.ok) {
    ElMessage.success(`已加入「${name}」`)
    emit('saved', { collectionId, name })
    emit('update:modelValue', false)
  }
}
</script>

<style scoped>
.sav-loading { text-align: center; color: #9ca3af; padding: 20px 0; font-size: 13px; }
.sav-tip { font-size: 12.5px; color: #6b7280; margin-bottom: 10px; }
.sav-list { display: flex; flex-direction: column; gap: 4px; width: 100%; }
.sav-item {
  height: auto;
  padding: 8px 10px;
  margin-right: 0;
  border-radius: 8px;
}
.sav-item:hover { background: #f8f9ff; }
.sav-name { font-size: 13.5px; font-weight: 500; color: #1f2937; }
.sav-count { font-size: 12px; color: #9ca3af; margin-left: 8px; }
.sav-new-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #6366f1;
  cursor: pointer;
  padding: 4px 2px;
}
.sav-new-toggle:hover { color: #4f46e5; }
.sav-new-input { margin-top: 8px; }
.sav-actions { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
