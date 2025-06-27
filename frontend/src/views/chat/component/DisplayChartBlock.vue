<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type { ChatMessage } from '@/api/chat.ts'
import { computed, nextTick, ref } from 'vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'

const props = defineProps<{
  id?: number | string
  chartType: ChartTypes
  message: ChatMessage
  data: Array<{ [key: string]: any }>
}>()

const chartObject = computed<{
  type: ChartTypes
  title: string
  axis: {
    x: { name: string; value: string }
    y: { name: string; value: string }
    series: { name: string; value: string }
  }
  columns: Array<{ name: string; value: string }>
}>(() => {
  if (props.message?.record?.chart) {
    return JSON.parse(props.message.record.chart)
  }
  return {}
})

const xAxis = computed(() => {
  if (chartObject.value?.axis?.x) {
    return [chartObject.value.axis.x]
  }
  return []
})
const yAxis = computed(() => {
  if (chartObject.value?.axis?.y) {
    return [chartObject.value.axis.y]
  }
  return []
})
const series = computed(() => {
  if (chartObject.value?.axis?.series) {
    return [chartObject.value.axis.series]
  }
  return []
})

const chartRef = ref()

function onTypeChange() {
  nextTick(() => {
    chartRef.value?.destroyChart()
    chartRef.value?.renderChart()
  })
}

defineExpose({
  onTypeChange,
})
</script>

<template>
  <div v-if="message?.record">
    <div v-if="message.record.chart" class="chart-base-container">
      <div v-if="data?.length > 0">
        <ChartComponent
          v-if="message.record.id"
          :id="id ?? 'default_chat_id'"
          ref="chartRef"
          :type="chartType"
          :columns="chartObject?.columns"
          :x="xAxis"
          :y="yAxis"
          :series="series"
          :data="data"
        />
      </div>
      <el-empty v-else description="No Data" />
    </div>
  </div>
</template>

<style scoped lang="less">
.chart-base-container {
  padding: 20px;
  background: rgba(224, 224, 226, 0.29);
}
</style>
