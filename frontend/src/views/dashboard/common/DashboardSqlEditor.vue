<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { dashboardApi } from '@/api/dashboard.ts'
import { externalMcpApi, type ExternalMcpServerInfo, type ExternalMcpToolInfo } from '@/api/externalMcp.ts'
import { request } from '@/utils/request.ts'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type {
  ChartAxis,
  ChartForecastConfig,
  ChartForecastMethod,
  ChartTypes,
} from '@/views/chat/component/BaseChart.ts'
import { isAverageAxis, isPercentAxis } from '@/views/chat/component/charts/utils.ts'
import {
  defaultPivotAggregationForAxes,
  resolvePivotMetricAggregations,
  withResolvedMetricSemantics,
} from '@/views/dashboard/utils/metricSemantics.ts'
import {
  inferPivotDimensions,
  isLikelyPivotDateField,
} from '@/views/dashboard/utils/pivotDimensions.ts'
import {
  availableTrendComparisonMetrics,
  defaultTrendComparisonMetrics,
  detectTrendAxisGranularity,
  type TrendComparisonMetric,
  type TrendAggregateMetric,
  type TrendTimeGranularity,
} from '@/views/chat/component/chartInsight.ts'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    viewInfo?: any
    dashboardInfo?: any
    allowStaticApply?: boolean
  }>(),
  {
    modelValue: false,
    viewInfo: null,
    dashboardInfo: null,
    allowStaticApply: false,
  }
)

const emits = defineEmits(['update:modelValue', 'applied'])
const { t } = useI18n()
type ChartDataSourceType = 'sql' | 'external_mcp'
type PreviewResultSnapshot = {
  fields: string[]
  data: Array<Record<string, any>>
  status: string
  message: string
  raw?: any
}

const mcpTextFallbacks: Record<string, string> = {
  chart_source_config: '数据来源',
  chart_source_sql: 'SQL',
  chart_source_mcp: 'MCP',
  chart_source_required: '请至少选择一个数据来源',
  chart_source_changed: '数据配置已修改，请先运行预览',
  chart_mixed_merge_no_common_field: 'SQL 和 MCP 没有可自动合并的同名维度字段',
  mcp_editor_no_server: '当前图表缺少第三方 MCP 数据源配置',
  mcp_editor_no_bound_server: '当前工作空间没有可用的第三方 MCP 数据源',
  mcp_editor_server: 'MCP 数据源',
  mcp_editor_select_server: '请选择 MCP 数据源',
  mcp_editor_select_tool: '请选择 MCP 函数',
  mcp_editor_invalid_arguments: '参数必须是合法 JSON 对象',
  mcp_editor_tool: 'MCP 函数',
  mcp_editor_result_path: '结果路径',
  mcp_editor_result_path_placeholder: '例如 items、data.items、by_priority',
  mcp_editor_key_field: '键字段名',
  mcp_editor_value_field: '值字段名',
  mcp_editor_arguments: '参数 JSON',
  mcp_editor_changed: 'MCP 配置已修改，请先运行预览',
  mcp_editor_need_preview: 'MCP 配置修改后需要先运行预览',
  mcp_editor_input_schema: '参数说明',
  mcp_editor_parameters: '函数参数',
  mcp_editor_advanced_arguments: '高级 JSON',
  mcp_editor_servers_load_failed: 'MCP 数据源列表获取失败',
  mcp_editor_tools_load_failed: 'MCP 函数列表获取失败',
}

function mt(key: string) {
  const i18nKey = `dashboard.${key}`
  const value = t(i18nKey)
  return value === i18nKey ? mcpTextFallbacks[key] || value : value
}

const visible = computed({
  get() {
    return props.modelValue
  },
  set(value: boolean) {
    emits('update:modelValue', value)
  },
})

const form = reactive({
  sourceTypes: ['sql'] as ChartDataSourceType[],
  primarySource: 'sql' as ChartDataSourceType,
  sql: '',
  title: '',
  chartType: 'table' as ChartTypes,
  columns: [] as string[],
  x: '',
  y: [] as string[],
  series: '',
  multiQuotaName: '',
  insightEnabled: true,
  insightComparisonEnabled: true,
  insightComparisonMetrics: [] as TrendComparisonMetric[],
  insightAggregateEnabled: true,
  insightAggregateMetrics: [] as TrendAggregateMetric[],
  forecastEnabled: false,
  forecastMethod: 'auto' as ChartForecastMethod,
  forecastPeriods: 7,
  forecastHistoryWindow: 0,
  pivotEnabled: false,
  pivotTimeField: '',
  pivotGroupField: '',
  pivotGroupEnabled: true,
  pivotRangeEnabled: true,
  pivotGranularity: 'day' as 'day' | 'week' | 'month',
  pivotRange: 'source' as 'source' | '7d' | '14d' | '30d' | '90d' | 'all' | 'custom',
  pivotCustomStart: '',
  pivotCustomEnd: '',
  pivotGroupValues: [] as string[],
  mcpServerId: '',
  mcpTool: '',
  mcpArgumentsObject: {} as Record<string, any>,
  mcpArgumentsText: '{}',
  mcpResultPath: '',
  mcpKeyField: '',
  mcpValueField: '',
})

const preview = reactive({
  fields: [] as string[],
  data: [] as Array<Record<string, any>>,
  status: 'success',
  message: '',
  raw: undefined as any,
})
const sourcePreview = reactive({
  fields: [] as string[],
  data: [] as Array<Record<string, any>>,
})
const sourceResults = reactive<Record<ChartDataSourceType, PreviewResultSnapshot>>({
  sql: createEmptyPreviewResultSnapshot(),
  external_mcp: createEmptyPreviewResultSnapshot(),
})
const mergeState = reactive({
  joinFields: [] as string[],
  fieldMap: {
    sql: {} as Record<string, string>,
    external_mcp: {} as Record<string, string>,
  },
})

const loading = ref(false)
const mcpServersLoading = ref(false)
const mcpServersError = ref('')
const mcpServers = ref<ExternalMcpServerInfo[]>([])
const mcpToolsLoading = ref(false)
const mcpToolsError = ref('')
const mcpTools = ref<ExternalMcpToolInfo[]>([])
const mcpFilterOptionsLoading = ref(false)
const mcpFilterOptions = ref<Record<string, string[]>>({})
const previewVersion = ref(0)
const lastPreviewSql = ref('')
const lastPreviewSignature = ref('')
const initializedPivotGroupValueField = ref('')
const PIVOT_GROUP_SELECT_ALL_VALUE = '__dashboard_pivot_group_select_all__'
const PIVOT_GROUP_SELECT_NONE_VALUE = '__dashboard_pivot_group_select_none__'

function isExternalSnapshotChart(viewInfo: any) {
  return viewInfo?.externalSnapshot === true || viewInfo?.dataSourceType === 'external_mcp'
}

function normalizeSourceType(value: any): ChartDataSourceType | '' {
  if (value === 'external_mcp' || value === 'mcp') {
    return 'external_mcp'
  }
  if (value === 'sql') {
    return 'sql'
  }
  return ''
}

function normalizeSourceTypes(values: any): ChartDataSourceType[] {
  const rawValues = Array.isArray(values) ? values : []
  return Array.from(
    new Set(rawValues.map(normalizeSourceType).filter(Boolean) as ChartDataSourceType[])
  )
}

function chartSourceConfig(viewInfo: any) {
  return viewInfo?.sourceConfig || viewInfo?.source_config || {}
}

function resolveChartSourceTypes(viewInfo: any): ChartDataSourceType[] {
  const config = chartSourceConfig(viewInfo)
  const configured = normalizeSourceTypes(config.sources || config.sourceTypes || viewInfo?.sources)
  const sourceTypes = configured.length ? configured : []
  if ((viewInfo?.sql || viewInfo?.datasource) && !sourceTypes.includes('sql')) {
    sourceTypes.push('sql')
  }
  if (
    (
      isExternalSnapshotChart(viewInfo) ||
      viewInfo?.external_mcp_server_id ||
      viewInfo?.mcp ||
      config?.mcp
    ) &&
    !sourceTypes.includes('external_mcp')
  ) {
    sourceTypes.push('external_mcp')
  }
  return sourceTypes.length ? sourceTypes : ['sql']
}

function resolveMcpServerId(viewInfo: any) {
  const config = chartSourceConfig(viewInfo)
  const value =
    viewInfo?.external_mcp_server_id ||
      viewInfo?.mcp?.externalMcpServerId ||
      viewInfo?.mcp?.external_mcp_server_id ||
      config?.mcp?.externalMcpServerId ||
      config?.mcp?.external_mcp_server_id
  return value === undefined || value === null || value === '' ? '' : String(value)
}

const chartTypes: Array<{ label: string; value: ChartTypes }> = [
  { label: 'table', value: 'table' },
  { label: 'metric', value: 'metric' },
  { label: 'column', value: 'column' },
  { label: 'bar', value: 'bar' },
  { label: 'line', value: 'line' },
  { label: 'area', value: 'area' },
  { label: 'pie', value: 'pie' },
  { label: 'funnel', value: 'funnel' },
  { label: 'heatmap', value: 'heatmap' },
  { label: 'scatter', value: 'scatter' },
  { label: 'sankey', value: 'sankey' },
  { label: 'treemap', value: 'treemap' },
]

