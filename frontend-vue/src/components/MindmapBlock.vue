<template>
  <div class="mindmap-block">
    <div v-if="title" class="mindmap-title">{{ title }}</div>

    <!-- 工具栏：放大查看 / 下载图片 / 保存到我的笔记 -->
    <div v-if="showToolbar" class="mindmap-toolbar">
      <button class="mm-tool-btn" title="放大查看" @click="openViewer">
        <el-icon><ZoomIn /></el-icon> 放大
      </button>
      <button class="mm-tool-btn" title="下载为图片" :disabled="busy" @click="onDownload">
        <el-icon><Download /></el-icon> 下载
      </button>
      <button
        v-if="showSave"
        class="mm-tool-btn"
        title="保存到我的笔记"
        :disabled="busy || isStreaming"
        @click="onSave"
      >
        <el-icon><Collection /></el-icon> 保存到笔记
      </button>
    </div>

    <div class="mindmap-wrap" ref="wrapEl">
      <svg ref="svgEl" class="mindmap-svg"></svg>
      <div v-if="empty" class="mindmap-empty">正在生成思维导图…</div>
      <!-- 点击展开全图 -->
      <button v-if="showToolbar" class="mm-expand-btn" title="放大查看" @click.stop="openViewer">
        <el-icon><FullScreen /></el-icon>
      </button>
    </div>

    <!-- 放大查看弹窗：独立大画布 markmap，鼠标滚轮缩放 / 拖拽平移 -->
    <el-dialog
      v-model="viewerVisible"
      class="mm-viewer-dialog"
      :show-close="false"
      append-to-body
      top="2vh"
      width="96%"
      @closed="destroyViewer"
    >
      <template #header>
        <div class="mm-viewer-head">
          <span class="mm-viewer-title">{{ title || '思维导图' }}</span>
          <div class="mm-viewer-actions">
            <el-button size="small" @click="viewerFit">
              <el-icon><Aim /></el-icon> 适配
            </el-button>
            <el-button size="small" :loading="busy" @click="downloadFrom(viewerMm)">
              <el-icon><Download /></el-icon> 下载
            </el-button>
            <el-button v-if="showSave" size="small" :loading="busy" @click="saveFrom(viewerMm)">
              <el-icon><Collection /></el-icon> 保存到笔记
            </el-button>
            <el-button size="small" @click="viewerVisible = false">
              <el-icon><Close /></el-icon> 关闭
            </el-button>
          </div>
        </div>
      </template>
      <div class="mm-viewer-body" ref="viewerBodyEl">
        <div v-if="viewerEmpty" class="mm-viewer-empty">无法生成思维导图</div>
        <svg ref="viewerSvgEl" class="mm-viewer-svg"></svg>
        <div class="mm-viewer-hint">鼠标滚轮缩放 · 拖拽平移</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'

const props = defineProps({
  markdown: { type: String, default: '' },
  title: { type: String, default: '' },
  /** 流式生成中：禁用「保存到笔记」，避免存到半张图 */
  isStreaming: { type: Boolean, default: false },
  /** 是否显示「保存到笔记」按钮（我的练习里浏览已存笔记时不显示） */
  showSave: { type: Boolean, default: true },
})
const emit = defineEmits(['save'])

const svgEl = ref(null)
const wrapEl = ref(null)
const empty = ref(false)
const viewerVisible = ref(false)
const viewerSvgEl = ref(null)
const viewerBodyEl = ref(null)
const viewerEmpty = ref(false)
const busy = ref(false)

let mm = null          // 内联实例
let viewerMm = null    // 放大弹窗实例
let ro = null
let viewerRo = null
let renderTimer = null
let fitTimer = null

// 浅色舒适配色（柔和、不鲜艳），按节点深度取色
const PALETTE = ['#7d98b3', '#9fc0e0', '#a9d1c2', '#e5c9a3', '#d4b8c4', '#b7c4dd']
const colorByDepth = (node) => {
  const d = node?.depth || 0
  return PALETTE[Math.min(d, PALETTE.length - 1)]
}

const showToolbar = computed(() => !!props.markdown.trim() && !empty.value)

function transform(md) {
  const transformer = new Transformer()
  return transformer.transform(md || '# ')
}

function render() {
  empty.value = false
  if (!svgEl.value) return
  const svg = svgEl.value
  try {
    const { root } = transform(props.markdown)
    if (!root?.children?.length) {
      empty.value = true
      return
    }
    if (!mm) {
      mm = Markmap.create(svg, {
        color: colorByDepth,
        colorFreezeLevel: 0,
        duration: 200,
        initialExpandLevel: 3,
        fitRatio: 0.96,
        maxWidth: 260,
        spacingHorizontal: 90,
        spacingVertical: 12,
      }, root)
      requestAnimationFrame(() => {
        try { mm.fit() } catch {}
      })
    } else {
      mm.setData(root).catch(() => {})
    }
  } catch (e) {
    console.error('markmap 渲染失败', e)
    empty.value = true
  }
}

