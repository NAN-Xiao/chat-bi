<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { reactive } from 'vue'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'

const state = reactive({
  chartInfo: {
    id: null as string | null,
    type: '' as string,
    columns: [] as ChartAxis[],
    xAxis: [] as ChartAxis[],
    yAxis: [] as ChartAxis[],
    series: [] as ChartAxis[],
    data: [] as ChartData[],
  },
})
</script>

<template>
  <div class="chart-base-container">
    <div>
      <ChartComponent
        v-if="state.chartInfo.id"
        :id="state.chartInfo.id"
        ref="chartRef"
        :type="state.chartInfo.type"
        :columns="state.chartInfo.columns"
        :x="state.chartInfo.xAxis"
        :y="state.chartInfo.yAxis"
        :series="state.chartInfo.series"
        :data="state.chartInfo.data"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.chart-base-container {
  padding: 20px;
  background: rgba(224, 224, 226, 0.29);
}
</style>
