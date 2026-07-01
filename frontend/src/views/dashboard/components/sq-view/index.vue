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
  showLabel: {
    type: Boolean,
    required: false,
    default: false,
  },
})

import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChartPopover from '@/views/chat/chat-block/ChartPopover.vue'
import {
  buildInsightColumns,
  detectTrendAxisGranularity,
  resolveInsightDisplay,
} from '@/views/chat/component/chartInsight.ts'
import { axisValue } from '@/views/chat/component/BaseChart.ts'
import { toNullableNumber } from '@/views/chat/component/charts/utils.ts'
import ICON_TABLE from '@/assets/svg/chart/icon_form_outlined.svg'
import ICON_COLUMN from '@/assets/svg/chart/icon_dashboard_outlined.svg'
import ICON_BAR from '@/assets/svg/chart/icon_bar_outlined.svg'
import ICON_LINE from '@/assets/svg/chart/icon_chart-line.svg'
import ICON_PIE from '@/assets/svg/chart/icon_pie_outlined.svg'
import type { ChartAxis, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  defaultPivotAggregationForAxes,
  resolvePivotMetricAggregations,
  withResolvedMetricSemantics,
} from '@/views/dashboard/utils/metricSemantics.ts'
import { inferPivotDimensions, type PivotDimension } from '@/views/dashboard/utils/pivotDimensions.ts'
import { ArrowLeft, ArrowRight, Search } from '@element-plus/icons-vue'
const { t, locale } = useI18n()
const containerRef = ref<HTMLElement | null>(null)
const chartRef = ref(null)
const currentChartType = ref<ChartTypes | undefined>(undefined)
const frameSize = ref({ width: 0, height: 0 })
const refreshing = ref(false)
const blockingRefreshLoading = ref(false)
const chartRenderVersion = ref(0)
const pivotCalendarMonth = ref('')
const pivotCalendarDraftStart = ref('')
let resizeObserver: ResizeObserver | undefined
let renderTimer: number | undefined
let progressTimer: number | undefined
let pivotRefreshTimer: number | undefined
let refreshRequestSeq = 0
let blockingRefreshRequestSeq = 0

type PivotGranularity = 'day' | 'week' | 'month'
type PivotQuickRange = {
  value: string
  label: string
  days: number
  offset?: number
  range?: string
}
type PivotGroupValueSelectionMode = 'all' | 'custom'
type PivotGroupValueOption = {
  value: string
  label: string
  count: number
}
const dashboardTextFallbacks = {
  'zh-CN': {
    pivot_group_search: '请输入搜索',
    pivot_group_no_match: '无匹配分组',
    pivot_group_select_all: '全选',
    pivot_group_select_none: '全不选',
  },
  'zh-TW': {
    pivot_group_search: '請輸入搜尋',
    pivot_group_no_match: '無符合分組',
    pivot_group_select_all: '全選',
    pivot_group_select_none: '全不選',
  },
  en: {
    pivot_group_search: 'Search',
    pivot_group_no_match: 'No matching groups',
    pivot_group_select_all: 'Select all',
    pivot_group_select_none: 'Select none',
  },
  'ko-KR': {
    pivot_group_search: '검색어 입력',
    pivot_group_no_match: '일치하는 그룹 없음',
    pivot_group_select_all: '전체 선택',
    pivot_group_select_none: '전체 해제',
  },
} as const
type DashboardTextKey = keyof typeof dashboardTextFallbacks['zh-CN']
const DAY_MS = 24 * 60 * 60 * 1000

const renderChart = () => {
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.destroyChart()
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.renderChart()
}
const chartComponentKey = computed(
  () => `${props.outerId || props.viewInfo?.id || 'chart'}-${chartRenderVersion.value}`
)

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

function normalizePivotGroupValue(value: unknown) {
  if (value === undefined || value === null) {
    return ''
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? '' : value.toISOString()
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (_error) {
      return `${value}`
    }
  }
  return `${value}`.trim()
}

function dashboardText(key: DashboardTextKey) {
  const fullKey = `dashboard.${key}`
  const value = t(fullKey)
  if (value && value !== fullKey) {
    return value
  }
  const localeKey = String(locale.value || 'zh-CN') as keyof typeof dashboardTextFallbacks
  return (dashboardTextFallbacks[localeKey] || dashboardTextFallbacks['zh-CN'])[key]
}

function getResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

type RefreshDataOptions = {
  silent?: boolean
  forceRefresh?: boolean
  blocking?: boolean
}

function clampChartLoadingProgress(progress: unknown) {
  const numericProgress = Number(progress)
  if (!Number.isFinite(numericProgress)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(numericProgress)))
}

function setChartLoadingProgress(progress: number, allowDecrease = false) {
  if (!props.viewInfo) {
    return
  }
  const nextProgress = clampChartLoadingProgress(progress)
  const currentProgress = clampChartLoadingProgress(props.viewInfo.loadingProgress)
  props.viewInfo.loadingProgress = allowDecrease ? nextProgress : Math.max(currentProgress, nextProgress)
}

const pivotGranularityOptions = computed(() => [
  { value: 'day', label: t('dashboard.pivot_day') },
  { value: 'week', label: t('dashboard.pivot_week') },
  { value: 'month', label: t('dashboard.pivot_month') },
])
const pivotRangeOptions = computed(() => [
  { value: 'source', label: t('dashboard.pivot_source_time') },
  { value: '7d', label: t('dashboard.pivot_recent_7d') },
  { value: '14d', label: t('dashboard.pivot_recent_14d') },
  { value: '30d', label: t('dashboard.pivot_recent_30d') },
  { value: '90d', label: t('dashboard.pivot_recent_90d') },
  { value: 'all', label: t('dashboard.pivot_all_time') },
  { value: 'custom', label: t('dashboard.pivot_custom_range') },
])
const pivotQuickRangeOptions = computed<PivotQuickRange[]>(() => [
  { value: 'today', label: t('dashboard.pivot_today'), days: 1 },
  { value: '2d', label: t('dashboard.pivot_recent_2d'), days: 2 },
  { value: '3d', label: t('dashboard.pivot_recent_3d'), days: 3 },
  { value: '7d', label: t('dashboard.pivot_recent_7d'), days: 7, range: '7d' },
  { value: 'yesterday', label: t('dashboard.pivot_yesterday'), days: 1, offset: 1 },
])
const pivotCalendarWeekdays = computed(() => [
  t('dashboard.pivot_weekday_mo'),
  t('dashboard.pivot_weekday_tu'),
  t('dashboard.pivot_weekday_we'),
  t('dashboard.pivot_weekday_th'),
  t('dashboard.pivot_weekday_fr'),
  t('dashboard.pivot_weekday_sa'),
  t('dashboard.pivot_weekday_su'),
])
const pivotState = reactive({
  initializedFor: '',
  granularity: 'day',
  range: 'source',
  customStart: '',
  customEnd: '',
  groupEnabled: true,
  groupField: '',
})
const pivotGroupValueSearch = ref('')
const pivotGroupValueState = reactive<{
  key: string
  mode: PivotGroupValueSelectionMode
  selectedValues: string[]
}>({
  key: '',
  mode: 'all',
  selectedValues: [],
})
const rawChartData = computed(() =>
  Array.isArray(props.viewInfo?.data?.data) ? props.viewInfo.data.data : []
)

function normalizeAxisList(list: any): ChartAxis[] {
  return Array.isArray(list) ? list : []
}

function normalizeAxisField(axis: any) {
  return axisValue(axis)
}

function firstAxisValue(list: any) {
  const axis = normalizeAxisList(list).find((item) => normalizeAxisField(item))
  return axis ? normalizeAxisField(axis) : ''
}

function normalizedAxis(axis: any): ChartAxis | null {
  const value = normalizeAxisField(axis)
  if (!value) {
    return null
  }
  return { ...(axis || {}), value }
}