const sourceTypeOptions = computed(() => [
  { label: mt('chart_source_sql'), value: 'sql' as ChartDataSourceType },
  { label: mt('chart_source_mcp'), value: 'external_mcp' as ChartDataSourceType },
])
const hasSqlSource = computed(() => form.sourceTypes.includes('sql'))
const hasMcpSource = computed(() => form.sourceTypes.includes('external_mcp'))
const isMixedSource = computed(() => hasSqlSource.value && hasMcpSource.value)
const isExternalSnapshot = computed(() => hasMcpSource.value && !hasSqlSource.value)
const isMaterializedSource = computed(() => isExternalSnapshot.value || isMixedSource.value)
const editorTitle = computed(() => t('dashboard.edit_chart'))
const snapshotSourceTitle = computed(() => {
  const mcp = props.viewInfo?.mcp || {}
  const server = mcpServers.value.find((item) => stableId(item.id) === stableId(form.mcpServerId))
  return [server?.name || mcp.server || t('dashboard.external_snapshot_source'), form.mcpTool || mcp.tool]
    .filter(Boolean)
    .join(' / ')
})
const snapshotMetaText = computed(() => {
  const mcp = props.viewInfo?.mcp || {}
  return [mcp.timezone, mcp.snapshotAt].filter(Boolean).join(' · ')
})
const selectedMcpTool = computed(() => mcpTools.value.find((item) => item.name === form.mcpTool))
const selectedMcpToolDescription = computed(() => selectedMcpTool.value?.description || '')
const mcpParameterFields = computed(() => buildMcpParameterFields(selectedMcpTool.value?.input_schema))
const mcpResultPathOptions = computed(() => buildMcpResultPathOptions(selectedMcpTool.value?.output_schema))
const selectedMcpToolSchemaText = computed(() => {
  const schema = selectedMcpTool.value?.input_schema
  if (!schema || Object.keys(schema).length === 0) {
    return ''
  }
  return formatJson(schema)
})
const stableId = (value: any) => (value === undefined || value === null || value === '' ? '' : String(value))
const currentExternalMcpServerId = computed(() => stableId(form.mcpServerId))
const currentExternalMcpTenantId = computed(() =>
  stableId(
    props.viewInfo?.tenant_id ||
    props.viewInfo?.tenantId ||
    props.viewInfo?.mcp?.tenantId ||
    props.viewInfo?.mcp?.tenant_id ||
    props.dashboardInfo?.tenant_id ||
    props.dashboardInfo?.tenantId
  )
)
const currentDashboardId = computed(() => stableId(props.dashboardInfo?.id || props.viewInfo?.dashboard_id || props.viewInfo?.dashboardId || props.viewInfo?.mcp?.dashboardId || props.viewInfo?.mcp?.dashboard_id))
const fieldOptions = computed(() => toFieldOptions(sourcePreview.fields))
const seriesFieldOptions = computed(() => {
  const excluded = new Set(form.y)
  if (form.chartType !== 'pie' && form.x) {
    excluded.add(form.x)
  }
  return toFieldOptions(sourcePreview.fields.filter((field) => !excluded.has(field)))
})
const pivotTimeFieldOptions = computed(() => {
  const dateFields = sourcePreview.fields.filter((field) =>
    isLikelyPivotDateField(field, sourcePreview.data)
  )
  return toFieldOptions(dateFields.length ? dateFields : sourcePreview.fields)
})
const canRunPreview = computed(() => Boolean(props.viewInfo?.datasource) && hasSqlSource.value)
const canRunEditorPreview = computed(() => {
  if (!hasSqlSource.value && !hasMcpSource.value) {
    return false
  }
  if (hasSqlSource.value && !props.viewInfo?.datasource) {
    return false
  }
  if (hasMcpSource.value && !currentExternalMcpServerId.value) {
    return false
  }
  return true
})
const sourceChangedAfterPreview = computed(() => currentPreviewSignature() !== lastPreviewSignature.value)
const sqlChangedAfterPreview = computed(
  () => hasSqlSource.value && !hasMcpSource.value && sourceChangedAfterPreview.value
)
const mcpChangedAfterPreview = computed(
  () => hasMcpSource.value && !hasSqlSource.value && sourceChangedAfterPreview.value
)
const mixedChangedAfterPreview = computed(() => isMixedSource.value && sourceChangedAfterPreview.value)
const previewDisplayFields = computed(() => visiblePreviewFields(preview.fields, preview.data))
const previewTableFields = computed(() => previewDisplayFields.value.slice(0, 10))
const chartPreviewId = computed(() => `dashboard-sql-preview-${props.viewInfo?.id || 'new'}-${previewVersion.value}`)
const showXAxis = computed(() => !['table', 'metric', 'pie'].includes(form.chartType))
const showSeries = computed(() => !['table', 'metric', 'funnel', 'scatter'].includes(form.chartType))
const supportsInsightConfig = computed(() => !['table', 'metric'].includes(form.chartType))
const supportsPivotConfig = computed(() => hasSqlSource.value && !hasMcpSource.value && !['table', 'metric'].includes(form.chartType))
const supportsForecastConfig = computed(
  () => ['line', 'area'].includes(form.chartType) && Boolean(form.x) && form.y.length > 0
)
const effectiveSeriesField = computed(() => normalizeSeriesField(form.series))
const supportsTrendInsightConfig = computed(
  () => ['line', 'area'].includes(form.chartType) && Boolean(form.x) && form.y.length === 1 && !effectiveSeriesField.value
)
const trendTimeGranularity = computed<TrendTimeGranularity | null>(() =>
  supportsTrendInsightConfig.value ? detectTrendAxisGranularity(sourcePreview.data, form.x) : null
)
const supportsComparisonInsightConfig = computed(
  () =>
    supportsTrendInsightConfig.value &&
    availableTrendComparisonMetrics(trendTimeGranularity.value).length > 0
)
const selectedMetricAxis = computed<ChartAxis | undefined>(() => {
  const field = form.y[0]
  return field ? { name: field, value: field } : undefined
})
const selectedMetricIsRatioOrAverage = computed(() => {
  const axis = selectedMetricAxis.value
  if (!axis) {
    return false
  }
  return isPercentAxis(axis, sourcePreview.data) || isAverageAxis(axis)
})
const chartPreviewYFields = computed(() => {
  if (form.chartType === 'table') {
    return []
  }
  if (form.chartType === 'pie') {
    return form.y.slice(0, 1)
  }
  return form.y
})
const activePivotGroupValueField = computed(() => form.pivotGroupField || effectiveSeriesField.value)
const previewHasPivotGroupField = computed(() => {
  const field = activePivotGroupValueField.value
  return Boolean(field && visiblePreviewFields([field], preview.data).includes(field))
})
const sourceHasPivotGroupValues = computed(() => {
  const field = activePivotGroupValueField.value
  return Boolean(field && collectPivotGroupValueCounts(field).size > 0)
})
const chartPreviewSeriesFields = computed(() => {
  const field = form.chartType === 'pie' ? effectiveSeriesField.value || form.x : effectiveSeriesField.value
  return field && previewDisplayFields.value.includes(field) ? [field] : []
})
const showPivotGroupValueConfig = computed(
  () =>
    supportsPivotConfig.value &&
    form.pivotEnabled &&
    form.pivotGroupEnabled &&
    Boolean(activePivotGroupValueField.value) &&
    sourceHasPivotGroupValues.value
)
const pivotGroupValueOptions = computed(() => {
  const field = activePivotGroupValueField.value
  if (!field) {
    return []
  }
  const counts = collectPivotGroupValueCounts(field)
  unique(form.pivotGroupValues.map(normalizePivotGroupValue)).forEach((value) => {
    if (value && !counts.has(value)) {
      counts.set(value, 0)
    }
  })
  return Array.from(counts.entries())
    .map(([value, count]) => ({
      label: count > 0 ? value : `${value} (0)`,
      value,
    }))
    .sort((a, b) => a.value.localeCompare(b.value, undefined, { numeric: true, sensitivity: 'base' }))
})
const previewDisplayData = computed(() => {
  if (!showPivotGroupValueConfig.value || !previewHasPivotGroupField.value) {
    return preview.data
  }
  const field = activePivotGroupValueField.value
  const selected = new Set(unique(form.pivotGroupValues.map(normalizePivotGroupValue)))
  if (!field || selected.size === 0) {
    return []
  }
  return preview.data.filter((row) => selected.has(normalizePivotGroupValue(row?.[field])))
})
const hasPreviewData = computed(() => preview.status !== 'failed' && previewDisplayData.value.length > 0)
const pivotGroupValueSelectionText = computed(
  () => `${form.pivotGroupValues.length}/${pivotGroupValueOptions.value.length}`
)

function comparisonMetricLabel(metric: TrendComparisonMetric, granularity: TrendTimeGranularity | null) {
  if (metric === 'week_over_week' && granularity === 'day') {
    return t('dashboard.insight_week_same_period')
  }
  if (metric === 'day_over_day') {
    return t('dashboard.insight_day_over_day')
  }
  if (metric === 'week_over_week') {
    return t('dashboard.insight_week_over_week')
  }
  if (metric === 'month_over_month') {
    return t('dashboard.insight_month_over_month')
  }
  return t('dashboard.insight_year_over_year')
}

const comparisonMetricOptions = computed(() =>
  availableTrendComparisonMetrics(trendTimeGranularity.value).map((value) => ({
    label: comparisonMetricLabel(value, trendTimeGranularity.value),
    value,
  }))
)
const aggregateMetricOptions = computed(() => [
  { label: t('dashboard.insight_period_average'), value: 'average' as TrendAggregateMetric },
  {
    label: t('dashboard.insight_period_sum'),
    value: 'sum' as TrendAggregateMetric,
    disabled: selectedMetricIsRatioOrAverage.value,
  },
  { label: t('dashboard.insight_peak'), value: 'max' as TrendAggregateMetric },
  { label: t('dashboard.insight_lowest'), value: 'min' as TrendAggregateMetric },
])
const pivotGranularityOptions = computed(() => [
  { label: t('dashboard.pivot_day'), value: 'day' },
  { label: t('dashboard.pivot_week'), value: 'week' },
  { label: t('dashboard.pivot_month'), value: 'month' },
])
const pivotRangeOptions = computed(() => [
  { label: t('dashboard.pivot_source_time'), value: 'source' },
  { label: t('dashboard.pivot_recent_7d'), value: '7d' },
  { label: t('dashboard.pivot_recent_14d'), value: '14d' },
  { label: t('dashboard.pivot_recent_30d'), value: '30d' },
  { label: t('dashboard.pivot_recent_90d'), value: '90d' },
  { label: t('dashboard.pivot_all_time'), value: 'all' },
  { label: t('dashboard.pivot_custom_range'), value: 'custom' },
])
const forecastMethodOptions = computed<Array<{ label: string; value: ChartForecastMethod }>>(() => [
  { label: t('dashboard.forecast_method_auto'), value: 'auto' },
  { label: t('dashboard.forecast_method_linear'), value: 'linear' },
  { label: t('dashboard.forecast_method_polynomial'), value: 'polynomial' },
  { label: t('dashboard.forecast_method_exponential'), value: 'exponential' },
  { label: t('dashboard.forecast_method_logarithmic'), value: 'logarithmic' },
  { label: t('dashboard.forecast_method_power'), value: 'power' },
  { label: t('dashboard.forecast_method_reciprocal'), value: 'reciprocal' },
  { label: t('dashboard.forecast_method_logistic'), value: 'logistic' },
  { label: t('dashboard.forecast_method_gompertz'), value: 'gompertz' },
  { label: t('dashboard.forecast_method_holt_winters'), value: 'holt_winters' },
])
type PivotGranularity = 'day' | 'week' | 'month'

function unique(values: Array<string | undefined | null>) {
  return Array.from(new Set(values.filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '').map((value) => `${value}`)))
}

function isMeaningfulPreviewValue(value: unknown) {
  if (value === undefined || value === null) {
    return false
  }
  if (typeof value === 'string') {
    return value.trim() !== ''
  }
  if (typeof value === 'number') {
    return Number.isFinite(value)
  }
  if (value instanceof Date) {
    return !Number.isNaN(value.getTime())
  }
  if (Array.isArray(value)) {
    return value.length > 0
  }
  if (typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length > 0
  }
  return true
}

function visiblePreviewFields(fields: string[], rows: Array<Record<string, any>>) {
  const orderedFields = unique([
    ...fields,
    ...rows.slice(0, 20).flatMap((row) => Object.keys(row || {})),
  ])
  const visibleFields = orderedFields.filter((field) =>
    rows.some((row) => isMeaningfulPreviewValue(row?.[field]))
  )
  return visibleFields.length ? visibleFields : orderedFields
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

function collectPivotGroupValueCounts(field: string) {
  const counts = new Map<string, number>()
  if (!field) {
    return counts
  }
  sourcePreview.data.forEach((row) => {
    const value = normalizePivotGroupValue(row?.[field])
    if (!value) {
      return
    }
    counts.set(value, (counts.get(value) || 0) + 1)
  })
  return counts
}

function collectPivotGroupSourceValues(field: string) {
  return Array.from(collectPivotGroupValueCounts(field).keys())
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }))
}

function toFieldOptions(fields: string[]) {
  return fields.map((field) => ({ label: field, value: field }))
}

function chartSupportsExplicitSeries(chartType: ChartTypes) {
  return !['table', 'metric', 'funnel', 'scatter'].includes(chartType)
}

function normalizeSeriesField(field: string) {
  if (!field || !chartSupportsExplicitSeries(form.chartType)) {
    return ''
  }
  if (form.y.includes(field)) {
    return ''
  }
  if (form.chartType !== 'pie' && field === form.x) {
    return ''
  }
  return field
}

function sanitizeSeriesSelection() {
  const nextSeries = normalizeSeriesField(form.series)
  if (form.series !== nextSeries) {
    form.series = nextSeries
  }
}

function toAxis(field: string): ChartAxis {
  return { value: field }
}

