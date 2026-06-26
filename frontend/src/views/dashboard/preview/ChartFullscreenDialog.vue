<script setup lang="ts">
import { computed } from 'vue'
import { Close } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import ChartInsightHeader from '@/views/chat/component/ChartInsightHeader.vue'
import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import { buildInsightColumns } from '@/views/chat/component/chartInsight.ts'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
    viewInfo: Record<string, any>
  }>(),
  {
    modelValue: false,
  }
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()
const { t } = useI18n()

const chartConfig = computed(() => props.viewInfo?.chart || {})
const chartType = computed<ChartTypes>(
  () => (chartConfig.value?.type || chartConfig.value?.sourceType || 'table') as ChartTypes
)
const rows = computed<Array<ChartData>>(() =>
  Array.isArray(props.viewInfo?.data?.data) ? props.viewInfo.data.data : []
)
const columns = computed<Array<ChartAxis>>(() =>
  Array.isArray(chartConfig.value?.columns) ? chartConfig.value.columns : []
)
const xAxis = computed<Array<ChartAxis>>(() =>
  Array.isArray(chartConfig.value?.xAxis) ? chartConfig.value.xAxis : []
)
const yAxis = computed<Array<ChartAxis>>(() =>
  Array.isArray(chartConfig.value?.yAxis) ? chartConfig.value.yAxis : []
)
const seriesAxis = computed<Array<ChartAxis>>(() =>
  Array.isArray(chartConfig.value?.series) ? chartConfig.value.series : []
)
const insightColumns = computed(() =>
  buildInsightColumns(rows.value, [
    ...columns.value,
    ...xAxis.value,
    ...yAxis.value,
    ...seriesAxis.value,
  ])
)
const chartColumns = computed(() => [...columns.value, ...insightColumns.value])
const outerId = computed(() => `fullscreen-chart-${props.viewInfo?.id || 'view'}`)
const title = computed(() => chartConfig.value?.title || t('dashboard.view'))
const typeLabel = computed(() => t(`chat.chart_type.${chartType.value}`))
const hasInsight = computed(
  () => chartType.value !== 'table' && chartType.value !== 'metric' && rows.value.length > 0
)
const sideSummaryTypes = new Set<ChartTypes>([
  'line',
  'area',
  'bar',
  'column',
  'scatter',
  'heatmap',
  'sankey',
  'treemap',
  'pie',
  'funnel',
])
const useSideSummary = computed(() => hasInsight.value && sideSummaryTypes.has(chartType.value))
const viewClasses = computed(() => [
  `chart-layout-${chartType.value}`,
  {
    'has-side-summary': useSideSummary.value,
    'has-top-summary': hasInsight.value && !useSideSummary.value,
    'is-table-layout': chartType.value === 'table',
    'is-metric-layout': chartType.value === 'metric',
  },
])

function closeDialog() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    v-if="modelValue"
    :model-value="modelValue"
    fullscreen
    append-to-body
    :show-close="false"
    class="dashboard-chart-fullscreen-dialog"
    header-class="dashboard-chart-fullscreen-header"
    body-class="dashboard-chart-fullscreen-body"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="chart-fullscreen-view" :class="viewClasses">
      <header class="fullscreen-header">
        <div class="fullscreen-title-block">
          <div class="fullscreen-title-row">
            <h2>{{ title }}</h2>
            <span class="chart-type-chip">{{ typeLabel }}</span>
          </div>
        </div>
        <el-tooltip effect="dark" :content="t('dashboard.chart_exit_fullscreen')" placement="left">
          <el-button class="chart-fullscreen-close" text @click="closeDialog">
            <el-icon size="18"><Close /></el-icon>
          </el-button>
        </el-tooltip>
      </header>

      <main class="fullscreen-content">
        <aside v-if="useSideSummary" class="fullscreen-summary-panel">
          <ChartInsightHeader
            :chart-type="chartType"
            :data="rows"
            :columns="chartColumns"
            :x="xAxis"
            :y="yAxis"
            :series="seriesAxis"
            :sql="viewInfo.sql"
            :insight="chartConfig?.insight"
            layout="side"
            density="regular"
            :max-stats="4"
          />
        </aside>

        <section class="fullscreen-chart-stage">
          <ChartInsightHeader
            v-if="hasInsight && !useSideSummary"
            class="fullscreen-top-summary"
            :chart-type="chartType"
            :data="rows"
            :columns="chartColumns"
            :x="xAxis"
            :y="yAxis"
            :series="seriesAxis"
            :sql="viewInfo.sql"
            :insight="chartConfig?.insight"
            compact
            density="compact"
            :max-stats="4"
          />

          <div class="fullscreen-plot-wrap">
            <div class="fullscreen-plot-surface">
              <ChartComponent
                :id="outerId"
                :type="chartType"
                :columns="chartColumns"
                :x="xAxis"
                :y="yAxis"
                :series="seriesAxis"
                :data="rows"
                :multi-quota-name="chartConfig?.multiQuotaName"
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  </el-dialog>
</template>