function axisForField(list: any, field: string): ChartAxis | undefined {
  if (!field) {
    return undefined
  }
  const axis = normalizeAxisList(list).find((item) => normalizeAxisField(item) === field)
  return normalizedAxis(axis) || undefined
}

const pivotTimeField = computed(() => props.viewInfo?.pivot?.time_field || firstAxisValue(props.viewInfo?.chart?.xAxis))
const chartMetricAxes = computed<ChartAxis[]>(() => {
  const used = new Set<string>()
  return normalizeAxisList(props.viewInfo?.chart?.yAxis)
    .map(normalizedAxis)
    .map((axis) => axis && withResolvedMetricSemantics(axis, props.viewInfo?.data?.data || []))
    .filter((axis): axis is ChartAxis => {
      if (!axis || used.has(axis.value)) {
        return false
      }
      used.add(axis.value)
      return true
    })
})
const pivotMetricFields = computed(() => {
  const fields = chartMetricAxes.value.map((axis) => axis.value)
  if (fields.length > 0) {
    return fields
  }
  const legacyField = props.viewInfo?.pivot?.metric_field || firstAxisValue(props.viewInfo?.chart?.yAxis)
  return legacyField ? [legacyField] : []
})
const pivotGroupField = computed(() => props.viewInfo?.pivot?.group_field || firstAxisValue(props.viewInfo?.chart?.series))
const pivotDimensions = computed<PivotDimension[]>(() =>
  inferPivotDimensions({
    fields: [
      ...(Array.isArray(props.viewInfo?.data?.source_fields) ? props.viewInfo.data.source_fields : []),
      ...(Array.isArray(props.viewInfo?.data?.fields) ? props.viewInfo.data.fields : []),
      ...(Array.isArray(props.viewInfo?.fields) ? props.viewInfo.fields : []),
    ],
    data: props.viewInfo?.data?.source_data || props.viewInfo?.data?.data || [],
    chart: props.viewInfo?.chart || {},
    timeField: pivotTimeField.value,
    metricFields: pivotMetricFields.value,
    configured: props.viewInfo?.pivot?.dimensions,
  })
)
const activePivotGroupField = computed(() => pivotState.groupField || pivotGroupField.value || pivotDimensions.value[0]?.field || '')
const activePivotGroupDimension = computed(() =>
  pivotDimensions.value.find((item) => item.field === activePivotGroupField.value) ||
  (activePivotGroupField.value ? { field: activePivotGroupField.value, label: activePivotGroupField.value } : null)
)
const pivotHasGroup = computed(() => Boolean(activePivotGroupField.value))
const pivotRangeEnabled = computed(() => props.viewInfo?.pivot?.range_enabled !== false)
const pivotTimeRangeActive = computed(() => pivotRangeEnabled.value && pivotState.range !== 'source')
const pivotClientFilterOnly = computed(() => props.viewInfo?.pivot?.client_filter_only === true)
const pivotEnabled = computed(() => {
  if (props.showPosition === 'multiplexing') {
    return false
  }
  return props.viewInfo?.pivot?.enabled === true && Boolean(pivotTimeField.value && pivotMetricFields.value.length)
})
const pivotSummaryText = computed(() => {
  if (!pivotEnabled.value) {
    return ''
  }
  const groupLabel =
    activePivotGroupDimension.value && pivotState.groupEnabled
      ? activePivotGroupDimension.value.label
      : t('dashboard.pivot_ungrouped')
  return `${pivotRangeLabel.value} / ${groupLabel}`
})
const pivotGranularityLabel = computed(
  () =>
    pivotGranularityOptions.value.find((item) => item.value === pivotState.granularity)?.label ||
    t('dashboard.pivot_day')
)
const pivotModeLabel = computed(() =>
  pivotTimeRangeActive.value ? t('dashboard.pivot_select_time') : pivotGranularityLabel.value
)
const currentPivotTimeAxis = computed<ChartAxis | undefined>(() =>
  axisForField(props.viewInfo?.chart?.xAxis, pivotTimeField.value) ||
  (pivotTimeField.value ? { name: pivotTimeField.value, value: pivotTimeField.value } : undefined)
)
const currentPivotGroupAxis = computed<ChartAxis | undefined>(() =>
  axisForField(props.viewInfo?.chart?.series, activePivotGroupField.value) ||
  (activePivotGroupDimension.value
    ? { name: activePivotGroupDimension.value.label, value: activePivotGroupDimension.value.field, type: 'series' }
    : undefined)
)
const renderXAxis = computed<ChartAxis[]>(() => {
  if (pivotEnabled.value) {
    return currentPivotTimeAxis.value ? [currentPivotTimeAxis.value] : []
  }
  return normalizeAxisList(props.viewInfo?.chart?.xAxis)
})
const renderYAxis = computed<ChartAxis[]>(() => {
  if (pivotEnabled.value) {
    return chartMetricAxes.value
  }
  return normalizeAxisList(props.viewInfo?.chart?.yAxis)
})
const renderSeries = computed<ChartAxis[]>(() => {
  if (pivotEnabled.value) {
    return pivotHasGroup.value && pivotState.groupEnabled && currentPivotGroupAxis.value
      ? [currentPivotGroupAxis.value]
      : []
  }
  return normalizeAxisList(props.viewInfo?.chart?.series)
})
const pivotGroupValueFilterEnabled = computed(
  () => pivotEnabled.value && pivotHasGroup.value && pivotState.groupEnabled && Boolean(activePivotGroupField.value)
)
function hasRenderableMetricValue(value: unknown) {
  return toNullableNumber(value) !== null
}

function hasRenderableMetricRow(row: Record<string, any>, metricFields: string[]) {
  if (metricFields.length === 0) {
    return true
  }
  return metricFields.some((field) => hasRenderableMetricValue(row?.[field]))
}

const renderableChartData = computed(() => {
  const rows = rawChartData.value
  if (!pivotEnabled.value) {
    return rows
  }
  const metricFields = renderYAxis.value.map((axis) => axis.value).filter(Boolean)
  if (metricFields.length === 0) {
    return rows
  }
  return rows.filter((row: Record<string, any>) => hasRenderableMetricRow(row, metricFields))
})
const configuredPivotGroupValues = computed(() =>
  unique(Array.isArray(props.viewInfo?.pivot?.group_values) ? props.viewInfo.pivot.group_values : [])
)
const pivotGroupValueOptions = computed<PivotGroupValueOption[]>(() => {
  if (!pivotGroupValueFilterEnabled.value) {
    return []
  }
  const configured = configuredPivotGroupValues.value
  const configuredSet = new Set(configured)
  const counts = new Map<string, number>()
  const field = activePivotGroupField.value
  renderableChartData.value.forEach((row: Record<string, any>) => {
    const value = normalizePivotGroupValue(row?.[field])
    if (!value || (configuredSet.size > 0 && !configuredSet.has(value))) {
      return
    }
    counts.set(value, (counts.get(value) || 0) + 1)
  })
  configured.forEach((value) => {
    if (value && !counts.has(value)) {
      counts.set(value, 0)
    }
  })
  const values = configured.length > 0 ? configured.map((value) => [value, counts.get(value) || 0] as [string, number]) : Array.from(counts.entries())
  return values
    .map(([value, count]) => ({
      value,
      label: value,
      count,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true, sensitivity: 'base' }))
})
const pivotGroupValueTotal = computed(() => pivotGroupValueOptions.value.length)
const selectedPivotGroupValueSet = computed(() => {
  if (pivotGroupValueState.mode === 'all') {
    return new Set(pivotGroupValueOptions.value.map((option) => option.value))
  }
  return new Set(pivotGroupValueState.selectedValues)
})
const pivotGroupValueSelectedCount = computed(() => {
  if (!pivotGroupValueFilterEnabled.value) {
    return 0
  }
  if (pivotGroupValueState.mode === 'all') {
    return pivotGroupValueTotal.value
  }
  const available = new Set(pivotGroupValueOptions.value.map((option) => option.value))
  return pivotGroupValueState.selectedValues.filter((value) => available.has(value)).length
})
const pivotGroupValueAllSelected = computed(
  () => pivotGroupValueTotal.value > 0 && pivotGroupValueSelectedCount.value === pivotGroupValueTotal.value
)
const pivotGroupValuePartiallySelected = computed(
  () => pivotGroupValueSelectedCount.value > 0 && pivotGroupValueSelectedCount.value < pivotGroupValueTotal.value
)
const pivotGroupValueLabel = computed(() =>
  `${t('dashboard.pivot_group')} (${pivotGroupValueSelectedCount.value}/${pivotGroupValueTotal.value})`
)
const filteredPivotGroupValueOptions = computed(() => {
  const keyword = pivotGroupValueSearch.value.trim().toLowerCase()
  if (!keyword) {
    return pivotGroupValueOptions.value
  }
  return pivotGroupValueOptions.value.filter((option) => option.label.toLowerCase().includes(keyword))
})
const displayData = computed(() => {
  const rows = renderableChartData.value
  if (!pivotGroupValueFilterEnabled.value) {
    return rows
  }
  if (configuredPivotGroupValues.value.length === 0 && pivotGroupValueState.mode === 'all') {
    return rows
  }
  const selected = selectedPivotGroupValueSet.value
  if (selected.size === 0) {
    return []
  }
  const field = activePivotGroupField.value
  return rows.filter((row: Record<string, any>) =>
    selected.has(normalizePivotGroupValue(row?.[field]))
  )
})