function toAxes(fields: string[], options: { metrics?: boolean } = {}): ChartAxis[] {
  const axes = unique(fields).map(toAxis)
  return options.metrics ? axes.map((axis) => withResolvedMetricSemantics(axis, sourcePreview.data)) : axes
}

function defaultComparisonMetrics(): TrendComparisonMetric[] {
  return defaultTrendComparisonMetrics(trendTimeGranularity.value)
}

function defaultAggregateMetrics(): TrendAggregateMetric[] {
  return selectedMetricIsRatioOrAverage.value ? ['average'] : ['average', 'sum']
}

function normalizeInsightSelections(fillEmpty = false) {
  const allowedComparisonValues = comparisonMetricOptions.value.map((item) => item.value)
  form.insightComparisonMetrics = form.insightComparisonMetrics.filter((value) =>
    allowedComparisonValues.includes(value)
  )
  const allowedAggregateValues = aggregateMetricOptions.value
    .filter((item) => !item.disabled)
    .map((item) => item.value)
  form.insightAggregateMetrics = form.insightAggregateMetrics.filter((value) =>
    allowedAggregateValues.includes(value)
  )

  if (fillEmpty && form.insightComparisonEnabled && form.insightComparisonMetrics.length === 0) {
    form.insightComparisonMetrics = defaultComparisonMetrics()
  }
  if (fillEmpty && form.insightAggregateEnabled && form.insightAggregateMetrics.length === 0) {
    form.insightAggregateMetrics = defaultAggregateMetrics()
  }
}

function initInsightConfig(insight?: any) {
  form.insightEnabled = insight?.enabled !== false
  form.insightComparisonEnabled = insight?.comparison?.enabled !== false
  form.insightAggregateEnabled = insight?.aggregate?.enabled !== false
  form.insightComparisonMetrics = Array.isArray(insight?.comparison?.metrics)
    ? [...insight.comparison.metrics]
    : defaultComparisonMetrics()
  form.insightAggregateMetrics = Array.isArray(insight?.aggregate?.metrics)
    ? [...insight.aggregate.metrics]
    : defaultAggregateMetrics()
  normalizeInsightSelections(true)
}

function buildInsightConfig() {
  return {
    enabled: form.insightEnabled,
    comparison: {
      enabled: form.insightComparisonEnabled,
      metrics: [...form.insightComparisonMetrics],
    },
    aggregate: {
      enabled: form.insightAggregateEnabled,
      metrics: [...form.insightAggregateMetrics],
    },
  }
}

function normalizeForecastMethod(value: any): ChartForecastMethod {
  const methods = forecastMethodOptions.value.map((item) => item.value)
  return methods.includes(value) ? value : 'auto'
}

function normalizeForecastNumber(value: any, fallback: number, min: number, max: number) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) {
    return fallback
  }
  return Math.max(min, Math.min(max, Math.round(numericValue)))
}

function initForecastConfig(forecast?: ChartForecastConfig) {
  form.forecastEnabled = forecast?.enabled === true
  form.forecastMethod = normalizeForecastMethod(forecast?.method)
  form.forecastPeriods = normalizeForecastNumber(forecast?.periods, 7, 1, 60)
  form.forecastHistoryWindow = normalizeForecastNumber(forecast?.historyWindow, 0, 0, 240)
}

function buildForecastConfig(): ChartForecastConfig {
  if (!supportsForecastConfig.value || !form.forecastEnabled) {
    return { enabled: false }
  }
  return {
    enabled: true,
    method: form.forecastMethod,
    periods: normalizeForecastNumber(form.forecastPeriods, 7, 1, 60),
    historyWindow: normalizeForecastNumber(form.forecastHistoryWindow, 0, 0, 240),
  }
}

function defaultPivotField(field: string, fallback = '') {
  return field || fallback
}

function normalizePivotGranularity(value: any, fallback: PivotGranularity = 'day'): PivotGranularity {
  return value === 'week' || value === 'month' || value === 'day' ? value : fallback
}

function defaultPivotGranularity(): PivotGranularity {
  const detected = detectTrendAxisGranularity(sourcePreview.data, form.pivotTimeField || form.x)
  return detected === 'week' || detected === 'month' ? detected : 'day'
}

function defaultPivotAggregation() {
  return defaultPivotAggregationForAxes(toAxes(form.y, { metrics: true }), sourcePreview.data)
}

function inferredPivotDimensions() {
  return inferPivotDimensions({
    fields: sourcePreview.fields,
    data: sourcePreview.data,
    chart: {
      xAxis: toAxes([form.x].filter(Boolean) as string[]),
      yAxis: toAxes(form.y, { metrics: true }),
      series: toAxes([effectiveSeriesField.value].filter(Boolean) as string[]),
      columns: toAxes(form.columns),
    },
    timeField: form.pivotTimeField || form.x,
    metricFields: form.y,
  })
}

function pickAllowedField(preferredFields: string[], allowedFields: string[], fallback = '') {
  const preferred = preferredFields.find((field) => field && allowedFields.includes(field))
  return preferred || allowedFields[0] || fallback
}

function normalizePivotSelections() {
  sanitizeSeriesSelection()
  if (!form.pivotTimeField) {
    form.pivotTimeField = defaultPivotField(form.x, sourcePreview.fields[0] || '')
  }
  form.pivotGroupField = effectiveSeriesField.value || inferredPivotDimensions()[0]?.field || ''
  const fields = sourcePreview.fields
  if (fields.length) {
    const timeFields = pivotTimeFieldOptions.value.map((item) => item.value)
    if (!timeFields.includes(form.pivotTimeField)) {
      form.pivotTimeField = pickAllowedField([form.x], timeFields, fields[0] || '')
    }
    if (form.pivotGroupField && !fields.includes(form.pivotGroupField)) form.pivotGroupField = ''
  }
  if (!form.pivotGroupField) {
    form.pivotGroupEnabled = false
  }
}

function initPivotConfig(pivot?: any) {
  form.pivotEnabled = pivot?.enabled === true
  form.pivotTimeField = pivot?.time_field || ''
  form.pivotGroupField = effectiveSeriesField.value || pivot?.group_field || ''
  form.pivotGroupEnabled =
    typeof pivot?.group_enabled === 'boolean' ? pivot.group_enabled : Boolean(form.pivotGroupField || effectiveSeriesField.value)
  form.pivotRangeEnabled = pivot?.range_enabled !== false
  form.pivotGranularity = normalizePivotGranularity(pivot?.granularity)
  form.pivotRange = pivot?.range || 'source'
  form.pivotCustomStart = pivot?.custom_start || ''
  form.pivotCustomEnd = pivot?.custom_end || ''
  form.pivotGroupValues = []
  initializedPivotGroupValueField.value = ''
  normalizePivotSelections()
  form.pivotGroupValues = Array.isArray(pivot?.group_values)
    ? unique(pivot.group_values.map(normalizePivotGroupValue))
    : pivotGroupValueOptions.value.map((item) => item.value)
  initializedPivotGroupValueField.value = activePivotGroupValueField.value
  syncPivotGroupValues({ forceAll: !Array.isArray(pivot?.group_values) })
  if (!pivot?.granularity) {
    form.pivotGranularity = defaultPivotGranularity()
  }
}

function buildPivotConfig(options: { includeGroupValues?: boolean } = {}) {
  if (!supportsPivotConfig.value || !form.pivotEnabled) {
    return { enabled: false }
  }
  const groupField = form.pivotGroupField || effectiveSeriesField.value
  const config: Record<string, any> = {
    enabled: true,
    client_filter_only: props.viewInfo?.pivot?.client_filter_only === true,
    time_field: form.pivotTimeField,
    metric_fields: [...form.y],
    metric_aggregations: resolvePivotMetricAggregations(toAxes(form.y, { metrics: true }), sourcePreview.data),
    metric_field: form.y[0] || '',
    group_field: groupField,
    group_enabled: Boolean(groupField && form.pivotGroupEnabled),
    dimensions: inferredPivotDimensions(),
    range_enabled: form.pivotRangeEnabled,
    granularity: form.pivotGranularity,
    range: form.pivotRange,
    custom_start: form.pivotCustomStart,
    custom_end: form.pivotCustomEnd,
    aggregation: defaultPivotAggregation(),
  }
  if (options.includeGroupValues !== false) {
    config.group_values = groupField ? unique(form.pivotGroupValues.map(normalizePivotGroupValue)) : []
  }
  return config
}

function previewPivotPayload() {
  if (!supportsPivotConfig.value || !form.pivotEnabled) {
    return undefined
  }
  return buildPivotConfig({ includeGroupValues: false })
}

function currentPreviewSignature() {
  return JSON.stringify({
    sources: [...form.sourceTypes],
    sql: hasSqlSource.value
      ? {
          datasource: props.viewInfo?.datasource || null,
          sql: form.sql.trim(),
          pivot: previewPivotPayload() || { enabled: false },
        }
      : null,
    mcp: hasMcpSource.value
      ? {
          externalMcpServerId: currentExternalMcpServerId.value || null,
          tool: form.mcpTool,
          argumentsText: (form.mcpArgumentsText || '').trim(),
          resultPath: form.mcpResultPath || '',
          keyField: form.mcpKeyField || '',
          valueField: form.mcpValueField || '',
        }
      : null,
  })
}

function hasCurrentPreviewData() {
  return preview.status !== 'failed' && (preview.fields.length > 0 || preview.data.length > 0)
}

function axisValues(axis?: Array<{ value?: string }>) {
  return (axis || []).map((item) => item.value).filter(Boolean) as string[]
}

function collectFields(viewInfo: any) {
  const fields: string[] = []
  const dataObj = viewInfo?.data || {}
  fields.push(...(Array.isArray(dataObj.source_fields) ? dataObj.source_fields : []))
  ;(dataObj.source_data || []).slice(0, 20).forEach((row: Record<string, any>) => {
    fields.push(...Object.keys(row || {}))
  })
  fields.push(...(Array.isArray(dataObj.fields) ? dataObj.fields : []))
  ;(dataObj.data || []).slice(0, 20).forEach((row: Record<string, any>) => {
    fields.push(...Object.keys(row || {}))
  })
  const chart = viewInfo?.chart || {}
  fields.push(...axisValues(chart.columns))
  fields.push(...axisValues(chart.xAxis))
  fields.push(...axisValues(chart.yAxis))
  fields.push(...axisValues(chart.series))
  return unique(fields)
}

function collectCurrentPreviewFields(viewInfo: any) {
  const fields: string[] = []
  const dataObj = viewInfo?.data || {}
  fields.push(...(Array.isArray(dataObj.fields) ? dataObj.fields : []))
  ;(dataObj.data || []).slice(0, 20).forEach((row: Record<string, any>) => {
    fields.push(...Object.keys(row || {}))
  })
  return unique(fields)
}

function getPreviewResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

function createEmptyPreviewResultSnapshot(): PreviewResultSnapshot {
  return {
    fields: [],
    data: [],
    status: 'success',
    message: '',
  }
}

function previewResultSnapshot(result: any): PreviewResultSnapshot {
  return {
    fields: getPreviewResultFields(result),
    data: Array.isArray(result?.data) ? result.data : [],
    status: result?.status || 'success',
    message: result?.message || '',
    raw: result?.raw,
  }
}

function normalizePreviewResultSnapshot(value: any): PreviewResultSnapshot {
  if (!value || typeof value !== 'object') {
    return createEmptyPreviewResultSnapshot()
  }
  return {
    fields: getPreviewResultFields(value),
    data: Array.isArray(value?.data) ? value.data : [],
    status: value?.status || 'success',
    message: value?.message || '',
    raw: value?.raw,
  }
}

