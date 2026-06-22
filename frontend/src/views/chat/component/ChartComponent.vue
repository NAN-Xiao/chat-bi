<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { getChartInstance } from '@/views/chat/component/index.ts'
import type { BaseChart, ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
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
    const roleKey = `${axis.type || 'column'}:${axis.value}`
    if (axis.value && usedValues.has(roleKey)) {
      return
    }
    if (axis.value) {
      usedValues.add(roleKey)
    }
    _list.push(axis)
  }
  params.x.forEach((column) => {
    pushAxis({ name: column.name, value: column.value, type: 'x' })
  })
  params.y.forEach((column) => {
    pushAxis({
      name: column.name,
      value: column.value,
      type: 'y',
      'multi-quota': column['multi-quota'],
    })
  })
  params.series.forEach((column) => {
    pushAxis({ name: column.name, value: column.value, type: 'series' })
  })
  if (params.multiQuotaName) {
    pushAxis({
      name: params.multiQuotaName,
      value: params.multiQuotaName,
      type: 'other-info',
      hidden: true,
    })
  }
  params.columns.forEach((column) => {
    pushAxis({ name: column.name, value: column.value })
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