function reportAxisFields(axes: ChartAxis[]) {
  return axes.map((axis) => axis?.name || axis?.value).filter(Boolean).map((field) => `${field}`)
}

function getReportContextSnapshot() {
  const rows = Array.isArray(displayData.value) ? displayData.value : []
  const availableGroupValues = new Set(pivotGroupValueOptions.value.map((option) => option.value))
  const selectedGroupValues = pivotGroupValueFilterEnabled.value
    ? Array.from(selectedPivotGroupValueSet.value).filter((value) => availableGroupValues.has(value))
    : []

  return {
    fields: unique([
      ...(Array.isArray(props.viewInfo?.data?.fields) ? props.viewInfo.data.fields : []),
      ...(Array.isArray(props.viewInfo?.fields) ? props.viewInfo.fields : []),
      ...reportAxisFields(renderXAxis.value),
      ...reportAxisFields(renderYAxis.value),
      ...reportAxisFields(renderSeries.value),
      ...rows.flatMap((row: Record<string, any>) => Object.keys(row || {})),
    ]),
    data: rows,
    totalRows: rows.length,
    sourceRows: rawChartData.value.length,
    axes: {
      x: renderXAxis.value,
      y: renderYAxis.value,
      series: renderSeries.value,
    },
    pivot: pivotEnabled.value
      ? {
          enabled: true,
          time_field: pivotTimeField.value,
          granularity: pivotState.granularity,
          range: pivotState.range,
          custom_start: pivotState.customStart,
          custom_end: pivotState.customEnd,
          group_field: activePivotGroupField.value,
          group_enabled: pivotState.groupEnabled,
          selected_group_values: selectedGroupValues,
          selected_group_count: pivotGroupValueFilterEnabled.value
            ? pivotGroupValueSelectedCount.value
            : 0,
          total_group_count: pivotGroupValueFilterEnabled.value ? pivotGroupValueTotal.value : 0,
        }
      : {
          enabled: false,
        },
  }
}
const renderMultiQuotaName = computed(() => props.viewInfo.chart?.multiQuotaName)
const renderForecast = computed(() => props.viewInfo.chart?.forecast)
const pivotRangeLabel = computed(() => {
  if (pivotState.range === 'custom' && (pivotState.customStart || pivotState.customEnd)) {
    if (pivotState.customStart && pivotState.customEnd) {
      return `${pivotState.customStart} ~ ${pivotState.customEnd}`
    }
    return pivotState.customStart || pivotState.customEnd
  }
  return (
    pivotRangeOptions.value.find((item) => item.value === pivotState.range)?.label ||
    t('dashboard.pivot_source_time')
  )
})
function padDatePart(value: number) {
  return String(value).padStart(2, '0')
}

function formatDateKey(date: Date) {
  return `${date.getUTCFullYear()}-${padDatePart(date.getUTCMonth() + 1)}-${padDatePart(
    date.getUTCDate()
  )}`
}

function parseDateKey(value: string) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) {
    return null
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null
  }
  return date
}

function shiftDateKey(value: string, days: number) {
  const date = parseDateKey(value)
  if (!date) {
    return value
  }
  return formatDateKey(new Date(date.getTime() + days * DAY_MS))
}

function monthKeyFromDateKey(value: string) {
  return value.slice(0, 7)
}

function compareDateKey(a: string, b: string) {
  return a.localeCompare(b)
}

function normalizeRange(start: string, end: string) {
  if (!start || !end) {
    return { start, end }
  }
  return compareDateKey(start, end) <= 0 ? { start, end } : { start: end, end: start }
}

const pivotDataDateBounds = computed(() => {
  const rows = Array.isArray(props.viewInfo?.data?.data) ? props.viewInfo.data.data : []
  const field = pivotTimeField.value
  const dates = rows
    .map((row: Record<string, any>) => parseDateKey(String(row?.[field] || '').slice(0, 10)))
    .filter((date: Date | null): date is Date => Boolean(date))
    .map(formatDateKey)
    .sort()
  return {
    min: dates[0] || '',
    max: dates[dates.length - 1] || '',
  }
})

const pivotCalendarAnchorDate = computed(() => {
  return (
    pivotState.customEnd ||
    pivotState.customStart ||
    pivotDataDateBounds.value.max ||
    formatDateKey(new Date())
  )
})

const pivotCalendarMonthKey = computed(() => {
  return pivotCalendarMonth.value || monthKeyFromDateKey(pivotCalendarAnchorDate.value)
})

const pivotCalendarTitle = computed(() => pivotCalendarMonthKey.value)

const pivotActiveRange = computed(() => {
  if (pivotState.range === 'custom') {
    return normalizeRange(pivotState.customStart, pivotState.customEnd || pivotState.customStart)
  }
  if (pivotState.range === 'all' && pivotDataDateBounds.value.min && pivotDataDateBounds.value.max) {
    return { start: pivotDataDateBounds.value.min, end: pivotDataDateBounds.value.max }
  }
  const days = pivotState.range === '7d' || pivotState.range === '14d' || pivotState.range === '30d' || pivotState.range === '90d'
    ? Number(pivotState.range.replace('d', ''))
    : 0
  if (days && pivotDataDateBounds.value.max) {
    return {
      start: shiftDateKey(pivotDataDateBounds.value.max, -(days - 1)),
      end: pivotDataDateBounds.value.max,
    }
  }
  return { start: '', end: '' }
})

const pivotCalendarDays = computed(() => {
  const [yearText, monthText] = pivotCalendarMonthKey.value.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const firstDay = new Date(Date.UTC(year, month - 1, 1))
  const startOffset = (firstDay.getUTCDay() + 6) % 7
  const startTime = firstDay.getTime() - startOffset * DAY_MS
  const activeStart = pivotActiveRange.value.start
  const activeEnd = pivotActiveRange.value.end
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(startTime + index * DAY_MS)
    const value = formatDateKey(date)
    const inActiveRange =
      activeStart && activeEnd && compareDateKey(value, activeStart) >= 0 && compareDateKey(value, activeEnd) <= 0
    const isDraft = pivotCalendarDraftStart.value === value
    return {
      value,
      label: String(date.getUTCDate()),
      inMonth: date.getUTCMonth() === month - 1,
      isStart: Boolean(activeStart && value === activeStart),
      isEnd: Boolean(activeEnd && value === activeEnd),
      inRange: Boolean(inActiveRange),
      isDraft,
    }
  })
})

