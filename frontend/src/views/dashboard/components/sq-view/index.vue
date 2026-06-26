<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import ChartInsightHeader from '@/views/chat/component/ChartInsightHeader.vue'
import icon_window_mini_outlined from '@/assets/svg/icon_window-mini_outlined.svg'
import SqViewDisplay from '@/views/dashboard/components/sq-view/index.vue'
import { dashboardApi } from '@/api/dashboard.ts'
import { ElMessage } from 'element-plus-secondary'
const props = defineProps({
  viewInfo: {
    type: Object,
    required: true,
  },
  outerId: {
    type: String,
    required: false,
    default: null,
  },
  showPosition: {
    type: String,
    required: false,
    default: 'default',
  },
})

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChartPopover from '@/views/chat/chat-block/ChartPopover.vue'
import { buildInsightColumns, resolveInsightDisplay } from '@/views/chat/component/chartInsight.ts'
import ICON_TABLE from '@/assets/svg/chart/icon_form_outlined.svg'
import ICON_COLUMN from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import ICON_BAR from '@/assets/svg/chart/icon_bar_outlined.svg'
import ICON_LINE from '@/assets/svg/chart/icon_chart-line.svg'
import ICON_PIE from '@/assets/svg/chart/icon_pie_outlined.svg'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
const { t } = useI18n()
const containerRef = ref<HTMLElement | null>(null)
const chartRef = ref(null)
const currentChartType = ref<ChartTypes | undefined>(undefined)
const frameSize = ref({ width: 0, height: 0 })
const refreshing = ref(false)
let resizeObserver: ResizeObserver | undefined
let renderTimer: number | undefined
let progressTimer: number | undefined

const renderChart = () => {
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.destroyChart()
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.renderChart()
}

const enlargeDialogVisible = ref(false)

const enlargeView = () => {
  enlargeDialogVisible.value = true
}

function unique(values: Array<string | undefined | null>) {
  return Array.from(
    new Set(
      values
        .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
        .map((value) => `${value}`)
    )
  )
}

function getResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

async function refreshData() {
  if (!props.viewInfo?.datasource) {
    ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    return
  }
  if (!props.viewInfo?.sql?.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return
  }
  refreshing.value = true
  if (!props.viewInfo.data || typeof props.viewInfo.data !== 'object') {
    props.viewInfo.data = {}
  }
  props.viewInfo.dataState = 'loading'
  props.viewInfo.loadingProgress = 0
  startRefreshProgress()
  try {
    const result = await dashboardApi.preview_sql({
      datasource: props.viewInfo.datasource,
      sql: props.viewInfo.sql.trim(),
    })
    const fields = getResultFields(result)
    const data = Array.isArray(result?.data) ? result.data : []
    if (!props.viewInfo.data || typeof props.viewInfo.data !== 'object') {
      props.viewInfo.data = {}
    }
    props.viewInfo.data.fields = fields
    props.viewInfo.data.data = data
    props.viewInfo.fields = fields
    props.viewInfo.status = result?.status || 'success'
    props.viewInfo.message = result?.message || ''
    if (props.viewInfo.status === 'failed') {
      props.viewInfo.dataState = 'failed'
      ElMessage.error(props.viewInfo.message || t('dashboard.chart_refresh_failed'))
    } else {
      props.viewInfo.dataState = 'ready'
      ElMessage.success(t('dashboard.chart_refresh_success'))
    }
    props.viewInfo.loadingProgress = 100
    await nextTick()
    renderChart()
  } catch (error: any) {
    props.viewInfo.status = 'failed'
    props.viewInfo.message = error?.message || t('dashboard.chart_refresh_failed')
    props.viewInfo.dataState = 'failed'
    props.viewInfo.loadingProgress = 100
    ElMessage.error(error?.message || t('dashboard.chart_refresh_failed'))
  } finally {
    stopRefreshProgress()
    refreshing.value = false
  }
}

function startRefreshProgress() {
  stopRefreshProgress()
  progressTimer = window.setInterval(() => {
    if (!refreshing.value) {
      stopRefreshProgress()
      return
    }
    const current = Number(props.viewInfo?.loadingProgress || 0)
    props.viewInfo.loadingProgress = Math.min(95, current + Math.max(1, Math.round((96 - current) * 0.12)))
  }, 260)
}

