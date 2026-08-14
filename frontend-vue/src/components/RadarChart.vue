<template>
  <div ref="chartRef" class="radar-chart" :style="{ width: size + 'px', height: size + 'px' }"></div>
</template>

<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] },
  size: { type: Number, default: 400 },
  // dual 模式：data 项为 {name, skill_score, market_score, description}
  // 渲染两条系列「我的技能」vs「市场需求」
  mode: { type: String, default: 'single' },
})

const chartRef = ref(null)
let chart = null
let hoveredDimIdx = -1  // 跟踪当前悬浮的维度索引

const colors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#06b6d4', '#8b5cf6', '#f97316']

function render() {
  if (!chartRef.value || !props.data.length) return

  if (!chart) {
    chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  }

  const indicators = props.data.map((d, i) => ({
    name: d.name,
    max: 10,
    color: colors[i % colors.length],
  }))

  chart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      borderRadius: 8,
      padding: [10, 14],
      textStyle: { color: '#374151', fontSize: 12 },
      confine: true,          // 避免 tooltip 溢出画布
      extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.08);',
      formatter: (params) => {
        if (!params || !params.value) return ''

        // 计算悬浮的维度索引 (encode 优先，其次鼠标角度)
        let idx = -1
        const encodeIdx = params.encode?.x?.[0]
        if (encodeIdx !== undefined && encodeIdx >= 0 && encodeIdx < props.data.length) {
          idx = encodeIdx
        } else if (hoveredDimIdx >= 0 && hoveredDimIdx < props.data.length) {
          idx = hoveredDimIdx
        }

        // ── dual 模式：展示「我的技能 vs 市场需求」双值 + 差距 ──
        if (props.mode === 'dual') {
          if (idx >= 0) {
            const dim = props.data[idx]
            const c = colors[idx % colors.length]
            const sk = dim.skill_score ?? 0
            const mk = dim.market_score ?? 0
            const gap = Math.round((mk - sk) * 10) / 10
            const gapHtml = gap !== 0
              ? `<div style="font-size:12px;margin-top:6px;color:${gap > 0 ? '#f59e0b' : '#10b981'}">差距 ${gap > 0 ? '+' : ''}${gap.toFixed(1)}　${gap > 0 ? '🔥 需求大于技能，值得补' : '✓ 技能已满足需求'}</div>`
              : ''
            return `<div style="font-weight:600;font-size:14px;color:${c};margin-bottom:6px">${dim.name}</div>
              <div style="display:flex;flex-direction:column;gap:4px;min-width:150px">
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="width:10px;height:10px;border-radius:50%;background:#6366f1;display:inline-block"></span>
                  <span style="font-size:12px;color:#6b7280;width:52px">我的技能</span>
                  <span style="font-size:16px;font-weight:700;color:#6366f1">${typeof sk === 'number' ? sk.toFixed(1) : sk}</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="width:10px;height:10px;border-radius:50%;background:#f59e0b;display:inline-block"></span>
                  <span style="font-size:12px;color:#6b7280;width:52px">市场需求</span>
                  <span style="font-size:16px;font-weight:700;color:#f59e0b">${typeof mk === 'number' ? mk.toFixed(1) : mk}</span>
                </div>
                ${gapHtml}
                ${dim.description ? `<div style="font-size:12px;color:#6b7280;margin-top:6px;max-width:200px;line-height:1.4">${dim.description}</div>` : ''}`
          }
          // 兜底：全部维度对比
          let html = '<div style="font-weight:600;font-size:13px;margin-bottom:6px">维度对比</div>'
          props.data.forEach((d, i) => {
            const c = colors[i % colors.length]
            html += `<div style="display:flex;justify-content:space-between;gap:16px;padding:2px 0;border-bottom:${i < props.data.length - 1 ? '1px solid #f3f4f6' : 'none'}">
              <span style="font-size:12px;color:#374151">${d.name}</span>
              <span style="font-size:12px;font-weight:600;color:${c}">我的 ${typeof d.skill_score === 'number' ? d.skill_score.toFixed(1) : d.skill_score} / 市场 ${typeof d.market_score === 'number' ? d.market_score.toFixed(1) : d.market_score}</span>
            </div>`
          })
          return html
        }

        // ── 方案A: 通过 encode 获取悬浮的维度索引 (ECharts 5+) ──
        if (idx >= 0) {
          const dim = props.data[idx]
          const val = params.value[idx]
          const c = colors[idx % colors.length]
          return `<div style="font-weight:600;font-size:14px;color:${c};margin-bottom:6px">${dim.name}</div>
            <div style="display:flex;align-items:baseline;gap:6px">
              <span style="font-size:28px;font-weight:700;color:${c}">${typeof val === 'number' ? val.toFixed(1) : val}</span>
              <span style="font-size:12px;color:#9ca3af">/ 10</span>
            </div>
            ${dim.description ? `<div style="font-size:12px;color:#6b7280;margin-top:6px;max-width:180px;line-height:1.4">${dim.description}</div>` : ''}`
        }

        // ── 方案C: 兜底 - 显示所有维度 ──
        let html = '<div style="font-weight:600;font-size:13px;margin-bottom:6px">维度评分</div>'
        props.data.forEach((d, i) => {
          const val = params.value[i]
          const c = colors[i % colors.length]
          html += `<div style="display:flex;justify-content:space-between;gap:16px;padding:2px 0;border-bottom:${i < props.data.length - 1 ? '1px solid #f3f4f6' : 'none'}">
            <span style="font-size:12px;color:#374151">${d.name}</span>
            <span style="font-size:13px;font-weight:600;color:${c}">${typeof val === 'number' ? val.toFixed(1) : val}</span>
          </div>`
        })
        return html
      },
    },
    legend: props.mode === 'dual' ? {
      bottom: 0,
      left: 'center',
      itemWidth: 14,
      itemHeight: 8,
      icon: 'roundRect',
      textStyle: { color: '#6b7280', fontSize: 12 },
      data: ['我的技能', '市场需求'],
    } : undefined,
    radar: {
      indicator: indicators,
      radius: '58%',
      center: ['50%', '52%'],
      axisName: {
        color: '#4b5563',
        fontSize: 10,
        lineHeight: 13,
        padding: [2, 0],
        // 超过5个字自动换行显示
        formatter: (name) => {
          return name.length > 5 ? name.slice(0, 4) + '\n' + name.slice(4) : name
        },
      },
      splitArea: {
        areaStyle: {
          color: ['rgba(99,102,241,0.02)', 'rgba(99,102,241,0.04)', 'rgba(99,102,241,0.06)'],
        },
      },
      splitLine: { lineStyle: { color: '#e5e7eb', width: 1 } },
      axisLine: { lineStyle: { color: '#e5e7eb', width: 1 } },
    },
    series: props.mode === 'dual'
      ? [{
          type: 'radar',
          symbol: 'circle',
          symbolSize: 7,
          animationDuration: 500,
          animationEasing: 'cubicOut',
          data: [{
            value: props.data.map(d => Math.min(Math.max(d.skill_score ?? 0, 0), 10)),
            name: '我的技能',
            areaStyle: { color: 'rgba(99,102,241,0.15)' },
            lineStyle: { color: '#6366f1', width: 2 },
            itemStyle: { color: '#6366f1' },
          }],
          emphasis: {
            lineStyle: { width: 3, color: '#4f46e5' },
            itemStyle: { color: '#4f46e5', borderWidth: 3, borderColor: '#fff' },
          },
        }, {
          type: 'radar',
          symbol: 'circle',
          symbolSize: 7,
          animationDuration: 500,
          animationEasing: 'cubicOut',
          data: [{
            value: props.data.map(d => Math.min(Math.max(d.market_score ?? 0, 0), 10)),
            name: '市场需求',
            areaStyle: { color: 'rgba(245,158,11,0.15)' },
            lineStyle: { color: '#f59e0b', width: 2 },
            itemStyle: { color: '#f59e0b' },
          }],
          emphasis: {
            lineStyle: { width: 3, color: '#d97706' },
            itemStyle: { color: '#d97706', borderWidth: 3, borderColor: '#fff' },
          },
        }]
      : [{
          type: 'radar',
          symbol: 'circle',
          symbolSize: 10,
          animationDuration: 500,
          animationEasing: 'cubicOut',
          data: [{
            value: props.data.map(d => Math.min(Math.max(d.score, 0), 10)),
            name: '学习画像',
            areaStyle: { color: 'rgba(99,102,241,0.18)' },
            lineStyle: { color: '#6366f1', width: 2 },
            itemStyle: { color: '#6366f1', borderColor: '#fff', borderWidth: 1 },
          }],
          emphasis: {
            lineStyle: { width: 3, color: '#4f46e5' },
            itemStyle: { color: '#4f46e5', borderWidth: 3, borderColor: '#fff' },
          },
        }],
  }, true)

  // ── 鼠标移动跟踪：计算最近维度 ──
  chart.off('mousemove')
  chart.on('mousemove', (params) => {
    if (params.componentType === 'series' && params.seriesType === 'radar') {
      const center = chart.convertToPixel('polar', [0, 0])
      if (!center) { hoveredDimIdx = -1; return }
      const dx = params.event.offsetX - center[0]
      const dy = params.event.offsetY - center[1]
      let angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90
      if (angle < 0) angle += 360
      const n = props.data.length
      const step = 360 / n
      hoveredDimIdx = Math.round(angle / step) % n
    }
  })
  chart.off('mouseout')
  chart.on('mouseout', () => { hoveredDimIdx = -1 })
}

onMounted(() => { setTimeout(render, 150) })
watch(() => props.data, () => render(), { deep: true })

onBeforeUnmount(() => { chart?.dispose(); chart = null })
</script>

<style scoped>
.radar-chart { flex-shrink: 0; }
</style>
