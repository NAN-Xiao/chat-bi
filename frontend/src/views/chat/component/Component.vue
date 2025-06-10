<script setup lang="ts">
import {computed, onMounted, onUnmounted} from "vue";
import {getChartInstance} from "@/views/chat/component/index.ts";
import type {BaseChart} from "@/views/chat/component/BaseChart.ts";

const params = withDefaults(defineProps<{
  id: string | number
  type: string
  data?: Array<{ [key: string]: any }>
  columns?: Array<{ name: string, value: string }>
  x?: Array<{ name: string, value: string }>
  y?: Array<{ name: string, value: string }>
}>(), {
  data: () => [],
  columns: () => [],
  x: () => [],
  y: () => [],
})

const chartId = computed(() => {
  return "chart-component-" + params.id
})

const axis = computed(() => {
  const _list: Array<{ name: string, value: string, type?: 'x' | 'y' }> = []
  params.columns.forEach(column => {
    _list.push({name: column.name, value: column.value})
  })
  params.x.forEach(column => {
    _list.push({name: column.name, value: column.value, type: 'x'})
  })
  params.y.forEach(column => {
    _list.push({name: column.name, value: column.value, type: 'y'})
  })
  return _list
})

let chartInstance: BaseChart | undefined

function renderChart() {
  chartInstance = getChartInstance(params.type, chartId.value)
  console.log(chartInstance)
  if (chartInstance) {
    chartInstance.init(axis.value, params.data)
    chartInstance.render()
  }
}

function destroyChart() {
  if (chartInstance) {
    chartInstance.destroy()
    chartInstance = undefined
  }
}

defineExpose({
  renderChart,
  destroyChart,
})

onMounted(() => {
  renderChart()
})

onUnmounted(() => {
  destroyChart()
})

</script>

<template>
  <div class="chart-container" :id="chartId"></div>
</template>

<style scoped lang="less">
.chart-container {
  height: 100%;
  width: 100%;
  min-height: 360px;
  min-width: 360px;
}
</style>