function stopRefreshProgress() {
  if (progressTimer) {
    window.clearInterval(progressTimer)
    progressTimer = undefined
  }
}

function cleanExportFilename(name?: string) {
  return (name || t('dashboard.view')).replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
}

function collectExportFields() {
  const rows = Array.isArray(props.viewInfo?.data?.data) ? props.viewInfo.data.data : []
  const chart = chartRef.value as any
  const excelData = chart?.getExcelData?.()
  return unique([
    ...(Array.isArray(props.viewInfo?.data?.fields) ? props.viewInfo.data.fields : []),
    ...(Array.isArray(props.viewInfo?.fields) ? props.viewInfo.fields : []),
    ...(Array.isArray(excelData?.axis) ? excelData.axis.map((item: any) => item?.value || item?.name) : []),
    ...rows.flatMap((row: Record<string, any>) => Object.keys(row || {})),
  ])
}

function htmlCell(value: any) {
  if (value === null || value === undefined) {
    return ''
  }
  const text = typeof value === 'object' ? JSON.stringify(value) : `${value}`
  const safeText = /^[=+\-@]/.test(text) ? `\t${text}` : text
  return safeText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function exportTableData() {
  const rows = Array.isArray(props.viewInfo?.data?.data) ? props.viewInfo.data.data : []
  const fields = collectExportFields()
  if (!rows.length || !fields.length) {
    ElMessage.warning(t('dashboard.chart_export_no_data'))
    return
  }
  const tableRows = [
    `<tr>${fields.map((field) => `<th>${htmlCell(field)}</th>`).join('')}</tr>`,
    ...rows.map(
      (row: Record<string, any>) =>
        `<tr>${fields
          .map((field) => `<td style="mso-number-format:'\\@';">${htmlCell(row?.[field])}</td>`)
          .join('')}</tr>`
    ),
  ]
  const html = `<!doctype html><html><head><meta charset="utf-8" /></head><body><table>${tableRows.join('')}</table></body></html>`
  const blob = new Blob(['\ufeff' + html], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${cleanExportFilename(props.viewInfo?.chart?.title)}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
  ElMessage.success(t('dashboard.chart_export_success'))
}

const chartTypeList = computed(() => {
  const _list = []
  const pushChartType = (value: ChartTypes, icon: any) => {
    _list.push({
      value,
      name: t(`chat.chart_type.${value}`),
      icon,
    })
  }
  if (props.viewInfo.chart) {
    switch (props.viewInfo.chart['sourceType']) {
      case 'table':
        break
      case 'column':
      case 'bar':
      case 'line':
      case 'area':
        _list.push({
          value: 'column',
          name: t('chat.chart_type.column'),
          icon: ICON_COLUMN,
        })
        _list.push({
          value: 'bar',
          name: t('chat.chart_type.bar'),
          icon: ICON_BAR,
        })
        _list.push({
          value: 'line',
          name: t('chat.chart_type.line'),
          icon: ICON_LINE,
        })
        _list.push({
          value: 'area',
          name: t('chat.chart_type.area'),
          icon: ICON_LINE,
        })
        break
      case 'pie':
        pushChartType('pie', ICON_PIE)
        break
      case 'metric':
        pushChartType('metric', ICON_TABLE)
        break
      case 'funnel':
        pushChartType('funnel', ICON_BAR)
        break
      case 'heatmap':
        pushChartType('heatmap', ICON_COLUMN)
        break
      case 'scatter':
        pushChartType('scatter', ICON_LINE)
        break
      case 'sankey':
        pushChartType('sankey', ICON_COLUMN)
        break
      case 'treemap':
        pushChartType('treemap', ICON_PIE)
    }
  }

  return _list
})

function changeTable() {
  onTypeChange('table')
}

const chartType = computed<ChartTypes>({
  get() {
    if (currentChartType.value) {
      return currentChartType.value
    }
    return props.viewInfo.chart?.type ?? props.viewInfo.chart?.['sourceType'] ?? 'table'
  },
  set(v) {
    currentChartType.value = v
  },
})

const isDashboardSurface = computed(() => props.showPosition !== 'multiplexing')
const showInsightHeader = computed(() => {
  const type = chartType.value
  return type !== 'table' && type !== 'metric' && props.viewInfo.data?.data?.length > 0
})
const insightColumns = computed(() =>
  buildInsightColumns(props.viewInfo.data?.data, [
    ...(props.viewInfo.chart?.xAxis || []),
    ...(props.viewInfo.chart?.yAxis || []),
    ...(props.viewInfo.chart?.series || []),
    ...(props.viewInfo.chart?.columns || []),
  ])
)
const insightDisplay = computed(() =>
  resolveInsightDisplay({
    chartType: chartType.value,
    data: props.viewInfo.data?.data,
    x: props.viewInfo.chart?.xAxis,
    y: props.viewInfo.chart?.yAxis,
    series: props.viewInfo.chart?.series,
    width: frameSize.value.width,
    height: frameSize.value.height,
    dashboard: isDashboardSurface.value,
  })
)
const canShowInsightHeader = computed(() => {
  if (!showInsightHeader.value) {
    return false
  }
  return insightDisplay.value.show
})
const chartLoading = computed(
  () =>
    refreshing.value ||
    props.viewInfo?.dataState === 'loading' ||
    props.viewInfo?.status === 'loading'
)
const chartLoadingProgress = computed(() => {
  const progress = Number(props.viewInfo?.loadingProgress ?? 0)
  if (!Number.isFinite(progress)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(progress)))
})
const insightDensity = computed(() => insightDisplay.value.density)
const effectiveInsightLayout = computed(() => insightDisplay.value.layout)
const insightMaxStats = computed(() => insightDisplay.value.maxStats)
const isFeaturedSideInsight = computed(() => insightDisplay.value.featuredSide === true)

function measureFrame() {
  const el = containerRef.value
  if (!el) {
    return
  }
  const nextSize = {
    width: Math.round(el.clientWidth),
    height: Math.round(el.clientHeight),
  }
  if (nextSize.width === frameSize.value.width && nextSize.height === frameSize.value.height) {
    return
  }
  frameSize.value = nextSize
}

function scheduleRenderChart() {
  if (renderTimer) {
    window.clearTimeout(renderTimer)
  }
  renderTimer = window.setTimeout(() => {
    renderTimer = undefined
    nextTick(renderChart)
  }, 80)
}

watch(
  () => [props.viewInfo?.chart?.type, props.viewInfo?.chart?.sourceType],
  ([type, sourceType]) => {
    currentChartType.value = type ?? sourceType
  }
)

function onTypeChange(val: any) {
  chartType.value = val
  // eslint-disable-next-line vue/no-mutating-props
  props.viewInfo.chart.type = val
  nextTick(() => {
    //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
    chartRef.value?.destroyChart()
    //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
    chartRef.value?.renderChart()
  })
}

onMounted(() => {
  // eslint-disable-next-line vue/no-mutating-props
  props.viewInfo.chart['sourceType'] =
    props.viewInfo.chart['sourceType'] ?? props.viewInfo.chart.type
  nextTick(() => {
    measureFrame()
    if (containerRef.value) {
      resizeObserver = new ResizeObserver(() => {
        measureFrame()
        scheduleRenderChart()
      })
      resizeObserver.observe(containerRef.value)
    }
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  stopRefreshProgress()
  if (renderTimer) {
    window.clearTimeout(renderTimer)
  }
})

defineExpose({
  renderChart,
  enlargeView,
  refreshData,
  exportTableData,
})
</script>

<template>
  <div
    ref="containerRef"
    class="chart-base-container"
    :class="`insight-density-${insightDensity}`"
  >
    <div class="header-bar">
      <div class="title">
        {{ viewInfo.chart.title }}
      </div>
      <div v-if="showPosition === 'multiplexing'" class="buttons-bar">
        <div class="chart-select-container">
          <el-tooltip effect="dark" :content="t('chat.type')" placement="top">
            <ChartPopover
              v-if="chartTypeList.length > 0"
              :chart-type-list="chartTypeList"
              :chart-type="chartType"
              :title="t('chat.type')"
              @type-change="onTypeChange"
            ></ChartPopover>
          </el-tooltip>
          <el-tooltip effect="dark" :content="t('chat.chart_type.table')" placement="top">
            <el-button
              class="tool-btn"
              :class="{ 'chart-active': currentChartType === 'table' }"
              text
              @click="changeTable"
            >
              <el-icon size="16">
                <ICON_TABLE />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div class="divider" />
      </div>
    </div>
    <div class="chart-show-area" :class="`insight-layout-${effectiveInsightLayout}`">
      <div v-if="chartLoading" class="chart-loading-info">
        <el-progress
          type="circle"
          :percentage="chartLoadingProgress"
          :width="92"
          :stroke-width="7"
          :show-text="true"
        />
        <div class="chart-loading-text">{{ t('dashboard.chart_data_loading') }}</div>
      </div>
      <div v-else-if="viewInfo.status === 'failed'" class="error-info">
        {{ viewInfo.message }}
      </div>
      <ChartInsightHeader
        v-else-if="canShowInsightHeader && effectiveInsightLayout === 'top'"
        compact
        :density="insightDensity"
        :max-stats="insightMaxStats"
        :chart-type="chartType"
        :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
        :x="viewInfo.chart?.xAxis"
        :y="viewInfo.chart?.yAxis"
        :series="viewInfo.chart?.series"
        :data="viewInfo.data?.data"
        :sql="viewInfo.sql"
        :insight="viewInfo.chart?.insight"
      />
      <div
        v-if="!chartLoading && viewInfo.status !== 'failed' && viewInfo.id"
        class="chart-content-row"
        :class="{ 'side-layout': effectiveInsightLayout === 'side' }"
      >
        <ChartInsightHeader
          v-if="canShowInsightHeader && effectiveInsightLayout === 'side'"
          compact
          :density="insightDensity"
          layout="side"
          :max-stats="insightMaxStats"
          :chart-type="chartType"
          :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
          :x="viewInfo.chart?.xAxis"
          :y="viewInfo.chart?.yAxis"
          :series="viewInfo.chart?.series"
          :data="viewInfo.data?.data"
          :sql="viewInfo.sql"
          :insight="viewInfo.chart?.insight"
          :featured-side="isFeaturedSideInsight"
        />
        <ChartComponent
          :id="outerId || viewInfo.id"
          ref="chartRef"
          :type="chartType"
          :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
          :x="viewInfo.chart?.xAxis"
          :y="viewInfo.chart?.yAxis"
          :series="viewInfo.chart?.series"
          :data="viewInfo.data?.data"
          :multi-quota-name="viewInfo.chart?.multiQuotaName"
        />
      </div>
    </div>
    <el-dialog
      v-if="enlargeDialogVisible"
      v-model="enlargeDialogVisible"
      fullscreen
      :show-close="false"
      class="chart-fullscreen-dialog-view"
      header-class="chart-fullscreen-dialog-header-view"
      body-class="chart-fullscreen-dialog-body-view"
    >
      <div style="position: absolute; right: 15px; top: 15px; cursor: pointer">
        <el-tooltip effect="dark" :content="t('dashboard.exit_preview')" placement="top">
          <el-button
            class="tool-btn"
            style="width: 26px"
            text
            @click="() => (enlargeDialogVisible = false)"
          >
            <el-icon size="16">
              <icon_window_mini_outlined />
            </el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <SqViewDisplay :view-info="viewInfo" :outer-id="'enlarge-' + viewInfo.id" />
    </el-dialog>
  </div>
</template>

<style lang="less">
.chart-fullscreen-dialog-view {
  padding: 0;
}
.chart-fullscreen-dialog-header-view {
  display: none;
}
.chart-fullscreen-dialog-body-view {
  padding: 0;
  height: 100%;
}
</style>

<style scoped lang="less">
.chart-base-container {
  width: 100%;
  height: 100%;
  background: #ffffff;
  padding: 14px 16px !important;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  overflow: hidden;
  div::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
  }
  .header-bar {
    min-height: 34px;
    display: flex;
    margin-bottom: 10px;

    align-items: center;
    flex-direction: row;

    .tool-btn {
      width: 24px;
      height: 24px;

      font-size: 16px;
      font-weight: 400;
      line-height: 24px;
      border-radius: 6px;
      color: var(--workspace-text-secondary, rgba(100, 106, 115, 1));

      .tool-btn-inner {
        display: flex;
        flex-direction: row;
        align-items: center;
      }

      &:hover {
        background: var(--workspace-control-hover-bg, rgba(31, 35, 41, 0.1));
      }
      &:active {
        background: var(--workspace-control-hover-bg, rgba(31, 35, 41, 0.1));
      }
    }

    .chart-active {
      background: var(--ed-color-primary-1a, rgba(28, 186, 144, 0.1));
      color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      border-radius: 6px;

      :deep(.ed-select__wrapper) {
        background: transparent;
      }
      :deep(.ed-select__input) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }
      :deep(.ed-select__placeholder) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }
      :deep(.ed-select__caret) {
        color: var(--ed-color-primary, rgba(28, 186, 144, 1));
      }
    }

    .title {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      color: var(--workspace-text-primary, rgba(31, 35, 41, 1));
      font-weight: 600;
      font-size: 15px;
      line-height: 24px;
      letter-spacing: 0.01em;
    }

    .buttons-bar {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 16px;
      margin-right: 36px;
      .divider {
        width: 1px;
        height: 16px;
        border-left: 1px solid var(--workspace-border, rgba(31, 35, 41, 0.15));
      }
    }

    .chart-select-container {
      padding: 3px;
      display: flex;
      flex-direction: row;
      gap: 4px;
      border-radius: 6px;

      border: 1px solid var(--workspace-border, rgba(217, 220, 223, 1));

      .chart-select {
        min-width: 40px;
        width: 40px;
        height: 24px;

        :deep(.ed-select__wrapper) {
          padding: 4px;
          min-height: 24px;
          box-shadow: unset;
          border-radius: 6px;

          &:hover {
              background: var(--workspace-control-hover-bg, rgba(31, 35, 41, 0.1));
            }
            &:active {
              background: var(--workspace-control-hover-bg, rgba(31, 35, 41, 0.1));
            }
        }
        :deep(.ed-select__caret) {
          font-size: 12px !important;
        }
      }
    }
  }

  &.insight-density-mini,
  &.insight-density-basic {
    padding: 10px 12px !important;

    .header-bar {
      min-height: 28px;
      margin-bottom: 6px;

      .title {
        font-size: 14px;
        line-height: 22px;
      }
    }
  }

  &.insight-density-basic {
    padding: 8px 10px !important;

    .header-bar {
      min-height: 24px;
      margin-bottom: 4px;
    }
  }
}

