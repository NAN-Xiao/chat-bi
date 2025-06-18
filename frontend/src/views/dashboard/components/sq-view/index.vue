<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
defineProps({
  viewInfo: {
    type: Object,
    required: true,
  },
})

import { ref } from 'vue'

const chartRef = ref(null)
const renderChart = () => {
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.renderChart
}

defineExpose({
  renderChart,
})
</script>

<template>
  <div class="chart-base-container">
    <div style="height: 100%; width: 100%">
      <ChartComponent
        v-if="viewInfo.id"
        :id="viewInfo.id"
        ref="chartRef"
        :type="viewInfo.chart.type"
        :columns="viewInfo.chart.columns"
        :x="viewInfo.chart?.xAxis"
        :y="viewInfo.chart?.yAxis"
        :series="viewInfo.chart?.series"
        :data="viewInfo.data?.data"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.chart-base-container {
}
</style>