function setSourceResult(type: ChartDataSourceType, result: any) {
  const snapshot = previewResultSnapshot(result)
  sourceResults[type].fields = snapshot.fields
  sourceResults[type].data = snapshot.data
  sourceResults[type].status = snapshot.status
  sourceResults[type].message = snapshot.message
  sourceResults[type].raw = snapshot.raw
}

function normalizeJoinValue(value: any) {
  if (value === undefined || value === null) {
    return ''
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? '' : value.toISOString()
  }
  return typeof value === 'object' ? JSON.stringify(value) : `${value}`.trim()
}

function joinKey(row: Record<string, any>, fields: string[]) {
  return JSON.stringify(fields.map((field) => normalizeJoinValue(row?.[field])))
}

function hasNumericValues(rows: Array<Record<string, any>>, field: string) {
  return rows.some((row) => typeof row?.[field] === 'number')
}

function isPreferredJoinField(field: string, leftRows: Array<Record<string, any>>, rightRows: Array<Record<string, any>>) {
  return (
    isLikelyPivotDateField(field, leftRows) ||
    isLikelyPivotDateField(field, rightRows) ||
    (!hasNumericValues(leftRows, field) && !hasNumericValues(rightRows, field))
  )
}

function prefixedSourceField(type: ChartDataSourceType, field: string) {
  const label = type === 'sql' ? mt('chart_source_sql') : mt('chart_source_mcp')
  return `${label}.${field}`
}

function mergePreviewResults(
  sqlResult: PreviewResultSnapshot,
  mcpResult: PreviewResultSnapshot
): PreviewResultSnapshot & {
  joinFields: string[]
  fieldMap: Record<ChartDataSourceType, Record<string, string>>
} {
  if (sqlResult.status === 'failed') {
    return { ...sqlResult, joinFields: [], fieldMap: { sql: {}, external_mcp: {} } }
  }
  if (mcpResult.status === 'failed') {
    return { ...mcpResult, joinFields: [], fieldMap: { sql: {}, external_mcp: {} } }
  }
  const commonFields = sqlResult.fields.filter((field) => mcpResult.fields.includes(field))
  const joinFields = commonFields.filter((field) => isPreferredJoinField(field, sqlResult.data, mcpResult.data))
  if (joinFields.length === 0) {
    return {
      fields: [],
      data: [],
      status: 'failed',
      message: mt('chart_mixed_merge_no_common_field'),
      joinFields: [],
      fieldMap: { sql: {}, external_mcp: {} },
    }
  }

  const allMetricFields = [
    ...sqlResult.fields.filter((field) => !joinFields.includes(field)),
    ...mcpResult.fields.filter((field) => !joinFields.includes(field)),
  ]
  const duplicatedMetricFields = new Set(
    allMetricFields.filter((field, index) => allMetricFields.indexOf(field) !== index)
  )
  const fieldMap: Record<ChartDataSourceType, Record<string, string>> = {
    sql: {},
    external_mcp: {},
  }
  const makeOutputField = (type: ChartDataSourceType, field: string) =>
    joinFields.includes(field) ? field : duplicatedMetricFields.has(field) ? prefixedSourceField(type, field) : field
  ;(['sql', 'external_mcp'] as ChartDataSourceType[]).forEach((type) => {
    const fields = type === 'sql' ? sqlResult.fields : mcpResult.fields
    fields.forEach((field) => {
      fieldMap[type][field] = makeOutputField(type, field)
    })
  })

  const outputFields = unique([
    ...joinFields,
    ...sqlResult.fields.filter((field) => !joinFields.includes(field)).map((field) => fieldMap.sql[field]),
    ...mcpResult.fields.filter((field) => !joinFields.includes(field)).map((field) => fieldMap.external_mcp[field]),
  ])
  const rowMap = new Map<string, Record<string, any>>()
  const rowOrder: string[] = []
  const mergeRows = (type: ChartDataSourceType, rows: Array<Record<string, any>>) => {
    rows.forEach((row) => {
      const key = joinKey(row, joinFields)
      if (!rowMap.has(key)) {
        const baseRow: Record<string, any> = {}
        joinFields.forEach((field) => {
          baseRow[field] = row?.[field]
        })
        rowMap.set(key, baseRow)
        rowOrder.push(key)
      }
      const target = rowMap.get(key)!
      Object.entries(row || {}).forEach(([field, value]) => {
        const outputField = fieldMap[type][field] || field
        target[outputField] = value
      })
    })
  }
  mergeRows('sql', sqlResult.data)
  mergeRows('external_mcp', mcpResult.data)
  return {
    fields: outputFields,
    data: rowOrder.map((key) => rowMap.get(key)!).filter(Boolean),
    status: 'success',
    message: '',
    joinFields,
    fieldMap,
  }
}

function setMergeState(joinFields: string[], fieldMap: Record<ChartDataSourceType, Record<string, string>>) {
  mergeState.joinFields = [...joinFields]
  mergeState.fieldMap.sql = { ...(fieldMap.sql || {}) }
  mergeState.fieldMap.external_mcp = { ...(fieldMap.external_mcp || {}) }
}

function applyPreviewSnapshot(result: PreviewResultSnapshot) {
  updateSourcePreviewResult(result)
  resetFieldSelections()
  normalizePivotSelections()
  syncPivotGroupValues()
  updatePreviewResult(result)
}

function clearMergeState() {
  setMergeState([], { sql: {}, external_mcp: {} })
}

function updatePreviewResult(result: any) {
  preview.status = result?.status || 'success'
  preview.message = result?.message || ''
  preview.data = result?.data || []
  preview.fields = getPreviewResultFields(result)
  preview.raw = result?.raw
}

function updateSourcePreviewResult(result: any) {
  sourcePreview.data = result?.data || []
  sourcePreview.fields = getPreviewResultFields(result)
}

function formatJson(value: any) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch (_error) {
    return '{}'
  }
}

function parseJsonObject(text: string) {
  const trimmed = (text || '').trim()
  if (!trimmed) {
    return {}
  }
  const value = JSON.parse(trimmed)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Arguments must be a JSON object')
  }
  return value
}

function setMcpArgumentsObject(value: Record<string, any>) {
  Object.keys(form.mcpArgumentsObject).forEach((key) => {
    delete form.mcpArgumentsObject[key]
  })
  Object.entries(value || {}).forEach(([key, itemValue]) => {
    if (itemValue !== undefined) {
      form.mcpArgumentsObject[key] = itemValue
    }
  })
  form.mcpArgumentsText = formatJson(form.mcpArgumentsObject)
}

function syncMcpArgumentsObjectFromText(showMessage = true) {
  try {
    setMcpArgumentsObject(parseJsonObject(form.mcpArgumentsText))
    return true
  } catch (_error) {
    if (showMessage) {
      ElMessage.warning(mt('mcp_editor_invalid_arguments'))
    }
    return false
  }
}

function resolvedJsonSchemaVariant(schema: any) {
  const variants = [...(schema?.oneOf || []), ...(schema?.anyOf || [])]
  return variants.find((item: any) => item?.type && item.type !== 'null') || schema
}

function normalizeJsonSchemaType(schema: any) {
  const resolvedSchema = resolvedJsonSchemaVariant(schema)
  if (resolvedSchema !== schema) {
    return normalizeJsonSchemaType(resolvedSchema)
  }
  const rawType = schema?.type
  if (Array.isArray(rawType)) {
    return rawType.find((item) => item !== 'null') || rawType[0] || ''
  }
  if (rawType) {
    return rawType
  }
  if (Array.isArray(schema?.enum)) {
    const example = schema.enum.find((item: any) => item !== null && item !== undefined)
    return example === undefined ? 'string' : typeof example
  }
  if (schema?.properties) {
    return 'object'
  }
  if (schema?.items) {
    return 'array'
  }
  return 'string'
}

function schemaEnumValues(schema: any) {
  const resolvedSchema = resolvedJsonSchemaVariant(schema)
  if (Array.isArray(resolvedSchema?.enum)) {
    return resolvedSchema.enum.filter((item: any) => item !== null && item !== undefined).map((item: any) => `${item}`)
  }
  if (Array.isArray(resolvedSchema?.items?.enum)) {
    return resolvedSchema.items.enum.filter((item: any) => item !== null && item !== undefined).map((item: any) => `${item}`)
  }
  return []
}

function normalizeMcpOptionKey(value: string) {
  return String(value || '').replace(/[^a-z0-9]/gi, '').toLowerCase()
}

function pluralMcpOptionKey(value: string) {
  if (value.endsWith('y')) {
    return `${value.slice(0, -1)}ies`
  }
  if (value.endsWith('s')) {
    return value
  }
  return `${value}s`
}

function coerceMcpOptionValues(value: any) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item === null || item === undefined) return ''
        if (typeof item === 'object') {
          return item.value ?? item.id ?? item.name ?? item.label ?? ''
        }
        return item
      })
      .map((item) => String(item))
      .filter(Boolean)
  }
  if (value && typeof value === 'object') {
    return Object.keys(value)
  }
  return []
}

function mcpFilterOptionValues(paramName: string) {
  const rawName = String(paramName || '')
  const baseName = rawName.replace(/_in$/i, '')
  const candidates = new Set(
    [rawName, baseName, pluralMcpOptionKey(baseName)]
      .filter(Boolean)
      .map(normalizeMcpOptionKey)
  )
  for (const [key, value] of Object.entries(mcpFilterOptions.value || {})) {
    if (candidates.has(normalizeMcpOptionKey(key))) {
      return coerceMcpOptionValues(value)
    }
  }
  return []
}

function isMcpDateParameter(name: string, schema: any) {
  const resolvedSchema = resolvedJsonSchemaVariant(schema)
  const type = normalizeJsonSchemaType(schema)
  const text = [
    name,
    resolvedSchema?.title,
    resolvedSchema?.description,
    resolvedSchema?.format,
    resolvedSchema?.pattern,
  ].filter(Boolean).join(' ').toLowerCase()
  return type === 'string' && (
    resolvedSchema?.format === 'date' ||
    resolvedSchema?.format === 'date-time' ||
    /(^|[_\s-])date($|[_\s-])/.test(text) ||
    text.includes('yyyy-mm-dd') ||
    text.includes('\\\\d{4}-\\\\d{2}-\\\\d{2}')
  )
}

function schemaDefaultValue(schema: any, required = false): any {
  const type = normalizeJsonSchemaType(schema)
  const enumValues = schemaEnumValues(schema)
  if (schema?.default !== undefined && schema.default !== null) {
    return schema.default
  }
  if (required && Array.isArray(schema?.examples) && schema.examples.length > 0) {
    return schema.examples[0]
  }
  if (required && enumValues.length > 0) {
    return type === 'array' ? [enumValues[0]] : enumValues[0]
  }
  if (!required) {
    return undefined
  }
  if (type === 'integer' || type === 'number') {
    return schema?.minimum ?? 0
  }
  if (type === 'boolean') {
    return false
  }
  if (type === 'array') {
    return []
  }
  if (type === 'object') {
    return buildMcpArgumentsTemplate(schema)
  }
  return ''
}

function buildMcpArgumentsTemplate(schema: any) {
  const properties = schema?.properties || {}
  const requiredFields = new Set(Array.isArray(schema?.required) ? schema.required : [])
  const template: Record<string, any> = {}
  Object.entries(properties).forEach(([name, propertySchema]: [string, any]) => {
    const value = schemaDefaultValue(propertySchema, requiredFields.has(name))
    if (value !== undefined) {
      template[name] = value
    }
  })
  return template
}