function scheduleRender() {
  if (renderTimer) clearTimeout(renderTimer)
  renderTimer = setTimeout(render, 120)
  if (fitTimer) clearTimeout(fitTimer)
  fitTimer = setTimeout(() => {
    try { if (mm) mm.fit() } catch {}
  }, 700)
}

// ==================== 放大查看 ====================

function openViewer() {
  if (viewerVisible.value) return
  viewerVisible.value = true
  nextTick(buildViewer)
}

function buildViewer() {
  if (!viewerSvgEl.value || !viewerVisible.value) return
  viewerEmpty.value = false
  try {
    const { root } = transform(props.markdown)
    if (!root?.children?.length) {
      viewerEmpty.value = true
      return
    }
    if (viewerMm) viewerMm.destroy()
    viewerMm = Markmap.create(viewerSvgEl.value, {
      color: colorByDepth,
      colorFreezeLevel: 0,
      duration: 0,
      initialExpandLevel: 3,
      fitRatio: 0.95,
      maxWidth: 320,
      spacingHorizontal: 110,
      spacingVertical: 14,
    }, root)
    requestAnimationFrame(() => {
      try { viewerMm.fit() } catch {}
    })
    if (viewerBodyEl.value && typeof ResizeObserver !== 'undefined') {
      if (viewerRo) viewerRo.disconnect()
      viewerRo = new ResizeObserver(() => {
        try { if (viewerMm) viewerMm.fit() } catch {}
      })
      viewerRo.observe(viewerBodyEl.value)
    }
  } catch (e) {
    console.error('放大查看渲染失败', e)
    viewerEmpty.value = true
  }
}

function viewerFit() {
  try { if (viewerMm) viewerMm.fit() } catch {}
}

function destroyViewer() {
  if (viewerRo) { viewerRo.disconnect(); viewerRo = null }
  if (viewerMm) {
    try { viewerMm.destroy() } catch {}
    viewerMm = null
  }
  if (viewerSvgEl.value) viewerSvgEl.value.innerHTML = ''
}

// ==================== 导出（PNG / SVG 兜底） ====================

/**
 * 把 markmap 实例当前内容导出为图片。
 * 做法：临时去掉主分组 transform 量出完整内容包围盒 → 克隆 SVG（白底 + 标签文字内联黑色）
 * → 以 SVG blob 喂 <img> 绘制到 canvas 得到 PNG；canvas 失败时退回 SVG blob。
 */