function applyPivotCustomRange(start: string, end: string) {
  const range = normalizeRange(start, end)
  pivotCalendarDraftStart.value = ''
  pivotState.granularity = 'day'
  pivotState.range = 'custom'
  pivotState.customStart = range.start
  pivotState.customEnd = range.end
  pivotCalendarMonth.value = monthKeyFromDateKey(range.end || range.start || pivotCalendarAnchorDate.value)
  schedulePivotRefresh()
}

function setPivotQuickRange(option: PivotQuickRange) {
  if (option.range) {
    pivotCalendarDraftStart.value = ''
    setPivotRange(option.range)
    return
  }
  const anchor = pivotDataDateBounds.value.max || formatDateKey(new Date())
  const end = shiftDateKey(anchor, -(option.offset || 0))
  const start = shiftDateKey(end, -(option.days - 1))
  applyPivotCustomRange(start, end)
}

function isPivotQuickRangeActive(option: PivotQuickRange) {
  if (option.range) {
    return pivotState.range === option.range
  }
  const anchor = pivotDataDateBounds.value.max || formatDateKey(new Date())
  const end = shiftDateKey(anchor, -(option.offset || 0))
  const start = shiftDateKey(end, -(option.days - 1))
  return pivotState.range === 'custom' && pivotState.customStart === start && pivotState.customEnd === end
}

function selectPivotCalendarDate(value: string) {
  if (!pivotCalendarDraftStart.value || (pivotState.range === 'custom' && pivotState.customStart && pivotState.customEnd)) {
    pivotCalendarDraftStart.value = value
    pivotState.granularity = 'day'
    pivotState.range = 'custom'
    pivotState.customStart = value
    pivotState.customEnd = ''
    return
  }
  applyPivotCustomRange(pivotCalendarDraftStart.value, value)
}

function shiftPivotCalendarMonth(delta: number) {
  const [yearText, monthText] = pivotCalendarMonthKey.value.split('-')
  const date = new Date(Date.UTC(Number(yearText), Number(monthText) - 1 + delta, 1))
  pivotCalendarMonth.value = `${date.getUTCFullYear()}-${padDatePart(date.getUTCMonth() + 1)}`
}

function normalizePivotGranularity(value: any, fallback: PivotGranularity = 'day'): PivotGranularity {
  return value === 'week' || value === 'month' || value === 'day' ? value : fallback
}

function detectedPivotGranularity(): PivotGranularity {
  const detected = detectTrendAxisGranularity(props.viewInfo?.data?.data, pivotTimeField.value)
  return detected === 'week' || detected === 'month' ? detected : 'day'
}

function initialPivotGranularity(pivot: any): PivotGranularity {
  if (pivot?.range && pivot.range !== 'source') {
    return 'day'
  }
  const configured = normalizePivotGranularity(pivot?.granularity, 'day')
  const detected = detectedPivotGranularity()
  if ((!pivot?.granularity || (configured === 'day' && detected !== 'day')) && pivot?.range !== 'custom') {
    return detected
  }
  return configured
}

function defaultPivotAggregation() {
  return defaultPivotAggregationForAxes(chartMetricAxes.value, props.viewInfo?.data?.data || [])
}

function resetPivotGroupValueSelection(mode: PivotGroupValueSelectionMode = 'all') {
  pivotGroupValueState.mode = mode
  pivotGroupValueState.selectedValues = mode === 'all'
    ? pivotGroupValueOptions.value.map((option) => option.value)
    : []
}

function syncPivotGroupValueSelection() {
  const key = `${props.viewInfo?.id || ''}:${activePivotGroupField.value}`
  const optionValues = pivotGroupValueOptions.value.map((option) => option.value)
  if (!pivotGroupValueFilterEnabled.value || optionValues.length === 0) {
    pivotGroupValueState.key = key
    pivotGroupValueState.mode = 'all'
    pivotGroupValueState.selectedValues = []
    pivotGroupValueSearch.value = ''
    return
  }
  if (pivotGroupValueState.key !== key) {
    pivotGroupValueState.key = key
    pivotGroupValueState.mode = 'all'
    pivotGroupValueState.selectedValues = optionValues
    pivotGroupValueSearch.value = ''
    return
  }
  if (pivotGroupValueState.mode === 'all') {
    pivotGroupValueState.selectedValues = optionValues
    return
  }
  const available = new Set(optionValues)
  pivotGroupValueState.selectedValues = pivotGroupValueState.selectedValues.filter((value) => available.has(value))
}

function isPivotGroupValueSelected(value: string) {
  return selectedPivotGroupValueSet.value.has(value)
}

function setPivotGroupValueChecked(value: string, checked: boolean) {
  const selected = new Set(
    pivotGroupValueState.mode === 'all'
      ? pivotGroupValueOptions.value.map((option) => option.value)
      : pivotGroupValueState.selectedValues
  )
  if (checked) {
    selected.add(value)
  } else {
    selected.delete(value)
  }
  pivotGroupValueState.mode =
    selected.size === pivotGroupValueTotal.value && pivotGroupValueTotal.value > 0 ? 'all' : 'custom'
  pivotGroupValueState.selectedValues =
    pivotGroupValueState.mode === 'all' ? pivotGroupValueOptions.value.map((option) => option.value) : Array.from(selected)
  chartRenderVersion.value += 1
}

function togglePivotGroupValue(value: string, event: Event) {
  setPivotGroupValueChecked(value, Boolean((event.target as HTMLInputElement | null)?.checked))
}

function toggleAllPivotGroupValues(event: Event) {
  if (Boolean((event.target as HTMLInputElement | null)?.checked)) {
    selectAllPivotGroupValues()
  } else {
    clearPivotGroupValues()
  }
}

function selectAllPivotGroupValues() {
  resetPivotGroupValueSelection('all')
  chartRenderVersion.value += 1
}

function clearPivotGroupValues() {
  resetPivotGroupValueSelection('custom')
  chartRenderVersion.value += 1
}

function getPivotPayload() {
  if (!pivotEnabled.value || pivotClientFilterOnly.value) {
    return undefined
  }
  return {
    enabled: true,
    time_field: pivotTimeField.value,
    metric_fields: pivotMetricFields.value,
    metric_aggregations: resolvePivotMetricAggregations(chartMetricAxes.value, props.viewInfo?.data?.data || []),
    metric_field: pivotMetricFields.value[0] || '',
    group_field: activePivotGroupField.value,
    group_enabled: pivotHasGroup.value ? pivotState.groupEnabled : false,
    dimensions: pivotDimensions.value,
    range_enabled: pivotRangeEnabled.value,
    granularity: pivotState.granularity,
    range: pivotRangeEnabled.value ? pivotState.range : 'source',
    custom_start: pivotRangeEnabled.value ? pivotState.customStart : '',
    custom_end: pivotRangeEnabled.value ? pivotState.customEnd : '',
    aggregation: defaultPivotAggregation(),
  }
}

function hasSourcePivotData() {
  const dataObj = props.viewInfo?.data || {}
  return (
    (Array.isArray(dataObj.source_fields) && dataObj.source_fields.length > 0) ||
    (Array.isArray(dataObj.source_data) && dataObj.source_data.length > 0)
  )
}

function syncPivotStateFromView(force = false) {
  const viewId = `${props.viewInfo?.id || ''}:${props.viewInfo?.sql || ''}`
  if (!force && pivotState.initializedFor === viewId) {
    return
  }
  const pivot = props.viewInfo?.pivot || {}
  pivotState.initializedFor = viewId
  pivotState.granularity = initialPivotGranularity(pivot)
  pivotState.range = pivot.range || 'source'
  pivotState.customStart = pivot.custom_start || ''
  pivotState.customEnd = pivot.custom_end || ''
  pivotState.groupField = pivot.group_field || pivotDimensions.value[0]?.field || pivotGroupField.value || ''
  pivotState.groupEnabled =
    typeof pivot.group_enabled === 'boolean' ? pivot.group_enabled : Boolean(pivotState.groupField)
  if (pivotEnabled.value) {
    const pivotPayload = getPivotPayload()
    props.viewInfo.pivot = {
      ...pivot,
      ...(pivotPayload || {}),
    }
  }
}

