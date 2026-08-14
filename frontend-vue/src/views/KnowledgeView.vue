<template>
  <div class="knowledge-view">
    <div class="page-header">
      <h2><el-icon><Reading /></el-icon> 知识库</h2>
      <el-button size="small" @click="$router.push('/')">
        <el-icon><Back /></el-icon> 返回聊天
      </el-button>
    </div>

    <el-card shadow="never" class="kb-card">
      <template #header>
        <div class="card-header">
          <span>📄 上传文档</span>
        </div>
      </template>
      <el-upload
        drag
        :auto-upload="false"
        :show-file-list="false"
        :before-upload="handleUpload"
        accept=".pdf,.doc,.docx,.md,.txt"
        style="width:100%"
      >
        <el-icon :size="40" color="#c7d2fe"><UploadFilled /></el-icon>
        <div style="margin:8px 0;font-size:14px;color:#374151">
          拖拽或点击上传文档
        </div>
        <div style="font-size:12px;color:#9ca3af">
          支持 PDF / Word / Markdown / TXT，最大 20MB
        </div>
      </el-upload>
      <div v-if="uploadStatus" class="upload-status" :class="uploadStatus.type">
        {{ uploadStatus.msg }}
      </div>
    </el-card>

    <el-card shadow="never" class="kb-card">
      <template #header>
        <span>📋 已上传文档</span>
      </template>
      <div v-if="chatStore.uploadedFiles.length === 0" style="color:#9ca3af;font-size:13px;padding:8px 0;">
        暂无上传文档
      </div>
      <div v-for="f in chatStore.uploadedFiles" :key="f.id" class="file-row">
        <div class="file-info">
          <span class="file-icon">{{ fileIcon(f.ext) }}</span>
          <div class="file-detail">
            <span class="file-name">{{ f.name }}</span>
            <span class="file-meta">{{ f.ext?.toUpperCase() }} · {{ f.size }}</span>
          </div>
        </div>
        <div class="file-status-col">
          <el-tag v-if="f.status === 'vectored'" size="small" type="success">就绪</el-tag>
          <el-tag v-else-if="f.status === 'failed'" size="small" type="danger">失败</el-tag>
          <el-tag v-else size="small" type="warning">处理中</el-tag>
          <span v-if="f.id === chatStore.tempFileId" class="file-active-badge">当前</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { Reading, Back, UploadFilled } from '@element-plus/icons-vue'

const chatStore = useChatStore()
const uploadStatus = ref(null)

function fileIcon(ext) {
  const map = { pdf: '📕', doc: '📘', docx: '📘', md: '📝', txt: '📄' }
  return map[ext?.toLowerCase()] || '📄'
}

async function handleUpload(file) {
  const formData = new FormData()
  formData.append('file', file)
  uploadStatus.value = { type: 'loading', msg: '上传中...' }
  try {
    const resp = await fetch('/api/file/upload', { method: 'POST', body: formData })
    const data = await resp.json()
    if (data.success || data.temp_file_id) {
      chatStore.setTempFileId(data.temp_file_id)
      chatStore.addUploadedFile({
        id: data.temp_file_id,
        name: file.name,
        ext: file.name.split('.').pop(),
        size: (data.size / 1024).toFixed(1) + 'KB',
        status: 'vectored',
      })
      uploadStatus.value = { type: 'success', msg: `✅ 上传成功！${file.name}` }
    } else {
      uploadStatus.value = { type: 'error', msg: `❌ ${data.msg || '上传失败'}` }
    }
  } catch (e) {
    uploadStatus.value = { type: 'error', msg: `❌ ${e.message}` }
  }
  return false
}
</script>

<style scoped>
.knowledge-view {
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
.kb-card { border-radius: 10px; margin-bottom: 16px; }
.card-header { font-weight: 600; }
.upload-status {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.upload-status.success { background: #ecfdf5; color: #065f46; }
.upload-status.error { background: #fef2f2; color: #dc2626; }
.upload-status.loading { background: #eff6ff; color: #1d4ed8; }

/* File list */
.file-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 8px; border-radius: 8px;
}
.file-row + .file-row { border-top: 1px solid #f3f4f6; }
.file-info {
  display: flex; align-items: center; gap: 10px; min-width: 0;
}
.file-icon { font-size: 20px; }
.file-detail {
  display: flex; flex-direction: column; min-width: 0;
}
.file-name {
  font-size: 13px; font-weight: 500; color: #1f2937;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.file-meta { font-size: 11px; color: #9ca3af; }
.file-status-col {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.file-active-badge {
  font-size: 11px; color: #6366f1; font-weight: 600;
  background: #eef0ff; padding: 1px 8px; border-radius: 8px;
}
</style>
