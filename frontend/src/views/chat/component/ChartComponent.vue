<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getChartInstance } from '@/views/chat/component/index.ts'
import {
  axisValue,
  type BaseChart,
  type ChartAxis,
  type ChartData,
  type ChartForecastConfig,
} from '@/views/chat/component/BaseChart.ts'
import { useEmitt } from '@/utils/useEmitt.ts'

const params = withDefaults(
  defineProps<{
    id: string | number
    type: string
    data?: Array<ChartData>
    columns?: Array<ChartAxis>
    x?: Array<ChartAxis>
    y?: Array<ChartAxis>
    series?: Array<ChartAxis>
    multiQuotaName?: string | undefined
    showLabel?: boolean
    hideZeroLabel?: boolean
    hideValueAxis?: boolean
    forecast?: ChartForecastConfig
  }>(),
  {
    data: () => [],
    columns: () => [],
    x: () => [],
    y: () => [],
    series: () => [],
    multiQuotaName: undefined,
    showLabel: false,
    hideZeroLabel: false,
    hideValueAxis: false,
    forecast: undefined,
  }
)

const chartId = computed(() => {
  return 'chart-component-' + params.id
})

const axis = computed(() => {
  const _list: Array<ChartAxis> = []
  const usedValues = new Set<string>()
  const pushAxis = (axis: ChartAxis) => {
    const value = axisValue(axis)
    if (!value) {
      return
    }
    const normalizedAxis: ChartAxis = { ...axis, value }
    const roleKey = `${normalizedAxis.type || 'column'}:${value}`
    if (usedValues.has(roleKey)) {
      return
    }
    usedValues.add(roleKey)
    _list.push(normalizedAxis)
  }
  params.x.forEach((column) => {
    pushAxis({ ...column, value: axisValue(column), type: 'x' })
  })
  params.y.forEach((column) => {
    pushAxis({
      ...column,
      value: axisValue(column),
      type: 'y',
      'multi-quota': column['multi-quota'],
    })
  })
  params.series.forEach((column) => {
    pushAxis({ ...column, value: axisValue(column), type: 'series' })
  })
  if (params.multiQuotaName) {
    pushAxis({
      value: params.multiQuotaName,
      type: 'other-info',
      hidden: true,
    })
  }
  params.columns.forEach((column) => {
    pushAxis({ ...column, value: axisValue(column) })
  })
  return _list
})

let chartInstance: BaseChart | undefined
const chartContainerRef = ref<HTMLElement>()
let resizeObserver: ResizeObserver | undefined
let renderTimer: number | undefined
let renderToken = 0
const maxRenderRetries = 2

function hasRenderableSize() {
  const element = chartContainerRef.value
  return Boolean(element && element.clientWidth > 0 && element.clientHeight > 0)
}

function hasRenderedOutput() {
  const element = chartContainerRef.value
  if (!element) {
    return false
  }
  if (params.type === 'metric') {
    return element.children.length > 0
  }
  return Boolean(element.querySelector('canvas, svg'))
}

function scheduleRenderChart(delay = 0, retry = 0) {
  if (renderTimer) {
    window.clearTimeout(renderTimer)
  }
  renderTimer = window.setTimeout(() => {
    renderTimer = undefined
    nextTick(() => {
      if (hasRenderableSize()) {
        renderChart(retry)
      }
    })
  }, delay)
}

function retryRenderIfNeeded(token: number, retry: number) {
  window.setTimeout(() => {
    if (token !== renderToken || !hasRenderableSize() || hasRenderedOutput()) {
      return
    }
    if (retry < maxRenderRetries) {
      scheduleRenderChart(120, retry + 1)
    }
  }, 120)
}

function handleRenderError(error: unknown, token: number, retry: number) {
  if (token !== renderToken) {
    return
  }
  console.warn('[ChartComponent] chart render failed, retrying if possible', error)
  if (retry < maxRenderRetries) {
    scheduleRenderChart(160, retry + 1)
  }
}

function renderChart(retry = 0) {
  if (!hasRenderableSize()) {
    return
  }
  const token = ++renderToken
  destroyChart(false)
  const container = chartContainerRef.value
  if (!container) {
    return
  }
  chartInstance = getChartInstance(params.type, container)
  if (chartInstance) {
    chartInstance.showLabel = params.showLabel
    chartInstance.hideZeroLabel = params.hideZeroLabel
    chartInstance.hideValueAxis = params.hideValueAxis
    chartInstance.forecast = params.forecast
    chartInstance.init(axis.value, params.data)
    try {
      Promise.resolve(chartInstance.render())
        .then(() => retryRenderIfNeeded(token, retry))
        .catch((error) => handleRenderError(error, token, retry))
    } catch (error) {
      handleRenderError(error, token, retry)
    }
  }
}

function destroyChart(invalidate = true) {
  if (invalidate) {
    renderToken += 1
  }
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = undefined
  }
  chartContainerRef.value?.replaceChildren()
}

watch(
  () => ({
    type: params.type,
    columns: params.columns,
    x: params.x,
    y: params.y,
    series: params.series,
    data: params.data,
    multiQuotaName: params.multiQuotaName,
    showLabel: params.showLabel,
    hideZeroLabel: params.hideZeroLabel,
    hideValueAxis: params.hideValueAxis,
    forecast: params.forecast,
  }),
  () => {
    scheduleRenderChart()
  },
  { deep: true, flush: 'post' }
)

function getExcelData() {
  return {
    axis: axis.value,
    data: params.data,
  }
}

useEmitt({
  name: 'view-render-all',
  callback: () => scheduleRenderChart(),
})

useEmitt({
  name: `view-render-${params.id}`,
  callback: () => scheduleRenderChart(),
})

defineExpose({
  renderChart: () => scheduleRenderChart(),
  destroyChart,
  getExcelData,
  getElement: () => chartContainerRef.value,
})

onMounted(() => {
  resizeObserver = new ResizeObserver(() => scheduleRenderChart(80))
  if (chartContainerRef.value) {
    resizeObserver.observe(chartContainerRef.value)
    if (chartContainerRef.value.parentElement) {
      resizeObserver.observe(chartContainerRef.value.parentElement)
    }
  }
  window.addEventListener('resize', handlePageRestore)
  window.addEventListener('pageshow', handlePageRestore)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  scheduleRenderChart()
  scheduleRenderChart(160)
})

onUnmounted(() => {
  if (renderTimer) {
    window.clearTimeout(renderTimer)
    renderTimer = undefined
  }
  resizeObserver?.disconnect()
  window.removeEventListener('resize', handlePageRestore)
  window.removeEventListener('pageshow', handlePageRestore)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  destroyChart()
})

function handlePageRestore() {
  scheduleRenderChart(120)
}

function handleVisibilityChange() {
  if (!document.hidden) {
    handlePageRestore()
  }
}
</script>

<template>
  <div :id="chartId" ref="chartContainerRef" class="chart-container"></div>
</template>

<style scoped lang="less">
.chart-container {
  height: 100%;
  width: 100%;
}
</style>