function schedulePivotRefresh() {
  if (!pivotEnabled.value) {
    return
  }
  if (pivotState.range === 'custom' && !pivotState.customStart && !pivotState.customEnd) {
    return
  }
  if (props.viewInfo?.pivot) {
    const pivotPayload = getPivotPayload()
    props.viewInfo.pivot = {
      ...props.viewInfo.pivot,
      ...(pivotPayload || {}),
    }
  }
  if (pivotRefreshTimer) {
    window.clearTimeout(pivotRefreshTimer)
  }
  if (pivotClientFilterOnly.value) {
    chartRenderVersion.value += 1
    scheduleRenderChart()
    return
  }
  pivotRefreshTimer = window.setTimeout(() => {
    pivotRefreshTimer = undefined
    void refreshData({ silent: true, forceRefresh: true, blocking: true })
  }, 120)
}

function hasChartResult(viewInfo: any) {
  const rows = viewInfo?.data?.data
  return Array.isArray(rows) && rows.length > 0
}

function hasChartShape(viewInfo: any) {
  return (
    hasChartResult(viewInfo) ||
    (Array.isArray(viewInfo?.data?.fields) && viewInfo.data.fields.length > 0) ||
    (Array.isArray(viewInfo?.fields) && viewInfo.fields.length > 0)
  )
}

function isExternalSnapshotChart(viewInfo: any) {
  return viewInfo?.externalSnapshot === true || viewInfo?.dataSourceType === 'external_mcp'
}