<style lang="less">
.dashboard-chart-fullscreen-dialog {
  padding: 0;
}

.dashboard-chart-fullscreen-header {
  display: none;
}

.dashboard-chart-fullscreen-body {
  height: 100vh;
  padding: 0;
  background: #f4f7fb;
}
</style>

<style scoped lang="less">
.chart-fullscreen-view {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  background:
    radial-gradient(circle at 12% 4%, rgba(47, 107, 255, 0.07), transparent 32%),
    linear-gradient(180deg, #ffffff 0%, #f4f7fb 100%);
  color: #14243a;
}

.fullscreen-header {
  height: 76px;
  padding: 18px 72px 12px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(221, 228, 238, 0.85);
}

.fullscreen-title-block {
  min-width: 0;
}

.fullscreen-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;

  h2 {
    margin: 0;
    max-width: min(920px, 72vw);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 20px;
    line-height: 28px;
    font-weight: 700;
    letter-spacing: 0;
  }
}

.chart-type-chip {
  flex: 0 0 auto;
  height: 24px;
  padding: 0 9px;
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: rgba(47, 107, 255, 0.09);
  color: #2f5ec7;
  font-size: 12px;
  font-weight: 600;
}

.chart-fullscreen-close {
  position: absolute;
  top: 18px;
  right: 24px;
  width: 32px;
  min-width: 32px;
  height: 32px;
  padding: 0;
  border-radius: 7px;
  color: #394b63;
  background: transparent;

  &:hover,
  &:focus {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.1);
  }
}

.fullscreen-content {
  min-height: 0;
  padding: 24px 32px 30px;
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  gap: 22px;
}

.fullscreen-summary-panel {
  min-height: 0;
  padding: 18px 18px 16px;
  align-self: stretch;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 4px 12px rgba(18, 34, 66, 0.035);
  overflow: hidden;

  :deep(.chart-insight-header.side) {
    width: 100%;
    padding: 0;
    margin: 0;
    border: 0;
  }
}

.fullscreen-chart-stage {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 16px;
}

.fullscreen-top-summary {
  padding: 14px 16px 12px;
  margin: 0;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 8px 24px rgba(18, 34, 66, 0.05);
}

.fullscreen-plot-wrap {
  min-width: 0;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.fullscreen-plot-surface {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 18px 20px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 12px;
  background: #ffffff;
  box-shadow:
    0 6px 18px rgba(18, 34, 66, 0.045),
    0 1px 3px rgba(18, 34, 66, 0.03);

  :deep(.chart-container) {
    min-height: 0;
  }
}

.chart-layout-line,
.chart-layout-area,
.chart-layout-scatter {
  .fullscreen-content {
    grid-template-columns: minmax(230px, 300px) minmax(0, 1fr);
  }

  .fullscreen-plot-surface {
    height: min(100%, 680px);
    max-height: calc(100vh - 168px);
  }
}

.chart-layout-column,
.chart-layout-heatmap {
  .fullscreen-content {
    grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  }
}

.chart-layout-bar {
  .fullscreen-content {
    grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  }

  .fullscreen-plot-surface {
    padding-left: 24px;
  }
}

.chart-layout-pie,
.chart-layout-funnel,
.chart-layout-treemap,
.chart-layout-sankey {
  .fullscreen-content {
    grid-template-columns: minmax(230px, 300px) minmax(0, 1fr);
  }

  .fullscreen-plot-surface {
    width: min(100%, 980px);
    justify-self: center;
  }
}

.is-metric-layout {
  .fullscreen-content {
    grid-template-columns: minmax(0, 1fr);
    place-items: center;
  }

  .fullscreen-chart-stage {
    width: min(760px, 100%);
    height: min(460px, 100%);
  }
}

.is-table-layout {
  .fullscreen-content {
    grid-template-columns: minmax(0, 1fr);
  }

  .fullscreen-plot-surface {
    padding: 12px;
  }
}

@media (max-width: 960px) {
  .fullscreen-header {
    height: 68px;
    padding: 16px 58px 10px 20px;
  }

  .fullscreen-content,
  .chart-layout-line .fullscreen-content,
  .chart-layout-area .fullscreen-content,
  .chart-layout-scatter .fullscreen-content,
  .chart-layout-column .fullscreen-content,
  .chart-layout-heatmap .fullscreen-content,
  .chart-layout-bar .fullscreen-content,
  .chart-layout-pie .fullscreen-content,
  .chart-layout-funnel .fullscreen-content,
  .chart-layout-treemap .fullscreen-content,
  .chart-layout-sankey .fullscreen-content {
    padding: 16px;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
  }

  .fullscreen-summary-panel {
    max-height: 190px;
  }

  .fullscreen-plot-surface {
    padding: 12px;
  }
}
</style>