function buildMcpParameterFields(schema: any) {
  const properties = schema?.properties || {}
  const requiredFields = new Set(Array.isArray(schema?.required) ? schema.required : [])
  return Object.entries(properties).map(([name, propertySchema]: [string, any]) => {
    const resolvedSchema = resolvedJsonSchemaVariant(propertySchema)
    const type = normalizeJsonSchemaType(propertySchema)
    const enumValues = schemaEnumValues(propertySchema)
    const dynamicValues = enumValues.length ? [] : mcpFilterOptionValues(name)
    const optionValues = enumValues.length ? enumValues : dynamicValues
    const multiple = type === 'array' || /_in$/i.test(name)
    const inputKind =
      isMcpDateParameter(name, propertySchema)
        ? 'date'
        : optionValues.length || multiple
        ? 'select'
        : type === 'boolean'
        ? 'boolean'
        : type === 'integer' || type === 'number'
        ? 'number'
        : 'text'
    return {
      name,
      required: requiredFields.has(name),
      type,
      inputKind,
      multiple,
      title: propertySchema?.title || resolvedSchema?.title || name,
      description: propertySchema?.description || resolvedSchema?.description || '',
      enumValues: optionValues,
      allowCreate: multiple && optionValues.length === 0,
      placeholder: inputKind === 'date'
        ? 'YYYY-MM-DD'
        : propertySchema?.description || resolvedSchema?.description || propertySchema?.title || resolvedSchema?.title || '',
    }
  })
}

function buildMcpResultPathOptions(schema: any) {
  const options: Array<{ label: string; value: string }> = []
  const visit = (node: any, path: string) => {
    if (!node || typeof node !== 'object') {
      return
    }
    const type = normalizeJsonSchemaType(node)
    if (path && (type === 'array' || node.additionalProperties || node.items)) {
      options.push({ label: path, value: path })
    }
    const properties = node.properties || {}
    Object.entries(properties).forEach(([key, child]: [string, any]) => {
      const nextPath = path ? `${path}.${key}` : key
      const childType = normalizeJsonSchemaType(child)
      if (childType === 'array' || childType === 'object' || child?.additionalProperties) {
        visit(child, nextPath)
      }
    })
  }
  visit(schema, '')
  return Array.from(new Map(options.map((item) => [item.value, item])).values())
}

function applyMcpToolDefaults(options: { force?: boolean } = {}) {
  const schema = selectedMcpTool.value?.input_schema
  if (!schema) {
    return
  }
  const currentArguments = syncMcpArgumentsObjectFromText(false) ? { ...form.mcpArgumentsObject } : {}
  if (options.force || Object.keys(currentArguments).length === 0) {
    setMcpArgumentsObject(buildMcpArgumentsTemplate(schema))
  }
  mcpParameterFields.value.forEach((field) => {
    if (field.multiple && !Array.isArray(form.mcpArgumentsObject[field.name])) {
      form.mcpArgumentsObject[field.name] = []
    }
  })
  syncMcpArgumentsTextFromObject()
  if (!form.mcpResultPath && mcpResultPathOptions.value.length === 1) {
    form.mcpResultPath = mcpResultPathOptions.value[0].value
  }
}

function handleMcpToolChange() {
  form.mcpResultPath = ''
  form.mcpKeyField = ''
  form.mcpValueField = ''
  applyMcpToolDefaults({ force: true })
  void loadMcpFilterOptions()
}

function handleMcpServerChange() {
  form.mcpTool = ''
  form.mcpResultPath = ''
  form.mcpKeyField = ''
  form.mcpValueField = ''
  setMcpArgumentsObject({})
  mcpTools.value = []
  mcpFilterOptions.value = {}
  void loadMcpTools()
}

function handleSourceTypesChange(values: ChartDataSourceType[]) {
  const nextSources = normalizeSourceTypes(values)
  form.sourceTypes = nextSources.length ? nextSources : ['sql']
  form.primarySource = hasMcpSource.value && !hasSqlSource.value ? 'external_mcp' : 'sql'
  if (!hasMcpSource.value) {
    form.mcpServerId = ''
    mcpTools.value = []
    mcpFilterOptions.value = {}
  } else {
    void loadMcpServers().then(() => loadMcpTools())
  }
  previewVersion.value += 1
}

function syncMcpArgumentsTextFromObject() {
  form.mcpArgumentsText = formatJson(form.mcpArgumentsObject)
}

async function loadMcpServers() {
  if (!hasMcpSource.value) {
    mcpServers.value = []
    mcpServersError.value = ''
    return
  }
  mcpServersLoading.value = true
  mcpServersError.value = ''
  try {
    mcpServers.value = await externalMcpApi.available({
      tenant_id: currentExternalMcpTenantId.value || null,
      dashboard_id: currentDashboardId.value || null,
    })
    if (!form.mcpServerId && mcpServers.value.length === 1) {
      form.mcpServerId = stableId(mcpServers.value[0].id)
    }
    if (!form.mcpServerId && mcpServers.value.length > 0) {
      form.mcpServerId = stableId(mcpServers.value[0].id)
    }
  } catch (error: any) {
    mcpServers.value = []
    mcpServersError.value = error?.message || mt('mcp_editor_servers_load_failed')
  } finally {
    mcpServersLoading.value = false
  }
}

function fetchMcpTools(externalMcpServerId: number | string) {
  const tenantId = currentExternalMcpTenantId.value
  const dashboardId = currentDashboardId.value
  return request.get<ExternalMcpToolInfo[]>(`/external-mcp/${externalMcpServerId}/tools`, {
    params: {
      ...(tenantId ? { tenant_id: tenantId } : {}),
      ...(dashboardId ? { dashboard_id: dashboardId } : {}),
    },
  })
}

function previewMcpTool(data: any, config?: any) {
  return request.post('/external-mcp/preview', data, config)
}

function filterOptionsToolName() {
  const currentTool = form.mcpTool || selectedMcpTool.value?.name || ''
  const namespace = currentTool.includes('.') ? currentTool.split('.').slice(0, -1).join('.') : ''
  const preferred = namespace ? `${namespace}.filter_options` : ''
  if (preferred && mcpTools.value.some((tool) => tool.name === preferred)) {
    return preferred
  }
  return mcpTools.value.find((tool) => /(^|\.)filter_options$/i.test(tool.name))?.name || ''
}

async function loadMcpFilterOptions() {
  const tool = filterOptionsToolName()
  if (!hasMcpSource.value || !currentExternalMcpServerId.value || !tool) {
    mcpFilterOptions.value = {}
    return
  }
  mcpFilterOptionsLoading.value = true
  try {
    const result: any = await previewMcpTool(
      {
        external_mcp_server_id: currentExternalMcpServerId.value,
        tenant_id: currentExternalMcpTenantId.value || null,
        dashboard_id: currentDashboardId.value || null,
        tool,
        arguments: {},
      },
      { requestOptions: { silent: true } }
    )
    const raw = result?.raw
    mcpFilterOptions.value = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}
  } catch (_error) {
    mcpFilterOptions.value = {}
  } finally {
    mcpFilterOptionsLoading.value = false
  }
}

function cleanMcpArguments(value: Record<string, any>) {
  const cleaned: Record<string, any> = {}
  Object.entries(value || {}).forEach(([key, itemValue]) => {
    if (itemValue === '' || itemValue === null || itemValue === undefined) {
      return
    }
    if (Array.isArray(itemValue) && itemValue.length === 0) {
      return
    }
    cleaned[key] = itemValue
  })
  return cleaned
}

async function loadMcpTools() {
  if (!hasMcpSource.value || !currentExternalMcpServerId.value) {
    mcpTools.value = []
    return
  }
  mcpToolsLoading.value = true
  mcpToolsError.value = ''
  try {
    mcpTools.value = (await fetchMcpTools(currentExternalMcpServerId.value)) as any
    if (!form.mcpTool && mcpTools.value.length > 0) {
      form.mcpTool = (mcpTools.value.find((tool) => !/(^|\.)filter_options$/i.test(tool.name)) || mcpTools.value[0]).name
      await loadMcpFilterOptions()
      applyMcpToolDefaults({ force: true })
    } else {
      await loadMcpFilterOptions()
      applyMcpToolDefaults()
    }
  } catch (error: any) {
    mcpTools.value = []
    mcpToolsError.value = error?.message || mt('mcp_editor_tools_load_failed')
  } finally {
    mcpToolsLoading.value = false
  }
}

function syncPivotGroupValues(options: { forceAll?: boolean } = {}) {
  const field = activePivotGroupValueField.value
  const sourceValues = collectPivotGroupSourceValues(field)
  const optionValues = pivotGroupValueOptions.value.map((item) => item.value)
  if (!field || (sourceValues.length === 0 && optionValues.length === 0)) {
    form.pivotGroupValues = []
    initializedPivotGroupValueField.value = field
    return
  }
  const fieldChanged = initializedPivotGroupValueField.value !== field
  const selected = unique(form.pivotGroupValues.map(normalizePivotGroupValue))
  if (options.forceAll || fieldChanged) {
    form.pivotGroupValues = sourceValues
  } else {
    form.pivotGroupValues = selected.filter((value) => optionValues.includes(value))
  }
  initializedPivotGroupValueField.value = field
}

function selectAllPivotGroupValues() {
  syncPivotGroupValues({ forceAll: true })
  previewVersion.value += 1
}

function clearPivotGroupValues() {
  form.pivotGroupValues = []
  previewVersion.value += 1
}

function handlePivotGroupValuesChange(values: string[]) {
  if (values.includes(PIVOT_GROUP_SELECT_ALL_VALUE)) {
    selectAllPivotGroupValues()
    return
  }
  if (values.includes(PIVOT_GROUP_SELECT_NONE_VALUE)) {
    clearPivotGroupValues()
    return
  }
  form.pivotGroupValues = unique(values.map(normalizePivotGroupValue))
}

function resetFieldSelections() {
  const fields = sourcePreview.fields
  if (!fields.length) {
    form.columns = []
    form.x = ''
    form.y = []
    form.series = ''
    return
  }
  form.columns = form.columns.filter((field) => fields.includes(field))
  form.y = form.y.filter((field) => fields.includes(field))
  if (form.columns.length === 0) form.columns = fields.slice(0, 8)
  if (!fields.includes(form.x)) form.x = fields[0] || ''
  if (!fields.includes(form.series)) form.series = ''
  sanitizeSeriesSelection()
  if (form.y.length === 0) {
    const numericField = fields.find((field) =>
      sourcePreview.data.some((row) => typeof row?.[field] === 'number')
    )
    form.y = [numericField || fields[Math.min(1, fields.length - 1)] || fields[0]]
  }
}

