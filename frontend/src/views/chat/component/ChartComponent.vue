<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { getChartInstance } from '@/views/chat/component/index.ts'
import { axisValue, type BaseChart, type ChartAxis, type ChartData } from '@/views/chat/component/BaseChart.ts'
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

function renderChart() {
  destroyChart()
  chartInstance = getChartInstance(params.type, chartId.value)
  if (chartInstance) {
    chartInstance.showLabel = params.showLabel
    chartInstance.hideZeroLabel = params.hideZeroLabel
    chartInstance.hideValueAxis = params.hideValueAxis
    chartInstance.init(axis.value, params.data)
    chartInstance.render()
  }
}

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = undefined
  }
  document.getElementById(chartId.value)?.replaceChildren()
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
  }),
  () => {
    nextTick(() => {
      renderChart()
    })
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
  callback: renderChart,
})

useEmitt({
  name: `view-render-${params.id}`,
  callback: renderChart,
})

defineExpose({
  renderChart,
  destroyChart,
  getExcelData,
})

onMounted(() => {
  nextTick(() => {
    renderChart()
  })
})

onUnmounted(() => {
  destroyChart()
})
</script>

<template>
  <div :id="chartId" class="chart-container"></div>
</template>

<style scoped lang="less">
.chart-container {
  height: 100%;
  width: 100%;
}
</style>
