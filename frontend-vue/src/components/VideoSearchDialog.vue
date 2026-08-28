<template>
  <el-dialog
    :model-value="modelValue"
    title="搜B站热门视频"
    width="640px"
    append-to-body
    @update:model-value="v => emit('update:modelValue', v)"
  >
    <div class="vsd-tip">按关键词在 B站检索热门视频，可按播放量或点赞量排序；选中一条自动填入标题和链接。</div>

    <div class="vsd-search">
      <el-input
        v-model="keyword"
        placeholder="如：SQL 入门、数据分析 教程"
        clearable
        @keyup.enter="doSearch"
      />
      <el-button type="primary" :loading="loading" @click="doSearch">搜索</el-button>
    </div>

    <template v-if="searched">
      <div v-if="videos.length" class="vsd-sort">
        <span class="vsd-sort-label">排序</span>
        <el-radio-group v-model="sortKey" size="small">
          <el-radio-button value="play">播放量</el-radio-button>
          <el-radio-button value="like">点赞量</el-radio-button>
        </el-radio-group>
        <span class="vsd-count">{{ videos.length }} 条结果</span>
      </div>

      <div v-if="videos.length" class="vsd-list">
        <div v-for="(v, i) in sortedVideos" :key="v.bvid" class="vsd-item">
          <div class="vsd-cover" :style="coverStyle(v.cover)">
            <span class="vsd-duration">{{ v.duration }}</span>
          </div>
          <div class="vsd-info">
            <div class="vsd-title" :title="v.title">{{ v.title }}</div>
            <div class="vsd-meta">
              <span class="vsd-author" :title="v.author">UP：{{ v.author || '—' }}</span>
              <span>播放 {{ fmtNum(v.play) }}</span>
              <span>点赞 {{ fmtNum(v.like) }}</span>
            </div>
          </div>
          <el-button size="small" type="primary" plain @click="pick(v)">选用</el-button>
        </div>
      </div>

      <div v-else-if="!loading" class="vsd-empty">
        <div class="vsd-empty-title">没搜到「{{ keyword }}」相关视频</div>
        <div class="vsd-empty-sub">换个关键词，或直接用「自定义」手动填标题和链接</div>
      </div>
    </template>

    <div v-else class="vsd-placeholder">
      <div>输入关键词搜索 B站热门视频</div>
      <div class="vsd-placeholder-sub">搜不到也不影响 —— 下方仍可自定义添加任意链接</div>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { practiceApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 初始搜索关键词（从节点标题等预填） */
  initialKeyword: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const keyword = ref('')
const videos = ref([])
const loading = ref(false)
const searched = ref(false)
const sortKey = ref('play')

// 打开弹窗时预填关键词（节点标题等），并重置搜索结果
watch(() => props.modelValue, (open) => {
  if (open) {
    keyword.value = props.initialKeyword || ''
    searched.value = false
    videos.value = []
    sortKey.value = 'play'
  }
})

const sortedVideos = computed(() => {
  const arr = [...videos.value]
  const key = sortKey.value === 'like' ? 'like' : 'play'
  arr.sort((a, b) => (Number(b[key]) || 0) - (Number(a[key]) || 0))
  return arr
})

async function doSearch() {
  const kw = keyword.value.trim()
  if (!kw) return
  loading.value = true
  searched.value = true
  try {
    const res = await practiceApi.searchVideos(kw, 1)
    videos.value = (res.ok && res.videos) || []
  } catch (e) {
    console.error('[video-search] 失败', e)
    videos.value = []
  } finally {
    loading.value = false
  }
}

function pick(v) {
  emit('select', {
    title: v.title,
    url: v.url,
    platform: 'B站',
    author: v.author,
    play: v.play,
    like: v.like,
    duration: v.duration,
    cover: v.cover,
    bvid: v.bvid,
  })
  emit('update:modelValue', false)
}

/** 数字格式化：1.5万 / 2.3亿 */
function fmtNum(n) {
  const x = Number(n) || 0
  if (x >= 1e8) return (x / 1e8).toFixed(1).replace(/\.0$/, '') + '亿'
  if (x >= 1e4) return (x / 1e4).toFixed(1).replace(/\.0$/, '') + '万'
  return String(x)
}

/** 封面缺失时给个占位底色 */
function coverStyle(cover) {
  return cover ? { backgroundImage: `url(${cover})` } : { background: '#eef0f3' }
}
</script>

<style scoped>
.vsd-tip {
  font-size: 12.5px;
  color: #6b7280;
  margin-bottom: 12px;
  line-height: 1.6;
}
.vsd-search {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.vsd-sort {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.vsd-sort-label {
  font-size: 12.5px;
  color: #6b7280;
}
.vsd-count {
  margin-left: auto;
  font-size: 12px;
  color: #9ca3af;
}
.vsd-list {
  max-height: 340px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.vsd-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  transition: border-color 0.15s;
}
.vsd-item:hover {
  border-color: #c7d2fe;
}
.vsd-cover {
  position: relative;
  width: 108px;
  height: 60px;
  flex-shrink: 0;
  border-radius: 6px;
  background-size: cover;
  background-position: center;
  overflow: hidden;
}
.vsd-duration {
  position: absolute;
  right: 4px;
  bottom: 4px;
  font-size: 11px;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 3px;
  padding: 0 4px;
}
.vsd-info {
  flex: 1;
  min-width: 0;
}
.vsd-title {
  font-size: 13.5px;
  color: #1f2937;
  font-weight: 500;
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.vsd-meta {
  display: flex;
  gap: 12px;
  margin-top: 5px;
  font-size: 12px;
  color: #9ca3af;
}
.vsd-author {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vsd-empty {
  padding: 40px 0;
  text-align: center;
  color: #9ca3af;
}
.vsd-empty-title {
  font-size: 14px;
  color: #6b7280;
}
.vsd-empty-sub {
  font-size: 12.5px;
  margin-top: 6px;
}
.vsd-placeholder {
  padding: 40px 0;
  text-align: center;
  color: #9ca3af;
  font-size: 13.5px;
}
.vsd-placeholder-sub {
  font-size: 12.5px;
  margin-top: 6px;
}
</style>