function initEditor() {
  const viewInfo = props.viewInfo || {}
  const chart = viewInfo.chart || {}
  const sourceTypes = resolveChartSourceTypes(viewInfo)
  const sourceConfig = chartSourceConfig(viewInfo)
  const mcpConfig = {
    ...(sourceConfig.mcp || {}),
    ...(viewInfo.mcp || {}),
  }
  const fields = collectFields(viewInfo)
  const currentFields = collectCurrentPreviewFields(viewInfo)
  form.sourceTypes = sourceTypes
  form.primarySource = sourceTypes.includes('external_mcp') && !sourceTypes.includes('sql') ? 'external_mcp' : 'sql'
  form.sql = viewInfo.sql || ''
  form.title = chart.title || ''
  form.chartType = chart.sourceType || chart.type || 'table'
  form.columns = axisValues(chart.columns)
  form.x = axisValues(chart.xAxis)[0] || ''
  form.y = axisValues(chart.yAxis)
  form.series = axisValues(chart.series)[0] || ''
  form.multiQuotaName = t('dashboard.metric_type')
  sourcePreview.fields = fields
  sourcePreview.data = viewInfo.data?.source_data || viewInfo.data?.data || []
  preview.fields = currentFields.length ? currentFields : fields
  preview.data = viewInfo.data?.data || []
  preview.status = viewInfo.status || 'success'
  preview.message = viewInfo.message || ''
  preview.raw = viewInfo.data?.raw
  setSourceResult('sql', normalizePreviewResultSnapshot(sourceConfig.sql?.lastResult))
  setSourceResult('external_mcp', normalizePreviewResultSnapshot(sourceConfig.mcp?.lastResult))
  setMergeState(
    Array.isArray(sourceConfig.merge?.joinFields) ? sourceConfig.merge.joinFields : [],
    {
      sql: sourceConfig.merge?.fieldMap?.sql || {},
      external_mcp: sourceConfig.merge?.fieldMap?.external_mcp || {},
    }
  )
  form.mcpServerId = resolveMcpServerId(viewInfo)
  form.mcpTool = mcpConfig.tool || ''
  setMcpArgumentsObject(mcpConfig.arguments || {})
  form.mcpResultPath = mcpConfig.resultPath || mcpConfig.result_path || ''
  form.mcpKeyField = mcpConfig.keyField || mcpConfig.key_field || ''
  form.mcpValueField = mcpConfig.valueField || mcpConfig.value_field || ''
  lastPreviewSql.value = form.sql.trim()
  resetFieldSelections()
  initInsightConfig(chart.insight)
  initForecastConfig(chart.forecast)
  initPivotConfig(viewInfo.pivot)
  lastPreviewSignature.value = currentPreviewSignature()
  previewVersion.value += 1
  if (hasMcpSource.value) {
    void loadMcpServers().then(() => loadMcpTools())
  } else {
    mcpServers.value = []
    mcpTools.value = []
    mcpFilterOptions.value = {}
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      initEditor()
    }
  }
)

watch(
  () => [
    form.chartType,
    form.columns.join('|'),
    form.x,
    form.y.join('|'),
    effectiveSeriesField.value,
    form.multiQuotaName,
    form.insightEnabled,
    form.insightComparisonEnabled,
    form.insightComparisonMetrics.join('|'),
    form.insightAggregateEnabled,
    form.insightAggregateMetrics.join('|'),
    form.forecastEnabled,
    form.forecastMethod,
    form.forecastPeriods,
    form.forecastHistoryWindow,
    form.pivotEnabled,
    form.pivotTimeField,
    form.pivotGroupField,
    form.pivotGroupEnabled,
    form.pivotRangeEnabled,
    form.pivotGranularity,
    form.pivotRange,
    form.pivotCustomStart,
    form.pivotCustomEnd,
    form.pivotGroupValues.join('|'),
  ],
  () => {
    previewVersion.value += 1
  }
)

watch(
  () => [
    form.chartType,
    form.x,
    form.y.join('|'),
    effectiveSeriesField.value,
    selectedMetricIsRatioOrAverage.value,
    trendTimeGranularity.value,
  ],
  () => {
    sanitizeSeriesSelection()
    if (!supportsForecastConfig.value) {
      form.forecastEnabled = false
    }
    normalizeInsightSelections(true)
    normalizePivotSelections()
    syncPivotGroupValues()
  }
)

async function previewSqlSource() {
  if (!props.viewInfo?.datasource) {
    ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    return null
  }
  if (!form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return null
  }
  const shouldPreviewPivot = supportsPivotConfig.value && form.pivotEnabled
  if (shouldPreviewPivot) {
    const sourceResult = await dashboardApi.preview_sql({
      datasource: props.viewInfo.datasource,
      sql: form.sql.trim(),
    })
    const sourceSnapshot = previewResultSnapshot(sourceResult)
    setSourceResult('sql', sourceSnapshot)
    updateSourcePreviewResult(sourceSnapshot)
    resetFieldSelections()
    normalizePivotSelections()
    syncPivotGroupValues()
    if (sourceSnapshot.status === 'failed') {
      return sourceSnapshot
    }
  }
  const result = await dashboardApi.preview_sql({
    datasource: props.viewInfo.datasource,
    sql: form.sql.trim(),
    pivot: previewPivotPayload(),
  })
  const snapshot = previewResultSnapshot(result)
  setSourceResult('sql', snapshot)
  return snapshot
}

async function previewMcpSource() {
  if (!currentExternalMcpServerId.value) {
    ElMessage.warning(mt('mcp_editor_no_server'))
    return null
  }
  if (!form.mcpTool) {
    ElMessage.warning(mt('mcp_editor_select_tool'))
    return null
  }
  let argumentsValue: Record<string, any>
  try {
    argumentsValue = cleanMcpArguments(parseJsonObject(form.mcpArgumentsText))
  } catch (_error) {
    ElMessage.warning(mt('mcp_editor_invalid_arguments'))
    return null
  }
  const result: any = await previewMcpTool({
    external_mcp_server_id: currentExternalMcpServerId.value,
    tenant_id: currentExternalMcpTenantId.value || null,
    dashboard_id: currentDashboardId.value || null,
    tool: form.mcpTool,
    arguments: argumentsValue,
    result_path: form.mcpResultPath || null,
    key_field: form.mcpKeyField || null,
    value_field: form.mcpValueField || null,
  })
  if (result?.mcp) {
    props.viewInfo.mcp = {
      ...(props.viewInfo.mcp || {}),
      ...result.mcp,
      externalMcpServerId: currentExternalMcpServerId.value,
      tenantId: currentExternalMcpTenantId.value || null,
    }
  }
  const snapshot = previewResultSnapshot(result)
  setSourceResult('external_mcp', snapshot)
  return snapshot
}

async function runPreview() {
  if (!hasSqlSource.value && !hasMcpSource.value) {
    ElMessage.warning(mt('chart_source_required'))
    return
  }
  loading.value = true
  try {
    clearMergeState()
    let nextPreview: PreviewResultSnapshot | null = null
    if (isMixedSource.value) {
      const sqlResult = await previewSqlSource()
      if (!sqlResult) {
        return
      }
      const mcpResult = await previewMcpSource()
      if (!mcpResult) {
        return
      }
      const merged = mergePreviewResults(sqlResult, mcpResult)
      setMergeState(merged.joinFields, merged.fieldMap)
      nextPreview = merged
    } else if (hasSqlSource.value) {
      nextPreview = await previewSqlSource()
    } else if (hasMcpSource.value) {
      nextPreview = await previewMcpSource()
    }
    if (!nextPreview) {
      return
    }
    if (hasSqlSource.value && !hasMcpSource.value && supportsPivotConfig.value && form.pivotEnabled) {
      updatePreviewResult(nextPreview)
    } else {
      applyPreviewSnapshot(nextPreview)
    }
    lastPreviewSql.value = form.sql.trim()
    lastPreviewSignature.value = currentPreviewSignature()
    previewVersion.value += 1
    if (preview.status === 'failed') {
      ElMessage.error(preview.message || t('dashboard.sql_editor_preview_failed'))
    } else {
      ElMessage.success(t('dashboard.sql_editor_preview_success'))
      await nextTick()
    }
  } finally {
    loading.value = false
  }
}

function buildChart() {
  sanitizeSeriesSelection()
  const sourceChart = props.viewInfo?.chart || {}
  const chart: any = {
    ...sourceChart,
    type: form.chartType,
    sourceType: form.chartType,
    title: form.title || sourceChart.title || t('dashboard.view'),
    columns: [],
    xAxis: [],
    yAxis: [],
    series: [],
  }
  if (supportsInsightConfig.value) {
    chart.insight = buildInsightConfig()
  } else {
    delete chart.insight
  }
  if (supportsForecastConfig.value) {
    chart.forecast = buildForecastConfig()
  } else {
    delete chart.forecast
  }

  if (form.chartType === 'table') {
    chart.columns = toAxes(form.columns.length ? form.columns : sourcePreview.fields)
    return chart
  }

  if (form.chartType === 'metric') {
    chart.yAxis = toAxes(form.y, { metrics: true })
    return chart
  }

  if (form.chartType === 'pie') {
    chart.yAxis = toAxes(form.y.slice(0, 1), { metrics: true })
    chart.series = toAxes([effectiveSeriesField.value || form.x].filter(Boolean) as string[])
    return chart
  }

  chart.xAxis = toAxes([form.x].filter(Boolean) as string[])
  chart.yAxis = toAxes(form.y, { metrics: true })
  chart.series = toAxes([effectiveSeriesField.value].filter(Boolean) as string[])
  return chart
}

function validateBeforeApply() {
  if (form.sourceTypes.length === 0) {
    ElMessage.warning(mt('chart_source_required'))
    return false
  }
  if (hasSqlSource.value && !form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return false
  }
  if (hasMcpSource.value && !currentExternalMcpServerId.value) {
    ElMessage.warning(mt('mcp_editor_select_server'))
    return false
  }
  if (hasMcpSource.value && !form.mcpTool) {
    ElMessage.warning(mt('mcp_editor_select_tool'))
    return false
  }
  if (props.allowStaticApply && !isMaterializedSource.value && !canRunPreview.value) {
    return true
  }
  if (sqlChangedAfterPreview.value) {
    ElMessage.warning(t('dashboard.sql_editor_need_preview'))
    return false
  }
  if (mcpChangedAfterPreview.value) {
    ElMessage.warning(mt('mcp_editor_need_preview'))
    return false
  }
  if (mixedChangedAfterPreview.value) {
    ElMessage.warning(mt('chart_source_changed'))
    return false
  }
  if (preview.status === 'failed') {
    ElMessage.warning(preview.message || t('dashboard.sql_editor_preview_failed'))
    return false
  }
  if (!hasCurrentPreviewData()) {
    ElMessage.warning(t('dashboard.sql_editor_run_preview'))
    return false
  }
  if (form.chartType === 'table') {
    return true
  }
  if (!form.y.length) {
    ElMessage.warning(t('dashboard.sql_editor_select_y'))
    return false
  }
  if (form.chartType === 'metric') {
    return true
  }
  if (form.chartType === 'pie' && !(form.series || form.x)) {
    ElMessage.warning(t('dashboard.sql_editor_select_series'))
    return false
  }
  if (form.chartType !== 'pie' && !form.x) {
    ElMessage.warning(t('dashboard.sql_editor_select_x'))
    return false
  }
  if (['heatmap', 'sankey'].includes(form.chartType) && !effectiveSeriesField.value) {
    ElMessage.warning(t('dashboard.sql_editor_select_series'))
    return false
  }
  if (form.pivotEnabled && (!form.pivotTimeField || !form.y.length)) {
    ElMessage.warning(t('dashboard.pivot_required'))
    return false
  }
  if (showPivotGroupValueConfig.value && form.pivotGroupEnabled && form.pivotGroupValues.length === 0) {
    ElMessage.warning(t('dashboard.pivot_group_values_required'))
    return false
  }
  if (form.pivotEnabled && form.y.includes(form.pivotTimeField)) {
    ElMessage.warning(t('dashboard.pivot_distinct_fields_required'))
    return false
  }
  if (
    form.pivotEnabled &&
    pivotTimeFieldOptions.value.length > 0 &&
    !pivotTimeFieldOptions.value.some((item) => item.value === form.pivotTimeField)
  ) {
    ElMessage.warning(t('dashboard.pivot_time_field_invalid'))
    return false
  }
  return true
}

function sourceResultForSave(type: ChartDataSourceType) {
  const result = sourceResults[type]
  return {
    fields: [...result.fields],
    data: [...result.data],
    status: result.status,
    message: result.message,
    ...(result.raw !== undefined ? { raw: result.raw } : {}),
  }
}