async function exportBlob(mmInstance, format = 'png') {
  if (!mmInstance) return null
  const svg = mmInstance.svg?.node?.()
  const gNode = mmInstance.g?.node?.()
  if (!svg || !gNode) return null

  // 量完整内容包围盒（不动 viewport 内缩放：先摘 transform，量完即还原）
  const prev = gNode.getAttribute('transform')
  gNode.removeAttribute('transform')
  let bbox = null
  try {
    bbox = gNode.getBBox()
  } catch { bbox = null }
  if (prev !== null) gNode.setAttribute('transform', prev)
  if (!bbox || !bbox.width || !bbox.height) return null

  const W = Math.ceil(bbox.width)
  const H = Math.ceil(bbox.height)
  const clone = svg.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(W))
  clone.setAttribute('height', String(H))
  clone.setAttribute('viewBox', `${bbox.x} ${bbox.y} ${bbox.width} ${bbox.height}`)
  const cloneG = clone.querySelector('g')
  if (cloneG) cloneG.removeAttribute('transform')
  // 白底
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  rect.setAttribute('x', String(bbox.x))
  rect.setAttribute('y', String(bbox.y))
  rect.setAttribute('width', String(W))
  rect.setAttribute('height', String(H))
  rect.setAttribute('fill', '#ffffff')
  clone.insertBefore(rect, clone.firstChild)
  // 导出图片不携带外部 CSS：把标签文字颜色内联成黑色（同界面上的覆盖规则），
  // 并指定字体栈，避免 SVG 图片模式下回落到默认衬线字体
  clone.querySelectorAll('.markmap-foreign, .markmap-foreign *').forEach(el => {
    el.style.setProperty('color', '#000', 'important')
    el.style.setProperty('font-family', "'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif", 'important')
  })

  const svgBlob = new Blob([new XMLSerializer().serializeToString(clone)],
    { type: 'image/svg+xml;charset=utf-8' })
  if (format === 'svg') return svgBlob

  try {
    const url = URL.createObjectURL(svgBlob)
    const img = new Image()
    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = reject
      img.src = url
    })
    const scale = 2
    const canvas = document.createElement('canvas')
    canvas.width = W * scale
    canvas.height = H * scale
    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    }
    URL.revokeObjectURL(url)
    const pngBlob = await new Promise((r) => canvas.toBlob(r, 'image/png'))
    return pngBlob || svgBlob
  } catch (e) {
    console.warn('[mindmap] PNG 导出失败，退回 SVG', e)
    return svgBlob
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function filename() {
  const base = (props.title || '思维导图').replace(/[\\/:*?"<>|]/g, '').trim() || '思维导图'
  return `${base}_${Date.now()}.png`
}

async function withBusy(fn) {
  if (busy.value) return
  busy.value = true
  try { await fn() } finally { busy.value = false }
}

function onDownload() {
  withBusy(async () => {
    const blob = await exportBlob(mm, 'png')
    if (blob) triggerDownload(blob, filename())
    else ElMessage.error('导出失败，请重试')
  })
}

function downloadFrom(inst) {
  withBusy(async () => {
    const blob = await exportBlob(inst, 'png')
    if (blob) triggerDownload(blob, filename())
    else ElMessage.error('导出失败，请重试')
  })
}

function onSave() {
  withBusy(async () => {
    const blob = await exportBlob(mm, 'png')
    if (!blob) { ElMessage.error('导图导出失败，请重试'); return }
    const file = new File([blob], 'mindmap.png', { type: 'image/png' })
    emit('save', file)
  })
}

function saveFrom(inst) {
  withBusy(async () => {
    const blob = await exportBlob(inst, 'png')
    if (!blob) { ElMessage.error('导图导出失败，请重试'); return }
    const file = new File([blob], 'mindmap.png', { type: 'image/png' })
    emit('save', file)
  })
}

onMounted(() => {
  render()
  if (wrapEl.value && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => {
      try { if (mm) mm.fit() } catch {}
    })
    ro.observe(wrapEl.value)
  }
})

onBeforeUnmount(() => {
  if (renderTimer) clearTimeout(renderTimer)
  if (fitTimer) clearTimeout(fitTimer)
  if (ro) { ro.disconnect(); ro = null }
  destroyViewer()
  if (mm) {
    try { mm.destroy() } catch {}
    mm = null
  }
})

watch(() => props.markdown, () => scheduleRender())
</script>

<style scoped>
.mindmap-block {
  border: 1px solid #e6eaef;
  border-radius: 10px;
  background: #fbfcfe;
  padding: 12px 14px 4px;
  margin: 4px 0 2px;
}
.mindmap-title {
  font-size: 13px;
  font-weight: 600;
  color: #5b6b7b;
  padding-bottom: 6px;
  border-bottom: 1px dashed #e6eaef;
  margin-bottom: 6px;
}

/* 工具栏 */
.mindmap-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-bottom: 4px;
}
.mm-tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: #6b7280;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 2px 10px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}
.mm-tool-btn:hover:not(:disabled) {
  border-color: #c7d2fe;
  color: #6366f1;
  background: #f8f9ff;
}
.mm-tool-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mindmap-wrap {
  position: relative;
  width: 100%;
  height: 420px;
  overflow: hidden;
}
.mm-expand-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
  opacity: 0.6;
}
.mm-expand-btn:hover {
  opacity: 1;
  color: #6366f1;
  border-color: #c7d2fe;
  background: #fff;
}
.mindmap-svg {
  width: 100%;
  height: 100%;
  display: block;
}
/* 节点文字固定为黑色（覆盖 markmap 跟随节点颜色的内联色），浅色背景上清晰可读 */
.mindmap-svg :deep(.markmap-foreign),
.mindmap-svg :deep(.markmap-foreign *) {
  color: #000000 !important;
}
.mindmap-svg :deep(.markmap-node > circle) {
  stroke: #ffffff;
  stroke-width: 1.5px;
}
/* 连接线颜色不限制：沿用 markmap 默认（跟随子节点浅色） */
.mindmap-empty {
  color: #9aa5b1;
  font-size: 13px;
  padding: 12px 0;
  text-align: center;
}

/* 放大查看弹窗 */
.mm-viewer-dialog :deep(.el-dialog) {
  border-radius: 12px;
  overflow: hidden;
}
.mm-viewer-dialog :deep(.el-dialog__header) {
  padding: 12px 16px 10px;
  border-bottom: 1px solid #eef0f4;
}
.mm-viewer-dialog :deep(.el-dialog__body) {
  padding: 12px 16px 16px;
}
.mm-viewer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.mm-viewer-title {
  font-size: 15px;
  font-weight: 700;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mm-viewer-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}
.mm-viewer-body {
  position: relative;
  height: calc(88vh - 70px);
  background: #ffffff;
  border: 1px solid #eef0f4;
  border-radius: 8px;
  overflow: hidden;
}
.mm-viewer-svg {
  width: 100%;
  height: 100%;
  display: block;
}
.mm-viewer-svg :deep(.markmap-foreign),
.mm-viewer-svg :deep(.markmap-foreign *) {
  color: #000000 !important;
}
.mm-viewer-svg :deep(.markmap-node > circle) {
  stroke: #ffffff;
  stroke-width: 1.5px;
}
.mm-viewer-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9aa5b1;
  font-size: 14px;
}
.mm-viewer-hint {
  position: absolute;
  right: 12px;
  bottom: 10px;
  font-size: 11px;
  color: #c0c8d1;
  background: rgba(255, 255, 255, 0.8);
  padding: 2px 8px;
  border-radius: 10px;
  pointer-events: none;
}
</style>