.chart-show-area {
  width: 100%;
  height: calc(100% - 46px);
  display: flex;
  flex-direction: column;
  min-height: 0;

  :deep(.chart-container) {
    flex: 1 1 auto;
    min-height: 0;
  }

  .chart-content-row {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;

    &.side-layout {
      flex-direction: row;
      align-items: stretch;
    }
  }
}

.insight-density-mini .chart-show-area {
  height: calc(100% - 34px);
}

.insight-density-basic .chart-show-area {
  height: calc(100% - 28px);
}

.buttons-bar {
  display: flex;
  flex-direction: row;
  align-items: center;

  gap: 16px;

  .divider {
    width: 1px;
    height: 16px;
    border-left: 1px solid var(--workspace-border, rgba(31, 35, 41, 0.15));
  }
}

.chart-select-container {
  padding: 3px;
  display: flex;
  flex-direction: row;
  gap: 4px;
  border-radius: 6px;

  border: 1px solid rgba(217, 220, 223, 1);

  .chart-select {
    min-width: 40px;
    width: 40px;
    height: 24px;

      :deep(.ed-select__wrapper) {
      padding: 4px;
      min-height: 24px;
      box-shadow: unset;
      border-radius: 6px;

        &:hover {
          background: var(--workspace-control-hover-bg, rgba(31, 35, 41, 0.1));
        }
        &:active {
          background: var(--workspace-active-bg, rgba(31, 35, 41, 0.1));
        }
      }
    :deep(.ed-select__caret) {
      font-size: 12px !important;
    }
  }
}

.error-info {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  font-size: 12px;
  color: var(--workspace-text-secondary, var(--N600, #646a73));
}

.chart-loading-info {
  width: 100%;
  height: 100%;
  min-height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--workspace-text-primary, #1f2329);

  :deep(.ed-progress-circle__track),
  :deep(.el-progress-circle__track) {
    stroke: #eef1f5;
  }

  :deep(.ed-progress-circle__path),
  :deep(.el-progress-circle__path) {
    stroke: var(--ed-color-primary, #2f6bff);
  }

  :deep(.ed-progress__text),
  :deep(.el-progress__text) {
    min-width: 46px;
    color: var(--workspace-text-primary, #1f2329);
    font-size: 20px !important;
    font-weight: 700;
  }
}

.chart-loading-text {
  font-size: 13px;
  line-height: 20px;
  color: var(--workspace-text-secondary, #66758f);
}
</style>
