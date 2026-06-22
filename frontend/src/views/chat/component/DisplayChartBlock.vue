<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import ChartInsightHeader from '@/views/chat/component/ChartInsightHeader.vue'
import type { ChatMessage } from '@/api/chat.ts'
import { computed, nextTick, ref } from 'vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import { useI18n } from 'vue-i18n'
import { buildInsightColumns, resolveInsightLayout } from '@/views/chat/component/chartInsight.ts'

const props = defineProps<{
  id?: number | string
  chartType: ChartTypes
  message: ChatMessage
  data: Array<{ [key: string]: any }>
  loadingData?: boolean
  showLabel?: boolean
}>()

const { t } = useI18n()

const chartObject = computed<{
  type: ChartTypes
  title: string
  axis: {
    x: { name: string; value: string }
    y: { name: string; value: string } | Array<{ name: string; value: string }>
    series: { name: string; value: string }
    'multi-quota': {
      name: string
      value: Array<string>
    }
  }
  columns: Array<{ name: string; value: string }>
}>(() => {
  if (props.message?.record?.chart) {
    return JSON.parse(props.message.record.chart)
  }
  return {}
})

const xAxis = computed(() => {
  const axis = chartObject.value?.axis
  if (axis?.x) {
    return [axis.x]
  }
  return []
})
const yAxis = computed(() => {
  const axis = chartObject.value?.axis
  if (!axis?.y) {
    return []
  }

  const y = axis.y
  const multiQuotaValues = axis['multi-quota']?.value || []

  // 统一处理为数组
  const yArray = Array.isArray(y) ? [...y] : [{ ...y }]

  // 标记 multi-quota
  return yArray.map((item) => ({
    ...item,
    'multi-quota': multiQuotaValues.includes(item.value),
  }))
})
const series = computed(() => {
  const axis = chartObject.value?.axis
  if (axis?.series) {
    return [axis.series]
  }
  return []
})

const multiQuotaName = computed(() => {
  return chartObject.value?.axis?.['multi-quota']?.name
})

const isTableChart = computed(() => props.chartType === 'table')
const showInsightHeader = computed(() => {
  return props.chartType !== 'table' && props.chartType !== 'metric' && props.data?.length > 0
})
const insightColumns = computed(() =>
  buildInsightColumns(props.data, [
    ...xAxis.value,
    ...yAxis.value,
    ...series.value,
    ...(chartObject.value?.columns || []),
  ])
)
const insightLayout = computed(() =>
  resolveInsightLayout({
    chartType: props.chartType,
    data: props.data,
    x: xAxis.value,
    y: yAxis.value,
    series: series.value,
  })
)

const chartRef = ref()

function onTypeChange() {
  nextTick(() => {
    chartRef.value?.destroyChart()
    chartRef.value?.renderChart()
  })
}
function getViewInfo() {
  return {
    chart: {
      columns: chartObject.value?.columns,
      type: props.chartType,
      xAxis: xAxis.value,
      yAxis: yAxis.value,
      series: series.value,
      title: chartObject.value.title,
    },
    data: { data: props.data },
  }
}
function getExcelData() {
  return chartRef.value?.getExcelData()
}

defineExpose({
  onTypeChange,
  getViewInfo,
  getExcelData,
})
</script>

<template>
  <div
    v-if="message.record?.chart"
    class="chart-base-container"
    :class="{ 'is-table-chart': isTableChart, 'has-side-insight': insightLayout === 'side' }"
  >
    <ChartInsightHeader
      v-if="showInsightHeader && insightLayout === 'top'"
      :chart-type="chartType"
      :data="data"
      :columns="[...(chartObject?.columns || []), ...insightColumns]"
      :x="xAxis"
      :y="yAxis"
      :series="series"
      :sql="message.record?.sql"
    />
    <div
      v-if="message.record.id && data?.length > 0"
      class="chart-content-row"
      :class="{ 'side-layout': insightLayout === 'side' }"
    >
      <ChartInsightHeader
        v-if="showInsightHeader && insightLayout === 'side'"
        layout="side"
        :max-stats="4"
        :chart-type="chartType"
        :data="data"
        :columns="[...(chartObject?.columns || []), ...insightColumns]"
        :x="xAxis"
        :y="yAxis"
        :series="series"
        :sql="message.record?.sql"
      />
      <ChartComponent
        :id="id ?? 'default_chat_id'"
        ref="chartRef"
        :type="chartType"
        :columns="[...(chartObject?.columns || []), ...insightColumns]"
        :x="xAxis"
        :y="yAxis"
        :series="series"
        :data="data"
        :multi-quota-name="multiQuotaName"
        :show-label="showLabel"
      />
    </div>
    <el-empty v-else :description="loadingData ? t('chat.loading_data') : t('chat.no_data')" />
  </div>
</template>

<style scoped lang="less">
.chart-base-container {
  box-sizing: border-box;
  height: 100%;
  width: 100%;
  padding: 12px 14px 10px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
  border: 1px solid #dfe8f3;
  box-shadow: 0 10px 24px rgba(36, 64, 102, 0.06);

  &.is-table-chart {
    padding: 12px 22px 6px 14px;
  }

  .chart-content-row {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .chart-content-row.side-layout {
    flex-direction: row;
    align-items: stretch;
  }

  :deep(.chart-container) {
    flex: 1 1 auto;
    min-height: 0;
  }
}
</style>
