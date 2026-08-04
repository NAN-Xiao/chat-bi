<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getChartInstance } from '@/views/chat/component/index.ts'
import {
  buildChartLayoutContext,
  type ChartDensity,
  type ChartSurface,
} from '@/views/chat/component/chartLayout.ts'
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
    surface?: ChartSurface
    hasOuterTitle?: boolean
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
    surface: 'preview',
    hasOuterTitle: false,
  }
)
const emit = defineEmits<{
  (event: 'render-ready'): void
}>()

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
let stagingChartInstance: BaseChart | undefined
const chartContainerRef = ref<HTMLElement>()
const chartRenderHostRef = ref<HTMLElement>()
const activeLayerRef = ref<HTMLElement>()
const stagingLayerRef = ref<HTMLElement>()
const showInitialLoading = ref(true)
const chartSize = ref({ width: 0, height: 0 })
const previousDensity = ref<ChartDensity>()
let resizeObserver: ResizeObserver | undefined
let renderTimer: number | undefined
let renderReadyFrame: number | undefined
let renderToken = 0
let rerenderAfterStaging = false
let pendingRenderRetry = 0
const maxRenderRetries = 2
const destroyedChartInstances = new WeakSet<BaseChart>()

const currentLayoutContext = computed(() => {
  const context = buildChartLayoutContext({
    ...chartSize.value,
    surface: params.surface,
    hasOuterTitle: params.hasOuterTitle,
    previousDensity: previousDensity.value,
  })
  previousDensity.value = context.density
  return context
})

function measureChartContainer() {
  const element = chartContainerRef.value
  if (!element) return { renderable: false, changed: false }
  const width = Math.round(element.clientWidth)
  const height = Math.round(element.clientHeight)
  if (width <= 0 || height <= 0) return { renderable: false, changed: false }
  const changed = width !== chartSize.value.width || height !== chartSize.value.height
  if (changed) {
    chartSize.value = { width, height }
  }
  return { renderable: true, changed }
}

function hasRenderableSize() {
  return measureChartContainer().renderable
}

function hasRenderedOutput(element = activeLayerRef.value || chartRenderHostRef.value) {
  if (!element) {
    return false
  }
  if (params.type === 'metric') {
    return element.children.length > 0
  }
  if (params.type === 'table') {
    return Boolean(
      element.querySelector('canvas, svg, .s2-table, .s2-spreadsheet, .s2-container') ||
        element.children.length > 0
    )
  }
  return Boolean(element.querySelector('canvas, svg'))
}

function hasActiveRenderedLayer() {
  return Boolean(
    activeLayerRef.value &&
      !stagingLayerRef.value &&
      hasRenderedOutput(activeLayerRef.value)
  )
}

function cancelPendingRenderReady() {
  if (renderReadyFrame === undefined) {
    return
  }
  window.cancelAnimationFrame(renderReadyFrame)
  renderReadyFrame = undefined
}

function scheduleRenderReady() {
  cancelPendingRenderReady()
  renderReadyFrame = window.requestAnimationFrame(() => {
    renderReadyFrame = undefined
    if (hasActiveRenderedLayer()) {
      emit('render-ready')
    }
  })
}