function applyChange() {
  if (!props.viewInfo || !validateBeforeApply()) return
  let mcpArgumentsValue: Record<string, any> = {}
  if (hasMcpSource.value) {
    try {
      mcpArgumentsValue = cleanMcpArguments(parseJsonObject(form.mcpArgumentsText))
    } catch (_error) {
      ElMessage.warning(mt('mcp_editor_invalid_arguments'))
      return
    }
  }
  props.viewInfo.sql = hasSqlSource.value ? form.sql.trim() : null
  const nextData: Record<string, any> = {
    ...(props.viewInfo.data || {}),
    fields: [...preview.fields],
    data: [...preview.data],
  }
  if (isExternalSnapshot.value && preview.raw !== undefined) {
    nextData.raw = preview.raw
  } else {
    delete nextData.raw
  }
  if (supportsPivotConfig.value && form.pivotEnabled) {
    nextData.source_fields = [...sourcePreview.fields]
    nextData.source_data = [...sourcePreview.data]
  } else if (isMixedSource.value) {
    nextData.source_fields = [...preview.fields]
    nextData.source_data = [...preview.data]
  } else {
    delete nextData.source_fields
    delete nextData.source_data
  }
  props.viewInfo.data = nextData
  props.viewInfo.status = preview.status
  props.viewInfo.dataState = preview.status === 'failed' ? 'failed' : 'ready'
  props.viewInfo.loadingProgress = 100
  props.viewInfo.message = preview.message
  props.viewInfo.chart = buildChart()
  props.viewInfo.pivot = buildPivotConfig()
  props.viewInfo.datasource = hasSqlSource.value ? props.viewInfo.datasource || null : null
  props.viewInfo.sourceConfig = {
    sources: [...form.sourceTypes],
    mode: isMixedSource.value ? 'mixed' : isExternalSnapshot.value ? 'external_mcp' : 'sql',
    primarySource: isExternalSnapshot.value ? 'external_mcp' : 'sql',
    merge: isMixedSource.value
      ? {
          strategy: 'join_by_common_dimensions',
          joinFields: [...mergeState.joinFields],
          fieldMap: {
            sql: { ...mergeState.fieldMap.sql },
            external_mcp: { ...mergeState.fieldMap.external_mcp },
          },
        }
      : null,
    sql: hasSqlSource.value
      ? {
          datasource: props.viewInfo.datasource || null,
          sql: form.sql.trim(),
          lastResult: sourceResultForSave('sql'),
        }
      : null,
    mcp: hasMcpSource.value
      ? {
          externalMcpServerId: currentExternalMcpServerId.value,
          tenantId: currentExternalMcpTenantId.value || null,
          tool: form.mcpTool,
          arguments: mcpArgumentsValue,
          resultPath: form.mcpResultPath || '',
          keyField: form.mcpKeyField || '',
          valueField: form.mcpValueField || '',
          auth: 'not_stored',
          lastResult: sourceResultForSave('external_mcp'),
        }
      : null,
  }
  props.viewInfo.primarySource = props.viewInfo.sourceConfig.primarySource
  props.viewInfo.sources = [...form.sourceTypes]
  if (hasMcpSource.value) {
    props.viewInfo.tenant_id = currentExternalMcpTenantId.value || props.viewInfo.tenant_id || null
    props.viewInfo.external_mcp_server_id = currentExternalMcpServerId.value
    props.viewInfo.mcp = {
      ...(props.viewInfo.mcp || {}),
      externalMcpServerId: currentExternalMcpServerId.value,
      tenantId: currentExternalMcpTenantId.value || null,
      tool: form.mcpTool,
      arguments: mcpArgumentsValue,
      resultPath: form.mcpResultPath || '',
      keyField: form.mcpKeyField || '',
      valueField: form.mcpValueField || '',
      auth: 'not_stored',
    }
  } else {
    props.viewInfo.external_mcp_server_id = null
    props.viewInfo.mcp = null
  }
  if (isMixedSource.value) {
    props.viewInfo.externalSnapshot = false
    props.viewInfo.dataSourceType = 'mixed'
  } else if (isExternalSnapshot.value) {
    props.viewInfo.externalSnapshot = true
    props.viewInfo.dataSourceType = 'external_mcp'
  } else {
    props.viewInfo.externalSnapshot = false
    props.viewInfo.dataSourceType = 'sql'
  }
  previewVersion.value += 1
  emits('applied', props.viewInfo)
  visible.value = false
  ElMessage.success(t('dashboard.sql_editor_applied'))
}

function closeDrawer() {
  visible.value = false
}
</script>