function markChartSnapshotRefreshed(viewInfo: any, refreshedAt = Date.now()) {
  if (!viewInfo || typeof viewInfo !== 'object') {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.snapshotRefreshedAt = refreshedAt
  viewInfo.data.snapshotRefreshedAt = refreshedAt
}

function resultRefreshedAt(result: any) {
  const timestamp = Number(result?.refreshed_at || result?.cache_refreshed_at || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : Date.now()
}

function normalizeLoadedChartState() {
  if (props.viewInfo?.dataState !== 'loading' && props.viewInfo?.status !== 'loading') {
    return false
  }
  if (!hasChartResult(props.viewInfo)) {
    return false
  }
  if (props.viewInfo.status === 'loading') {
    props.viewInfo.status = 'success'
  }
  props.viewInfo.dataState = props.viewInfo.status === 'failed' ? 'failed' : 'ready'
  props.viewInfo.loadingProgress = 100
  return true
}

function isDashboardCacheMiss(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_cache_miss'
}

function isDashboardQueryBusy(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_query_busy'
}

function isPermissionDeniedResult(result: any) {
  return result?.status === 'failed' && result?.error_type === 'permission_denied'
}

async function previewChartSqlWithCacheFallback(payload: any, forceRefresh = false) {
  if (forceRefresh) {
    return dashboardApi.preview_sql({
      ...payload,
      force_refresh: true,
    })
  }
  const cachedResult = await dashboardApi.preview_sql({
    ...payload,
    cache_only: true,
  })
  if (!isDashboardCacheMiss(cachedResult)) {
    return cachedResult
  }
  return dashboardApi.preview_sql(payload)
}

async function refreshData(options: RefreshDataOptions = {}) {
  const silent = options.silent === true
  const forceRefresh = options.forceRefresh !== false
  const blocking = options.blocking === true || !silent
  if (isExternalSnapshotChart(props.viewInfo)) {
    if (!props.viewInfo.data || typeof props.viewInfo.data !== 'object') {
      props.viewInfo.data = {}
    }
    props.viewInfo.data.data = Array.isArray(props.viewInfo.data.data) ? props.viewInfo.data.data : []
    props.viewInfo.data.fields = Array.isArray(props.viewInfo.data.fields) ? props.viewInfo.data.fields : []
    props.viewInfo.fields = Array.isArray(props.viewInfo.fields) ? props.viewInfo.fields : props.viewInfo.data.fields
    props.viewInfo.status = 'success'
    props.viewInfo.message = ''
    props.viewInfo.dataState = 'ready'
    props.viewInfo.loadingProgress = 100
    props.viewInfo.refreshState = ''
    scheduleRenderChart()
    return
  }
  if (!props.viewInfo?.datasource) {
    if (!silent) {
      ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    }
    return
  }
  if (!props.viewInfo?.sql?.trim()) {
    if (!silent) {
      ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    }
    return
  }
  refreshing.value = true
  if (!props.viewInfo.data || typeof props.viewInfo.data !== 'object') {
    props.viewInfo.data = {}
  }
  const previousData = Array.isArray(props.viewInfo.data.data) ? [...props.viewInfo.data.data] : []
  const previousDataFields = Array.isArray(props.viewInfo.data.fields)
    ? [...props.viewInfo.data.fields]
    : []
  const previousFields = Array.isArray(props.viewInfo.fields) ? [...props.viewInfo.fields] : []
  const hasPreviousRows = previousData.length > 0
  props.viewInfo.dataState = 'loading'
  props.viewInfo.refreshState = forceRefresh ? 'loading' : 'waiting'
  setChartLoadingProgress(0, !silent)
  startRefreshProgress()
  const requestSeq = ++refreshRequestSeq
  if (blocking) {
    blockingRefreshLoading.value = true
    blockingRefreshRequestSeq = requestSeq
  }
  const pivotPayload = getPivotPayload()
  try {
    const result = await previewChartSqlWithCacheFallback({
      datasource: props.viewInfo.datasource,
      sql: props.viewInfo.sql.trim(),
      pivot: pivotPayload,
    }, forceRefresh)
    if (requestSeq !== refreshRequestSeq) {
      return
    }
    const fields = getResultFields(result)
    const data = Array.isArray(result?.data) ? result.data : []
    if (!props.viewInfo.data || typeof props.viewInfo.data !== 'object') {
      props.viewInfo.data = {}
    }
    if (pivotPayload && !hasSourcePivotData()) {
      props.viewInfo.data.source_fields = Array.isArray(props.viewInfo.data.fields)
        ? [...props.viewInfo.data.fields]
        : [...fields]
      props.viewInfo.data.source_data = Array.isArray(props.viewInfo.data.data)
        ? [...props.viewInfo.data.data]
        : [...data]
    }
    props.viewInfo.data.fields = fields
    props.viewInfo.data.data = data
    props.viewInfo.fields = fields
    const hasPreviousShape =
      hasPreviousRows || previousDataFields.length > 0 || previousFields.length > 0 || hasChartShape(props.viewInfo)
    props.viewInfo.status = result?.status || 'success'
    props.viewInfo.message = result?.message || ''
    if (props.viewInfo.status === 'failed') {
      const queryBusyWithSnapshot = isDashboardQueryBusy(result) && hasPreviousShape
      if (!isPermissionDeniedResult(result) && (hasPreviousRows || queryBusyWithSnapshot)) {
        props.viewInfo.data.fields = previousDataFields
        props.viewInfo.data.data = previousData
        props.viewInfo.fields = previousFields
        props.viewInfo.status = 'success'
        props.viewInfo.message = ''
        props.viewInfo.dataState = 'ready'
        props.viewInfo.refreshState = isDashboardQueryBusy(result) ? 'queued' : ''
      } else {
        props.viewInfo.dataState = 'failed'
        props.viewInfo.refreshState = ''
      }
      if (!silent && !queryBusyWithSnapshot) {
        ElMessage.error(props.viewInfo.message || t('dashboard.chart_refresh_failed'))
      }
    } else {
      props.viewInfo.dataState = 'ready'
      props.viewInfo.refreshState = ''
      markChartSnapshotRefreshed(props.viewInfo, resultRefreshedAt(result))
      if (!silent) {
        ElMessage.success(t('dashboard.chart_refresh_success'))
      }
    }
    props.viewInfo.loadingProgress = 100
    chartRenderVersion.value += 1
    await nextTick()
  } catch (error: any) {
    if (requestSeq !== refreshRequestSeq) {
      return
    }
    props.viewInfo.message = error?.message || t('dashboard.chart_refresh_failed')
    if (hasPreviousRows) {
      props.viewInfo.data.fields = previousDataFields
      props.viewInfo.data.data = previousData
      props.viewInfo.fields = previousFields
      props.viewInfo.status = 'success'
      props.viewInfo.dataState = 'ready'
      props.viewInfo.refreshState = ''
    } else {
      props.viewInfo.status = 'failed'
      props.viewInfo.dataState = 'failed'
      props.viewInfo.refreshState = ''
    }
    props.viewInfo.loadingProgress = 100
    if (!silent) {
      ElMessage.error(error?.message || t('dashboard.chart_refresh_failed'))
    }
  } finally {
    if (requestSeq === refreshRequestSeq) {
      stopRefreshProgress()
      refreshing.value = false
    }
    if (requestSeq === blockingRefreshRequestSeq) {
      blockingRefreshLoading.value = false
      blockingRefreshRequestSeq = 0
    }
  }
}

function setPivotGranularity(value: string) {
  pivotState.granularity = normalizePivotGranularity(value)
  pivotCalendarDraftStart.value = ''
  pivotState.range = 'source'
  pivotState.customStart = ''
  pivotState.customEnd = ''
  schedulePivotRefresh()
}

function setPivotRange(value: string) {
  pivotState.granularity = 'day'
  pivotState.range = value
  if (value !== 'custom') {
    pivotState.customStart = ''
    pivotState.customEnd = ''
  }
  schedulePivotRefresh()
}

function startRefreshProgress() {
  stopRefreshProgress()
  progressTimer = window.setInterval(() => {
    if (!refreshing.value) {
      stopRefreshProgress()
      return
    }
    const current = clampChartLoadingProgress(props.viewInfo?.loadingProgress)
    setChartLoadingProgress(Math.min(95, current + Math.max(1, Math.round((96 - current) * 0.12))))
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
  const rows = displayData.value
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
  const rows = displayData.value
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
  return type !== 'table' && type !== 'metric' && displayData.value.length > 0
})
const insightColumns = computed(() =>
  buildInsightColumns(displayData.value, [
    ...renderXAxis.value,
    ...renderYAxis.value,
    ...renderSeries.value,
    ...(props.viewInfo.chart?.columns || []),
  ])
)
const insightDisplay = computed(() =>
  resolveInsightDisplay({
    chartType: chartType.value,
    data: displayData.value,
    x: renderXAxis.value,
    y: renderYAxis.value,
    series: renderSeries.value,
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
const hasRenderedChartData = computed(() => {
  return displayData.value.length > 0
})
const showFullChartLoading = computed(
  () => chartLoading.value && (blockingRefreshLoading.value || !hasRenderedChartData.value)
)
const chartLoadingText = computed(() =>
  props.viewInfo?.refreshState === 'waiting'
    ? t('dashboard.chart_data_waiting')
    : t('dashboard.chart_data_loading')
)
const showEmptyChartState = computed(() => {
  return (
    !chartLoading.value &&
    props.viewInfo?.status !== 'failed' &&
    props.viewInfo?.id &&
    !hasRenderedChartData.value
  )
})
const showChartContent = computed(() => {
  return (
    !showFullChartLoading.value &&
    !showEmptyChartState.value &&
    props.viewInfo?.status !== 'failed' &&
    props.viewInfo?.id
  )
})
const insightDensity = computed(() => insightDisplay.value.density)
const compactInsightHeader = computed(() => insightDensity.value !== 'regular')
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

async function recoverStaleLoadingState() {
  if (refreshing.value) {
    return
  }
  if (props.viewInfo?.dataState !== 'loading' && props.viewInfo?.status !== 'loading') {
    return
  }
  if (normalizeLoadedChartState()) {
    scheduleRenderChart()
    return
  }
  if (props.showPosition === 'canvas' && props.viewInfo?.datasource && props.viewInfo?.sql?.trim()) {
    await refreshData({ silent: true, forceRefresh: false })
  }
}

watch(
  () => [props.viewInfo?.chart?.type, props.viewInfo?.chart?.sourceType],
  ([type, sourceType]) => {
    currentChartType.value = type ?? sourceType
  }
)

watch(
  () => [
    props.viewInfo?.id,
    props.viewInfo?.status,
    props.viewInfo?.dataState,
    props.viewInfo?.loadingProgress,
    props.viewInfo?.datasource,
    props.viewInfo?.sql,
    props.viewInfo?.data?.data?.length,
    props.viewInfo?.data?.fields?.length,
    props.viewInfo?.fields?.length,
    props.viewInfo?.pivot,
    activePivotGroupField.value,
    pivotGroupValueTotal.value,
  ],
  () => {
    syncPivotStateFromView()
    syncPivotGroupValueSelection()
    void recoverStaleLoadingState()
  },
  { immediate: true }
)

watch(
  () => [
    pivotGroupValueState.mode,
    pivotGroupValueState.selectedValues.join('\u0001'),
    displayData.value.length,
  ],
  () => {
    scheduleRenderChart()
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
  if (pivotRefreshTimer) {
    window.clearTimeout(pivotRefreshTimer)
  }
})

defineExpose({
  renderChart,
  enlargeView,
  refreshData,
  exportTableData,
  getReportContextSnapshot,
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
    <div v-if="pivotEnabled" class="pivot-toolbar">
      <el-popover
        trigger="click"
        placement="bottom-start"
        width="148"
        popper-class="dashboard-pivot-popper"
      >
        <template #reference>
          <button class="pivot-chip pivot-link" type="button">{{ pivotModeLabel }}</button>
        </template>
        <div class="pivot-time-panel">
          <div class="pivot-menu">
            <button
              v-for="option in pivotGranularityOptions"
              :key="option.value"
              type="button"
              class="pivot-menu-item"
              :class="{ active: !pivotTimeRangeActive && pivotState.granularity === option.value }"
              @click="setPivotGranularity(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
          <el-popover
            v-if="pivotRangeEnabled"
            trigger="click"
            placement="right-start"
            width="326"
            popper-class="dashboard-pivot-popper dashboard-pivot-calendar-popper"
          >
            <template #reference>
              <button
                type="button"
                class="pivot-menu-item with-arrow"
                :class="{ active: pivotTimeRangeActive }"
              >
                <span>{{ t('dashboard.pivot_select_time') }}</span>
                <el-icon size="14" class="pivot-menu-arrow">
                  <ArrowRight />
                </el-icon>
              </button>
            </template>
            <div class="pivot-time-panel">
              <div class="pivot-quick-row">
                <button
                  v-for="option in pivotQuickRangeOptions"
                  :key="option.value"
                  type="button"
                  class="pivot-quick-chip"
                  :class="{ active: isPivotQuickRangeActive(option) }"
                  @click="setPivotQuickRange(option)"
                >
                  {{ option.label }}
                </button>
              </div>
              <div class="pivot-calendar-head">
                <button class="pivot-calendar-nav" type="button" @click="shiftPivotCalendarMonth(-1)">
                  <el-icon size="16">
                    <ArrowLeft />
                  </el-icon>
                </button>
                <span class="pivot-calendar-title">{{ pivotCalendarTitle }}</span>
                <button class="pivot-calendar-nav" type="button" @click="shiftPivotCalendarMonth(1)">
                  <el-icon size="16">
                    <ArrowRight />
                  </el-icon>
                </button>
              </div>
              <div class="pivot-calendar-grid weekdays">
                <span v-for="weekday in pivotCalendarWeekdays" :key="weekday">{{ weekday }}</span>
              </div>
              <div class="pivot-calendar-grid days">
                <button
                  v-for="day in pivotCalendarDays"
                  :key="day.value"
                  type="button"
                  class="pivot-calendar-day"
                  :class="{
                    muted: !day.inMonth,
                    'in-range': day.inRange,
                    endpoint: day.isStart || day.isEnd || day.isDraft,
                  }"
                  @click="selectPivotCalendarDate(day.value)"
                >
                  {{ day.label }}
                </button>
              </div>
              <div class="pivot-calendar-foot">
                <span>{{ t('dashboard.pivot_calendar_hint') }}</span>
                <button class="pivot-clear-btn" type="button" @click="setPivotRange('source')">
                  {{ t('dashboard.pivot_clear_time') }}
                </button>
              </div>
            </div>
          </el-popover>
        </div>
      </el-popover>
      <el-popover
        v-if="pivotHasGroup"
        trigger="click"
        placement="bottom-start"
        width="206"
        popper-class="dashboard-pivot-popper"
      >
        <template #reference>
          <button
            type="button"
            class="pivot-chip pivot-group-chip"
            :class="{ active: pivotState.groupEnabled }"
          >
            {{ pivotState.groupEnabled ? pivotGroupValueLabel : t('dashboard.pivot_ungrouped') }}
          </button>
        </template>
        <div class="pivot-group-value-panel">
          <el-input
            v-model="pivotGroupValueSearch"
            class="pivot-group-search"
            :placeholder="dashboardText('pivot_group_search')"
            size="small"
            clearable
          >
            <template #prefix>
              <el-icon size="14">
                <Search />
              </el-icon>
            </template>
          </el-input>
          <div class="pivot-group-value-toolbar">
            <label class="pivot-group-value-item pivot-group-value-all">
              <input
                type="checkbox"
                :checked="pivotGroupValueAllSelected"
                :indeterminate="pivotGroupValuePartiallySelected"
                @change="toggleAllPivotGroupValues"
              />
              <span class="pivot-group-value-label">
                {{ dashboardText('pivot_group_select_all') }}
              </span>
            </label>
            <button class="pivot-clear-btn" type="button" @click="clearPivotGroupValues">
              {{ dashboardText('pivot_group_select_none') }}
            </button>
          </div>
          <div class="pivot-group-value-list">
            <label
              v-for="option in filteredPivotGroupValueOptions"
              :key="option.value"
              class="pivot-group-value-item"
            >
              <input
                type="checkbox"
                :checked="isPivotGroupValueSelected(option.value)"
                @change="togglePivotGroupValue(option.value, $event)"
              />
              <span class="pivot-group-value-label">{{ option.label }}</span>
            </label>
            <div v-if="filteredPivotGroupValueOptions.length === 0" class="pivot-group-value-empty">
              {{ dashboardText('pivot_group_no_match') }}
            </div>
          </div>
        </div>
      </el-popover>
      <span class="pivot-summary">{{ pivotSummaryText }}</span>
    </div>
    <div class="chart-show-area" :class="`insight-layout-${effectiveInsightLayout}`">
      <div v-if="showFullChartLoading" class="chart-loading-info">
        <div class="chart-loading-ring" aria-hidden="true"></div>
        <div class="chart-loading-text">{{ chartLoadingText }}</div>
      </div>
      <div v-else-if="viewInfo.status === 'failed'" class="error-info">
        {{ viewInfo.message }}
      </div>
      <div v-else-if="showEmptyChartState" class="chart-empty-info">
        {{ t('dashboard.chart_no_data_found') }}
      </div>
      <ChartInsightHeader
        v-else-if="canShowInsightHeader && effectiveInsightLayout === 'top'"
        :compact="compactInsightHeader"
        :density="insightDensity"
        :max-stats="insightMaxStats"
        :chart-type="chartType"
        :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
        :x="renderXAxis"
        :y="renderYAxis"
        :series="renderSeries"
        :data="displayData"
        :sql="viewInfo.sql"
        :insight="viewInfo.chart?.insight"
      />
      <div
        v-if="showChartContent"
        class="chart-content-row"
        :class="{ 'side-layout': effectiveInsightLayout === 'side' }"
      >
        <div v-if="chartLoading" class="chart-refresh-overlay">
          <span class="chart-loading-ring small" aria-hidden="true"></span>
          <span>{{ chartLoadingText }}</span>
        </div>
        <ChartInsightHeader
          v-if="canShowInsightHeader && effectiveInsightLayout === 'side'"
          :compact="compactInsightHeader"
          :density="insightDensity"
          layout="side"
          :max-stats="insightMaxStats"
          :chart-type="chartType"
          :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
          :x="renderXAxis"
          :y="renderYAxis"
          :series="renderSeries"
          :data="displayData"
          :sql="viewInfo.sql"
          :insight="viewInfo.chart?.insight"
          :featured-side="isFeaturedSideInsight"
        />
        <ChartComponent
          :key="chartComponentKey"
          :id="outerId || viewInfo.id"
          ref="chartRef"
          :type="chartType"
          :columns="[...(viewInfo.chart.columns || []), ...insightColumns]"
          :x="renderXAxis"
          :y="renderYAxis"
          :series="renderSeries"
          :data="displayData"
          :multi-quota-name="renderMultiQuotaName"
          :show-label="showLabel"
          :forecast="renderForecast"
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
      <SqViewDisplay :view-info="viewInfo" :outer-id="'enlarge-' + viewInfo.id" :show-label="showLabel" />
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

  .pivot-toolbar {
    min-height: 26px;
    margin: -4px 0 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    white-space: nowrap;

    .pivot-chip {
      flex: 0 0 auto;
      height: 24px;
      max-width: 140px;
      border: 0;
      border-radius: 4px;
      background: transparent;
      color: var(--workspace-text-primary, rgba(31, 35, 41, 1));
      cursor: pointer;
      font-size: 12px;
      line-height: 24px;
      padding: 0 4px;
      overflow: hidden;
      text-overflow: ellipsis;

      &.pivot-link {
        color: var(--ed-color-primary, #2f6bff);
        font-weight: 600;
      }

      &:hover,
      &:focus-visible {
        background: rgba(31, 35, 41, 0.06);
        outline: none;
      }

      &.pivot-link:hover,
      &.pivot-link:focus-visible {
        color: var(--ed-color-primary, #2f6bff);
      }

      &.pivot-group-chip {
        color: #d97706;
        font-weight: 600;
      }

      &.pivot-group-chip:not(.active):hover,
      &.pivot-group-chip:not(.active):focus-visible {
        color: #d97706;
        background: rgba(217, 119, 6, 0.1);
      }

      &.active {
        color: var(--ed-color-primary, #2f6bff);
        font-weight: 600;
      }
    }

    .pivot-summary {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--workspace-text-secondary, rgba(100, 106, 115, 1));
      font-size: 12px;
    }
  }

  &.insight-density-mini,
  &.insight-density-basic {
    .pivot-toolbar {
      margin-bottom: 4px;
      gap: 4px;

      .pivot-summary,
      > :nth-child(n + 3) {
        display: none;
      }
    }
  }
}

:global(.dashboard-pivot-popper) {
  padding: 8px !important;
  border: 1px solid rgba(31, 35, 41, 0.08) !important;
  border-radius: 8px !important;
  box-shadow: 0 12px 32px rgba(31, 35, 41, 0.12) !important;
}

:global(.dashboard-pivot-popper .pivot-menu),
:global(.dashboard-pivot-popper .pivot-time-panel),
:global(.dashboard-pivot-popper .pivot-range-panel) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

:global(.dashboard-pivot-popper .pivot-time-panel) {
  gap: 8px;
}

:global(.dashboard-pivot-popper .pivot-time-divider) {
  height: 1px;
  background: rgba(31, 35, 41, 0.08);
  margin: 2px 0;
}

:global(.dashboard-pivot-popper .pivot-menu-item) {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(31, 35, 41, 1);
  cursor: pointer;
  font-size: 13px;
  line-height: 20px;
  min-height: 32px;
  padding: 6px 10px;
  text-align: left;
}

:global(.dashboard-pivot-popper .pivot-menu-item:hover),
:global(.dashboard-pivot-popper .pivot-menu-item.active) {
  background: rgba(31, 35, 41, 0.06);
}

:global(.dashboard-pivot-popper .pivot-menu-item.active) {
  color: var(--ed-color-primary, rgba(28, 186, 144, 1));
  font-weight: 600;
}

:global(.dashboard-pivot-popper .pivot-menu-item.with-arrow) {
  align-items: center;
  display: flex;
  justify-content: space-between;
  width: 100%;
}

:global(.dashboard-pivot-popper .pivot-menu-arrow) {
  color: rgba(100, 106, 115, 0.82);
}

:global(.dashboard-pivot-popper .pivot-menu-item.with-arrow.active .pivot-menu-arrow) {
  color: var(--ed-color-primary, rgba(28, 186, 144, 1));
}

:global(.dashboard-pivot-popper .pivot-range-grid) {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

:global(.dashboard-pivot-popper .pivot-custom-range) {
  margin-top: 4px;
}

:global(.dashboard-pivot-popper .pivot-custom-range .ed-date-editor),
:global(.dashboard-pivot-popper .pivot-custom-range .el-date-editor) {
  width: 100%;
}

:global(.dashboard-pivot-popper .pivot-quick-row) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

:global(.dashboard-pivot-popper .pivot-quick-chip) {
  border: 1px solid rgba(51, 112, 255, 0.16);
  border-radius: 999px;
  background: rgba(51, 112, 255, 0.06);
  color: #12305f;
  cursor: pointer;
  font-size: 12px;
  line-height: 20px;
  min-width: 46px;
  padding: 2px 9px;
}

:global(.dashboard-pivot-popper .pivot-quick-chip:hover),
:global(.dashboard-pivot-popper .pivot-quick-chip.active) {
  background: rgba(51, 112, 255, 0.12);
  border-color: rgba(51, 112, 255, 0.28);
  color: var(--ed-color-primary, #1cba90);
  font-weight: 600;
}

:global(.dashboard-pivot-popper .pivot-calendar-head) {
  display: grid;
  grid-template-columns: 32px 1fr 32px;
  align-items: center;
  min-height: 30px;
}

:global(.dashboard-pivot-popper .pivot-calendar-title) {
  color: rgba(15, 23, 42, 1);
  font-size: 13px;
  font-weight: 700;
  text-align: center;
}

:global(.dashboard-pivot-popper .pivot-calendar-nav) {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(51, 112, 255, 1);
  cursor: pointer;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

:global(.dashboard-pivot-popper .pivot-calendar-nav:hover) {
  background: rgba(31, 35, 41, 0.06);
}

:global(.dashboard-pivot-popper .pivot-calendar-grid) {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 2px;
}

:global(.dashboard-pivot-popper .pivot-calendar-grid.weekdays) {
  color: rgba(100, 116, 139, 0.82);
  font-size: 12px;
  font-weight: 700;
  line-height: 22px;
  text-align: center;
}

:global(.dashboard-pivot-popper .pivot-calendar-day) {
  aspect-ratio: 1 / 1;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: rgba(15, 23, 42, 1);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  min-width: 0;
  padding: 0;
}

:global(.dashboard-pivot-popper .pivot-calendar-day:hover) {
  background: rgba(51, 112, 255, 0.1);
}

:global(.dashboard-pivot-popper .pivot-calendar-day.muted) {
  color: rgba(100, 116, 139, 0.7);
}

:global(.dashboard-pivot-popper .pivot-calendar-day.in-range) {
  background: rgba(51, 112, 255, 0.11);
  color: rgba(15, 23, 42, 1);
  font-weight: 700;
}

:global(.dashboard-pivot-popper .pivot-calendar-day.endpoint) {
  background: rgba(37, 99, 235, 1);
  color: #fff;
  font-weight: 800;
}

:global(.dashboard-pivot-popper .pivot-calendar-foot) {
  align-items: center;
  border-top: 1px solid rgba(31, 35, 41, 0.08);
  color: rgba(100, 106, 115, 1);
  display: flex;
  font-size: 11px;
  gap: 8px;
  justify-content: space-between;
  line-height: 18px;
  padding-top: 7px;
}

:global(.dashboard-pivot-popper .pivot-clear-btn) {
  border: 0;
  border-radius: 6px;
  background: rgba(31, 35, 41, 0.06);
  color: rgba(51, 112, 255, 1);
  cursor: pointer;
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  line-height: 22px;
  padding: 0 8px;
}

:global(.dashboard-pivot-popper .pivot-clear-btn:hover) {
  background: rgba(51, 112, 255, 0.12);
}

:global(.dashboard-pivot-popper .pivot-group-value-panel) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 190px;
}

:global(.dashboard-pivot-popper .pivot-group-search .ed-input__wrapper),
:global(.dashboard-pivot-popper .pivot-group-search .el-input__wrapper) {
  border-radius: 7px;
  box-shadow: 0 0 0 1px rgba(31, 35, 41, 0.08) inset;
}

:global(.dashboard-pivot-popper .pivot-group-value-toolbar) {
  align-items: center;
  border-bottom: 1px solid rgba(31, 35, 41, 0.08);
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding-bottom: 8px;
}

:global(.dashboard-pivot-popper .pivot-group-value-toolbar .pivot-group-value-all) {
  flex: 1 1 auto;
  min-width: 0;
}

:global(.dashboard-pivot-popper .pivot-group-value-list) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 236px;
  min-height: 34px;
  overflow-y: auto;
  padding-right: 2px;
}

:global(.dashboard-pivot-popper .pivot-group-value-item) {
  align-items: center;
  border-radius: 6px;
  color: rgba(31, 35, 41, 1);
  cursor: pointer;
  display: flex;
  gap: 8px;
  min-height: 30px;
  padding: 4px 6px;
}

:global(.dashboard-pivot-popper .pivot-group-value-item:hover) {
  background: rgba(31, 35, 41, 0.06);
}

:global(.dashboard-pivot-popper .pivot-group-value-item input) {
  accent-color: var(--ed-color-primary, #2f6bff);
  flex: 0 0 auto;
  height: 14px;
  margin: 0;
  width: 14px;
}

:global(.dashboard-pivot-popper .pivot-group-value-label) {
  flex: 1 1 auto;
  font-size: 13px;
  line-height: 18px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.dashboard-pivot-popper .pivot-group-value-empty) {
  color: rgba(100, 106, 115, 1);
  font-size: 12px;
  line-height: 30px;
  padding: 0 6px;
}

:global(.dashboard-pivot-popper .pivot-group-value-footer) {
  align-items: center;
  border-top: 1px solid rgba(31, 35, 41, 0.08);
  display: flex;
  gap: 6px;
  justify-content: space-between;
  padding-top: 8px;
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
    position: relative;
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

.chart-refresh-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 3;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 16px);
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--workspace-border-soft, rgba(31, 35, 41, 0.08));
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8px 20px rgba(31, 35, 41, 0.08);
  color: var(--workspace-text-secondary, #66758f);
  font-size: 12px;
  line-height: 28px;
  white-space: nowrap;
  pointer-events: none;
}

.chart-empty-info {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--workspace-text-secondary, #66758f);
  font-size: 13px;
}

.chart-base-container:has(.pivot-toolbar) .chart-show-area {
  height: calc(100% - 80px);
}

.insight-density-mini .chart-show-area {
  height: calc(100% - 34px);
}

.insight-density-basic .chart-show-area {
  height: calc(100% - 28px);
}

.insight-density-mini:has(.pivot-toolbar) .chart-show-area,
.insight-density-basic:has(.pivot-toolbar) .chart-show-area {
  height: calc(100% - 58px);
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
}

.chart-loading-ring {
  width: 56px;
  height: 56px;
  border: 5px solid #eef1f5;
  border-top-color: var(--ed-color-primary, #2f6bff);
  border-radius: 50%;
  animation: chart-loading-spin 0.85s linear infinite;

  &.small {
    width: 14px;
    height: 14px;
    border-width: 2px;
  }
}

.chart-loading-text {
  font-size: 13px;
  line-height: 20px;
  color: var(--workspace-text-secondary, #66758f);
}

@keyframes chart-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