function scheduleRenderChart(delay = 0, retry = 0, invalidate = false) {
  if (!hasActiveRenderedLayer()) {
    cancelPendingRenderReady()
  }
  if (invalidate && stagingLayerRef.value && !activeLayerRef.value) {
    rerenderAfterStaging = true
    pendingRenderRetry = retry
    return
  }
  if (invalidate) {
    renderToken += 1
  }
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

function drainPendingRender() {
  if (!rerenderAfterStaging) {
    return
  }
  const retry = pendingRenderRetry
  rerenderAfterStaging = false
  pendingRenderRetry = 0
  scheduleRenderChart(0, retry)
}

function configureChart(instance: BaseChart) {
  instance.layoutContext = currentLayoutContext.value
  instance.showLabel = params.showLabel
  instance.hideZeroLabel = params.hideZeroLabel
  instance.hideValueAxis = params.hideValueAxis
  instance.forecast = params.forecast
  instance.init(axis.value, params.data)
}

function destroyChartInstance(instance: BaseChart | undefined) {
  if (!instance || destroyedChartInstances.has(instance)) {
    return
  }
  destroyedChartInstances.add(instance)
  try {
    instance.destroy()
  } catch (error) {
    console.warn('[ChartComponent] chart destroy failed', error)
  }
}

function cleanupStagedChart(instance: BaseChart | undefined, layer: HTMLElement | undefined) {
  destroyChartInstance(instance)
  layer?.remove()
  if (stagingChartInstance === instance) {
    stagingChartInstance = undefined
  }
  if (stagingLayerRef.value === layer) {
    stagingLayerRef.value = undefined
  }
}

function commitStagedChart(nextInstance: BaseChart, stagingLayer: HTMLElement, token: number) {
  if (token !== renderToken) {
    cleanupStagedChart(nextInstance, stagingLayer)
    drainPendingRender()
    return
  }
  const previousInstance = chartInstance
  const previousLayer = activeLayerRef.value
  stagingLayer.classList.replace('chart-render-layer--staging', 'chart-render-layer--active')
  chartInstance = nextInstance
  activeLayerRef.value = stagingLayer
  stagingChartInstance = undefined
  stagingLayerRef.value = undefined
  showInitialLoading.value = false
  if (!rerenderAfterStaging) {
    scheduleRenderReady()
  }
  destroyChartInstance(previousInstance)
  previousLayer?.remove()
  drainPendingRender()
}

function handleAtomicRenderError(
  error: unknown,
  nextInstance: BaseChart | undefined,
  stagingLayer: HTMLElement,
  token: number,
  retry: number
) {
  cleanupStagedChart(nextInstance, stagingLayer)
  if (token !== renderToken) {
    drainPendingRender()
    return
  }
  console.warn('[ChartComponent] chart render failed, retrying if possible', error)
  if (rerenderAfterStaging) {
    drainPendingRender()
    return
  }
  if (retry < maxRenderRetries) {
    scheduleRenderChart(160, retry + 1)
  }
}

function renderAtomicChart(retry = 0) {
  if (stagingLayerRef.value) {
    rerenderAfterStaging = true
    pendingRenderRetry = retry
    return
  }
  const host = chartRenderHostRef.value
  if (!host) {
    return
  }
  const token = ++renderToken
  const stagingLayer = document.createElement('div')
  stagingLayer.className = 'chart-render-layer chart-render-layer--staging'
  const stagingMount = document.createElement('div')
  stagingMount.className = 'chart-render-mount'
  stagingLayer.appendChild(stagingMount)
  host.appendChild(stagingLayer)
  stagingLayerRef.value = stagingLayer
  let nextInstance: BaseChart | undefined
  try {
    nextInstance = getChartInstance(params.type, stagingMount)
    stagingChartInstance = nextInstance
    if (!nextInstance) {
      throw new Error(`Unsupported chart type: ${params.type}`)
    }
    const renderInstance = nextInstance
    configureChart(renderInstance)
    Promise.resolve(renderInstance.render())
      .then(() => {
        if (token !== renderToken) {
          cleanupStagedChart(renderInstance, stagingLayer)
          drainPendingRender()
          return
        }
        if (!hasRenderedOutput(stagingLayer)) {
          handleAtomicRenderError(
            new Error(`Chart rendered without output: ${params.type}`),
            renderInstance,
            stagingLayer,
            token,
            retry
          )
          return
        }
        commitStagedChart(renderInstance, stagingLayer, token)
      })
      .catch((error) => handleAtomicRenderError(error, renderInstance, stagingLayer, token, retry))
  } catch (error) {
    handleAtomicRenderError(error, nextInstance, stagingLayer, token, retry)
  }
}

function renderChart(retry = 0) {
  if (!measureChartContainer().renderable) {
    return
  }
  renderAtomicChart(retry)
}

function destroyChart(invalidate = true) {
  cancelPendingRenderReady()
  if (invalidate) {
    renderToken += 1
  }
  rerenderAfterStaging = false
  pendingRenderRetry = 0
  cleanupStagedChart(stagingChartInstance, stagingLayerRef.value)
  destroyChartInstance(chartInstance)
  chartInstance = undefined
  activeLayerRef.value?.remove()
  activeLayerRef.value = undefined
  chartRenderHostRef.value?.replaceChildren()
  showInitialLoading.value = true
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
    scheduleRenderChart(0, 0, true)
  },
  { deep: true, flush: 'post' }
)

function getExcelData() {
  return {
    axis: axis.value,
    data: params.data,
  }
}

function handleViewRenderAll(event?: { reason?: string }) {
  if (event?.reason !== 'resize') {
    scheduleRenderChart()
    return
  }
  const { changed } = measureChartContainer()
  if (changed) {
    scheduleRenderChart()
  }
}

useEmitt({
  name: 'view-render-all',
  callback: handleViewRenderAll,
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
  resizeObserver = new ResizeObserver(() => {
    const { changed } = measureChartContainer()
    if (changed && params.type !== 'table') scheduleRenderChart(80)
  })
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
  if (params.type === 'table' && hasRenderedOutput()) {
    return
  }
  scheduleRenderChart(120)
}

function handleVisibilityChange() {
  if (!document.hidden) {
    handlePageRestore()
  }
}
</script>

<template>
  <div :id="chartId" ref="chartContainerRef" class="chart-container">
    <div
      v-if="showInitialLoading && params.surface !== 'dashboard'"
      class="chart-component-loading"
      aria-label="loading"
    >
      <span class="chart-component-loading-ring"></span>
    </div>
    <div ref="chartRenderHostRef" class="chart-render-host"></div>
  </div>
</template>

<style scoped lang="less">
.chart-container {
  height: 100%;
  min-height: 0;
  position: relative;
  width: 100%;
}

.chart-render-host,
:deep(.chart-render-layer) {
  height: 100%;
  inset: 0;
  position: absolute;
  width: 100%;
}

:deep(.chart-render-layer--staging) {
  pointer-events: none;
  visibility: hidden;
}

:deep(.chart-render-mount) {
  height: 100%;
  width: 100%;
}

.chart-component-loading {
  align-items: center;
  display: flex;
  height: 100%;
  justify-content: center;
  position: relative;
  width: 100%;
  z-index: 1;
}

.chart-component-loading-ring {
  animation: chart-component-loading-spin 0.85s linear infinite;
  border: 3px solid #eef1f5;
  border-radius: 50%;
  border-top-color: var(--ed-color-primary, #2f6bff);
  height: 28px;
  width: 28px;
}

@keyframes chart-component-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