<template>
  <el-drawer
    v-model="visible"
    class="dashboard-sql-editor"
    direction="rtl"
    size="720px"
    :title="editorTitle"
    append-to-body
    :destroy-on-close="true"
  >
    <div v-loading="loading" class="sql-editor-body">
      <el-form label-position="top">
        <div class="source-config-panel">
          <div class="config-grid">
            <el-form-item :label="mt('chart_source_config')">
              <el-checkbox-group
                v-model="form.sourceTypes"
                class="source-checkbox-group"
                @change="handleSourceTypesChange"
              >
                <el-checkbox
                  v-for="item in sourceTypeOptions"
                  :key="item.value"
                  :label="item.value"
                >
                  {{ item.label }}
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </div>
        </div>
        <el-form-item v-if="hasSqlSource" :label="t('dashboard.sql_editor_sql')">
          <el-input
            v-model="form.sql"
            type="textarea"
            :autosize="{ minRows: 8, maxRows: 16 }"
            spellcheck="false"
            @keydown.stop
            @keyup.stop
          />
        </el-form-item>
        <div v-if="hasMcpSource" class="mcp-editor-panel">
          <el-alert
            class="editor-alert"
            type="info"
            :title="snapshotSourceTitle"
            :description="snapshotMetaText"
            :closable="false"
          />
          <el-alert
            v-if="mcpServersError"
            class="editor-alert"
            type="warning"
            :title="mcpServersError"
            :closable="false"
          />
          <el-alert
            v-else-if="!mcpServersLoading && mcpServers.length === 0"
            class="editor-alert"
            type="warning"
            :title="mt('mcp_editor_no_bound_server')"
            :closable="false"
          />
          <div class="config-grid">
            <el-form-item :label="mt('mcp_editor_server')">
              <el-select
                v-model="form.mcpServerId"
                filterable
                clearable
                :loading="mcpServersLoading"
                :placeholder="mt('mcp_editor_select_server')"
                @change="handleMcpServerChange"
              >
                <el-option
                  v-for="server in mcpServers"
                  :key="server.id"
                  :label="server.server_name ? `${server.name} - ${server.server_name}` : server.name"
                  :value="String(server.id)"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="mt('mcp_editor_tool')">
              <el-select
                v-model="form.mcpTool"
                filterable
                clearable
                :loading="mcpToolsLoading"
                :placeholder="mt('mcp_editor_select_tool')"
                @change="handleMcpToolChange"
              >
                <el-option
                  v-for="tool in mcpTools"
                  :key="tool.name"
                  :label="tool.title ? `${tool.name} - ${tool.title}` : tool.name"
                  :value="tool.name"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="mt('mcp_editor_result_path')">
              <el-select
                v-model="form.mcpResultPath"
                filterable
                allow-create
                clearable
                :placeholder="mt('mcp_editor_result_path_placeholder')"
              >
                <el-option
                  v-for="item in mcpResultPathOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
          </div>
          <el-alert
            v-if="mcpToolsError"
            class="editor-alert"
            type="warning"
            :title="mcpToolsError"
            :closable="false"
          />
          <div v-if="selectedMcpToolDescription" class="mcp-tool-description">
            {{ selectedMcpToolDescription }}
          </div>
          <details v-if="selectedMcpToolSchemaText" class="mcp-schema-details">
            <summary>{{ mt('mcp_editor_input_schema') }}</summary>
            <pre>{{ selectedMcpToolSchemaText }}</pre>
          </details>
          <div v-if="mcpParameterFields.length" class="mcp-parameter-section">
            <div class="mcp-section-title">{{ mt('mcp_editor_parameters') }}</div>
            <div class="config-grid">
              <el-form-item
                v-for="param in mcpParameterFields"
                :key="param.name"
                :label="`${param.title}${param.required ? ' *' : ''}`"
              >
                <el-date-picker
                  v-if="param.inputKind === 'date'"
                  v-model="form.mcpArgumentsObject[param.name]"
                  type="date"
                  value-format="YYYY-MM-DD"
                  clearable
                  :placeholder="param.placeholder"
                  @change="syncMcpArgumentsTextFromObject"
                />
                <el-select
                  v-else-if="param.inputKind === 'select'"
                  v-model="form.mcpArgumentsObject[param.name]"
                  filterable
                  clearable
                  :allow-create="param.allowCreate"
                  :multiple="param.multiple"
                  :loading="mcpFilterOptionsLoading"
                  collapse-tags
                  collapse-tags-tooltip
                  :placeholder="param.placeholder"
                  @change="syncMcpArgumentsTextFromObject"
                >
                  <el-option
                    v-for="value in param.enumValues"
                    :key="value"
                    :label="value"
                    :value="value"
                  />
                </el-select>
                <el-switch
                  v-else-if="param.inputKind === 'boolean'"
                  v-model="form.mcpArgumentsObject[param.name]"
                  @change="syncMcpArgumentsTextFromObject"
                />
                <el-input-number
                  v-else-if="param.inputKind === 'number'"
                  v-model="form.mcpArgumentsObject[param.name]"
                  :step="param.type === 'integer' ? 1 : 0.1"
                  controls-position="right"
                  @change="syncMcpArgumentsTextFromObject"
                />
                <el-input
                  v-else
                  v-model="form.mcpArgumentsObject[param.name]"
                  clearable
                  :placeholder="param.placeholder"
                  @input="syncMcpArgumentsTextFromObject"
                  @keydown.stop
                  @keyup.stop
                />
                <div v-if="param.description" class="mcp-param-description">{{ param.description }}</div>
              </el-form-item>
            </div>
          </div>
          <div class="config-grid">
            <el-form-item :label="mt('mcp_editor_key_field')">
              <el-input v-model="form.mcpKeyField" clearable placeholder="name" @keydown.stop @keyup.stop />
            </el-form-item>
            <el-form-item :label="mt('mcp_editor_value_field')">
              <el-input v-model="form.mcpValueField" clearable placeholder="value" @keydown.stop @keyup.stop />
            </el-form-item>
          </div>
          <details class="mcp-schema-details">
            <summary>{{ mt('mcp_editor_advanced_arguments') }}</summary>
            <el-form-item :label="mt('mcp_editor_arguments')">
              <el-input
                v-model="form.mcpArgumentsText"
                type="textarea"
                :autosize="{ minRows: 5, maxRows: 12 }"
                spellcheck="false"
                @blur="syncMcpArgumentsObjectFromText(false)"
                @keydown.stop
                @keyup.stop
              />
            </el-form-item>
          </details>
        </div>
        <div class="action-row">
          <el-button type="primary" :disabled="!canRunEditorPreview" @click="runPreview">{{ t('dashboard.sql_editor_run_preview') }}</el-button>
          <span v-if="hasSqlSource && !isExternalSnapshot && sqlChangedAfterPreview" class="muted">{{ t('dashboard.sql_editor_changed') }}</span>
          <span v-if="mcpChangedAfterPreview" class="muted">{{ mt('mcp_editor_changed') }}</span>
        </div>
        <el-alert
          v-if="preview.status === 'failed' && preview.message"
          class="editor-alert"
          type="error"
          :title="preview.message"
          :closable="false"
        />
        <div class="config-grid">
          <el-form-item :label="t('dashboard.sql_editor_chart_title')">
            <el-input v-model="form.title" @keydown.stop @keyup.stop />
          </el-form-item>
          <el-form-item :label="t('dashboard.sql_editor_chart_type')">
            <el-select v-model="form.chartType">
              <el-option
                v-for="item in chartTypes"
                :key="item.value"
                :label="t(`chat.chart_type.${item.label}`)"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item v-if="form.chartType === 'table'" :label="t('dashboard.sql_editor_columns')">
          <el-select v-model="form.columns" multiple filterable>
            <el-option
              v-for="field in fieldOptions"
              :key="field.value"
              :label="field.label"
              :value="field.value"
            />
          </el-select>
        </el-form-item>
        <div v-else class="config-grid">
          <el-form-item v-if="showXAxis" :label="t('dashboard.sql_editor_x')">
            <el-select v-model="form.x" filterable clearable>
              <el-option
                v-for="field in fieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('dashboard.sql_editor_y')">
            <el-select v-model="form.y" multiple filterable>
              <el-option
                v-for="field in fieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="showSeries" :label="t('dashboard.sql_editor_series')">
            <el-select v-model="form.series" filterable clearable>
              <el-option
                v-for="field in seriesFieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="showPivotGroupValueConfig"
            class="pivot-group-values-form-item"
            :label="`${t('dashboard.pivot_group_values')} (${pivotGroupValueSelectionText})`"
          >
            <el-select
              v-model="form.pivotGroupValues"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              popper-class="pivot-group-values-select-popper"
              :placeholder="t('dashboard.pivot_group_values_placeholder')"
              @change="handlePivotGroupValuesChange"
            >
              <el-option
                class="pivot-group-values-action-option"
                :label="t('dashboard.pivot_group_select_all')"
                :value="PIVOT_GROUP_SELECT_ALL_VALUE"
              />
              <el-option
                class="pivot-group-values-action-option"
                :label="t('dashboard.pivot_group_select_none')"
                :value="PIVOT_GROUP_SELECT_NONE_VALUE"
              />
              <el-option
                v-for="item in pivotGroupValueOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="form.y.length > 1 && !effectiveSeriesField && ['column', 'bar', 'line', 'area'].includes(form.chartType)"
            :label="t('dashboard.sql_editor_metric_group')"
          >
            <el-input v-model="form.multiQuotaName" @keydown.stop @keyup.stop />
          </el-form-item>
        </div>
        <div v-if="supportsInsightConfig" class="insight-config">
          <div class="insight-config-row">
            <span class="insight-config-caption">{{ t('dashboard.sql_editor_insight_config') }}</span>
            <el-checkbox v-model="form.insightEnabled">
              {{ t('dashboard.sql_editor_insight_enabled') }}
            </el-checkbox>
          </div>
          <template v-if="form.insightEnabled && supportsTrendInsightConfig">
            <div v-if="supportsComparisonInsightConfig" class="insight-config-row">
              <span class="insight-config-caption">{{ t('dashboard.sql_editor_simultaneous_display') }}</span>
              <el-checkbox v-model="form.insightComparisonEnabled">
                {{ t('dashboard.sql_editor_insight_comparison') }}
              </el-checkbox>
              <el-select
                v-model="form.insightComparisonMetrics"
                class="insight-metric-select"
                multiple
                collapse-tags
                collapse-tags-tooltip
                :disabled="!form.insightComparisonEnabled"
                @change="normalizeInsightSelections(false)"
              >
                <el-option
                  v-for="item in comparisonMetricOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </div>
            <div class="insight-config-row">
              <span class="insight-config-caption">{{ t('dashboard.sql_editor_simultaneous_display') }}</span>
              <el-checkbox v-model="form.insightAggregateEnabled">
                {{ t('dashboard.sql_editor_insight_aggregate') }}
              </el-checkbox>
              <el-select
                v-model="form.insightAggregateMetrics"
                class="insight-metric-select"
                multiple
                collapse-tags
                collapse-tags-tooltip
                :disabled="!form.insightAggregateEnabled"
                @change="normalizeInsightSelections(false)"
              >
                <el-option
                  v-for="item in aggregateMetricOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                  :disabled="item.disabled"
                />
              </el-select>
            </div>
          </template>
        </div>
        <div v-if="supportsForecastConfig" class="forecast-config">
          <div class="forecast-config-row">
            <span class="forecast-config-caption">{{ t('dashboard.forecast_config') }}</span>
            <el-checkbox v-model="form.forecastEnabled">
              {{ t('dashboard.forecast_enabled') }}
            </el-checkbox>
          </div>
          <div v-if="form.forecastEnabled" class="forecast-config-grid">
            <el-form-item :label="t('dashboard.forecast_method')">
              <el-select v-model="form.forecastMethod">
                <el-option
                  v-for="item in forecastMethodOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('dashboard.forecast_periods')">
              <el-input-number v-model="form.forecastPeriods" :min="1" :max="60" :step="1" />
            </el-form-item>
            <el-form-item :label="t('dashboard.forecast_history_window')">
              <el-input-number v-model="form.forecastHistoryWindow" :min="0" :max="240" :step="1" />
            </el-form-item>
          </div>
        </div>
        <div v-if="supportsPivotConfig" class="pivot-config">
          <div class="pivot-config-row">
            <span class="pivot-config-caption">{{ t('dashboard.pivot_config') }}</span>
            <el-checkbox v-model="form.pivotEnabled">
              {{ t('dashboard.pivot_enabled') }}
            </el-checkbox>
          </div>
          <div v-if="form.pivotEnabled" class="pivot-config-grid">
            <el-form-item :label="t('dashboard.pivot_time_field')">
              <el-select v-model="form.pivotTimeField" filterable>
                <el-option
                  v-for="field in pivotTimeFieldOptions"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('dashboard.pivot_granularity')">
              <el-select v-model="form.pivotGranularity">
                <el-option
                  v-for="item in pivotGranularityOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('dashboard.pivot_range_enabled')">
              <el-switch v-model="form.pivotRangeEnabled" />
            </el-form-item>
            <el-form-item v-if="form.pivotRangeEnabled" :label="t('dashboard.pivot_range')">
              <el-select v-model="form.pivotRange">
                <el-option
                  v-for="item in pivotRangeOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item
              v-if="form.pivotRangeEnabled && form.pivotRange === 'custom'"
              :label="t('dashboard.pivot_custom_range')"
            >
              <el-date-picker
                v-model="form.pivotCustomStart"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="t('common.start_time')"
              />
            </el-form-item>
            <el-form-item
              v-if="form.pivotRangeEnabled && form.pivotRange === 'custom'"
              :label="t('dashboard.pivot_custom_end')"
            >
              <el-date-picker
                v-model="form.pivotCustomEnd"
                type="date"
                value-format="YYYY-MM-DD"
                :placeholder="t('common.end_time')"
              />
            </el-form-item>
          </div>
        </div>
      </el-form>

      <div class="preview-title">{{ t('dashboard.sql_editor_chart_preview') }}</div>
      <div class="chart-preview">
        <ChartComponent
          v-if="hasPreviewData"
          :key="chartPreviewId"
          :id="chartPreviewId"
          :type="form.chartType"
          :columns="form.chartType === 'table' ? toAxes(previewTableFields) : []"
          :x="form.chartType !== 'table' && form.chartType !== 'metric' && form.chartType !== 'pie' ? toAxes([form.x]) : []"
          :y="toAxes(chartPreviewYFields, { metrics: true })"
          :series="toAxes(chartPreviewSeriesFields)"
          :data="previewDisplayData"
          :multi-quota-name="form.y.length > 1 && !effectiveSeriesField ? form.multiQuotaName : undefined"
          :forecast="buildForecastConfig()"
        />
        <div v-else class="empty-preview">{{ t('dashboard.sql_editor_no_preview_data') }}</div>
      </div>

      <div class="preview-title">{{ t('dashboard.sql_editor_data_preview') }}</div>
      <el-table
        v-if="preview.data.length"
        class="data-preview-table"
        :data="preview.data.slice(0, 8)"
        size="small"
        border
      >
        <el-table-column
          v-for="field in previewTableFields"
          :key="field"
          :prop="field"
          :label="field"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <div v-else class="empty-preview">{{ t('dashboard.sql_editor_no_preview_data') }}</div>
    </div>
    <template #footer>
      <el-button secondary @click="closeDrawer">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="applyChange">{{ t('dashboard.sql_editor_apply') }}</el-button>
    </template>
  </el-drawer>
</template>

<style scoped lang="less">
.sql-editor-body {
  padding-right: 4px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.muted {
  color: #8f959e;
  font-size: 13px;
}

.editor-alert {
  margin-bottom: 16px;
}

.source-config-panel {
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(31, 35, 41, 0.1);
  border-radius: 6px;
  background: #fff;
}

.source-checkbox-group {
  min-height: 32px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.mcp-editor-panel {
  padding: 12px;
  margin-bottom: 16px;
  border: 1px solid rgba(47, 107, 255, 0.18);
  border-radius: 6px;
  background: #f8fbff;
}

.mcp-editor-panel :deep(.ed-form-item:last-child),
.mcp-editor-panel :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.mcp-tool-description {
  margin: -4px 0 14px;
  color: #646a73;
  font-size: 12px;
  line-height: 18px;
}

.mcp-schema-details {
  margin: -4px 0 14px;
  color: #646a73;
  font-size: 12px;
}

.mcp-schema-details summary {
  cursor: pointer;
  color: #2f6bff;
  line-height: 20px;
}

.mcp-schema-details pre {
  max-height: 180px;
  overflow: auto;
  margin: 8px 0 0;
  padding: 8px 10px;
  border-radius: 4px;
  background: #fff;
  color: #1f2329;
  font-size: 12px;
  line-height: 18px;
  white-space: pre-wrap;
  word-break: break-word;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.insight-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 6px;
}

.forecast-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 6px;
}

.forecast-config-row {
  display: grid;
  grid-template-columns: 72px minmax(0, 1fr);
  align-items: center;
  column-gap: 12px;
  min-height: 32px;
}

.forecast-config-caption {
  color: #1f2329;
  font-size: 13px;
  font-weight: 500;
}

.forecast-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 12px;
}

.insight-config-row {
  display: grid;
  grid-template-columns: 72px 92px minmax(0, 1fr);
  align-items: center;
  column-gap: 12px;
  min-height: 32px;
}

.insight-config-caption {
  color: #1f2329;
  font-size: 13px;
  line-height: 20px;
}

.insight-metric-select {
  width: 100%;
}

.pivot-config {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 6px 0 8px;
}

.pivot-config-row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 32px;
}

.pivot-config-caption {
  color: #1f2329;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
}

.pivot-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.pivot-group-values-form-item {
  margin-bottom: 4px;
}

.pivot-group-checkbox {
  margin-top: -8px;
}

:global(.pivot-group-values-select-popper .ed-select-dropdown__item:first-child),
:global(.pivot-group-values-select-popper .el-select-dropdown__item:first-child),
:global(.pivot-group-values-select-popper .ed-select-dropdown__item:nth-child(2)),
:global(.pivot-group-values-select-popper .el-select-dropdown__item:nth-child(2)) {
  color: var(--ed-color-primary, #2f6bff);
  font-weight: 600;
}

:global(.pivot-group-values-select-popper .pivot-group-values-action-option.is-selected::after),
:global(.pivot-group-values-select-popper .pivot-group-values-action-option.selected::after) {
  display: none;
}

:global(.pivot-group-values-select-popper .pivot-group-values-action-option:nth-child(2)) {
  border-bottom: 1px solid rgba(31, 35, 41, 0.08);
  margin-bottom: 4px;
}

.preview-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  margin: 18px 0 8px;
}

.chart-preview {
  height: 300px;
  border: 1px solid #dee0e3;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
}

.empty-preview {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8f959e;
}

.data-preview-table {
  width: 100%;
}
</style>
