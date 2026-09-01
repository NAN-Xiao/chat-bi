<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CopyDocument, Delete, EditPen, Filter, FolderOpened, MoreFilled, Plus, WarningFilled } from '@element-plus/icons-vue'
import { datasourceApi } from '@/api/datasource'
import { dashboardApi } from '@/api/dashboard.ts'
import { externalMcpApi, type ExternalMcpServerInfo, type ExternalMcpToolInfo } from '@/api/externalMcp.ts'
import { trackingConfigApi } from '@/api/system.ts'
import { request } from '@/utils/request.ts'
import { formatRequestErrorMessage } from '@/utils/request.ts'
import BuilderSectionIcon from '@/assets/svg/dv-view.svg'
import AttributionWindowPicker from '@/views/dashboard/common/AttributionWindowPicker.vue'
import BuilderFieldPicker from '@/views/dashboard/common/BuilderFieldPicker.vue'
import BuilderFilterTree from '@/views/dashboard/common/BuilderFilterTree.vue'
import DistributionIntervalSettings from '@/views/dashboard/common/DistributionIntervalSettings.vue'
import DistributionMetricPicker from '@/views/dashboard/common/DistributionMetricPicker.vue'
import FunnelWindowPicker from '@/views/dashboard/common/FunnelWindowPicker.vue'
import IntervalLimitPicker from '@/views/dashboard/common/IntervalLimitPicker.vue'
import PathEventList from '@/views/dashboard/common/PathEventList.vue'
import PathSessionGapPicker from '@/views/dashboard/common/PathSessionGapPicker.vue'
import RevenueMetricPicker from '@/views/dashboard/common/RevenueMetricPicker.vue'
import {
  ATTRIBUTION_EVENT_LIMIT,
  DEFAULT_ATTRIBUTION_WINDOW,
  isValidAttributionWindow,
  normalizeAttributionWindow,
  type AttributionMethod,
  type AttributionWindowConfig,
} from '@/views/dashboard/common/attributionAnalysis.ts'
import type {
  DistributionIntervalConfig,
  DistributionMetricConfig,
} from '@/views/dashboard/common/distributionAnalysis.ts'
import {
  DEFAULT_FUNNEL_WINDOW,
  isValidFunnelWindow,
  normalizeFunnelWindow,
  type FunnelWindowConfig,
} from '@/views/dashboard/common/funnelAnalysis.ts'
import {
  DEFAULT_INTERVAL_LIMIT_SECONDS,
  INTERVAL_LIMIT_MAX_SECONDS,
  INTERVAL_LIMIT_MIN_SECONDS,
  clampIntervalLimitSeconds,
} from '@/views/dashboard/common/intervalAnalysis.ts'
import {
  DEFAULT_PATH_SESSION_GAP_SECONDS,
  PATH_EVENT_LIMIT,
  PATH_SESSION_GAP_MAX_SECONDS,
  PATH_SESSION_GAP_MIN_SECONDS,
  clampPathSessionGapSeconds,
  type PathAnalysisEvent,
} from '@/views/dashboard/common/pathAnalysis.ts'
import {
  DEFAULT_REVENUE_OBSERVATION_DAYS,
  REVENUE_OBSERVATION_MAX_DAYS,
  REVENUE_OBSERVATION_MIN_DAYS,
  clampRevenueObservationDays,
  revenueMetricUsesProperty,
  type RevenueMetricConfig,
} from '@/views/dashboard/common/revenueAnalysis.ts'
import DashboardDateExpressionPicker from '@/views/dashboard/common/DashboardDateExpressionPicker.vue'
import {
  cloneDashboardDateExpression,
  defaultDashboardDateExpression,
  normalizeDashboardDateExpression,
  validateDashboardDateExpression,
  type DashboardDateExpression,
} from '@/views/dashboard/common/dashboardDateExpression.ts'
import {
  eventScopedPropertyOptions,
  isEventUserPropertyOption,
  isNumericFieldOption,
  isSelectableFieldOption,
  isTimeFieldOption,
} from '@/views/dashboard/common/builderFieldPickerOptions.ts'
import { metricFilterRecoveryCandidates } from '@/views/dashboard/common/metricFilterRecovery.ts'
import {
  buildDashboardBuilderMetadataCacheKey,
  createFieldOptionIndex,
  getEventScopedFields,
  getCachedDashboardBuilderMetadata,
  resolveDashboardBuilderEventScope,
} from '@/views/dashboard/common/dashboardBuilderMetadata.ts'
import {
  formulaTokensToText,
  insertFormulaTokenAt,
  normalizeFormulaAtomicMetricDisplay,
  serializeFormulaTokensForContext,
  validateFormulaTokens,
  type FormulaAtomicMetric,
  type FormulaOperator,
  type FormulaToken,
} from '@/views/dashboard/common/formulaMetricUtils.ts'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type {
  ChartAxis,
  ChartForecastConfig,
  ChartForecastMethod,
  ChartTypes,
} from '@/views/chat/component/BaseChart.ts'
import { isRadialPartitionChartType } from '@/views/chat/component/chartTypes.ts'
import { isAverageAxis, isPercentAxis } from '@/views/chat/component/charts/utils.ts'
import {
  defaultPivotAggregationForAxes,
  resolvePivotMetricAggregations,
  withResolvedMetricSemantics,
} from '@/views/dashboard/utils/metricSemantics.ts'
import {
  DISTRIBUTION_DATE_COLUMN,
  DISTRIBUTION_TOTAL_COLUMN,
  normalizeDistributionTableViewInfo,
  shapeDistributionTableResult,
} from '@/views/dashboard/utils/distributionTable.ts'
import {
  inferPivotDimensions,
  isLikelyPivotDateField,
} from '@/views/dashboard/utils/pivotDimensions.ts'
import {
  buildPersistedPivotGroupValueSelection,
  normalizePivotGroupValueMode,
  type PivotGroupValueMode,
} from '@/views/dashboard/utils/pivotGroupValues.ts'
import {
  buildDashboardDateFilterRequest,
  buildDashboardDateSourcePreviewPivot,
  scanDashboardDateParameterTokens,
} from '@/views/dashboard/utils/dashboardDateFilter.ts'
import {
  DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED,
  buildDashboardDateFilterConfig,
  normalizeDashboardChartConfig,
} from '@/views/dashboard/utils/dashboardChartConfig.ts'
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
    canEditSql?: boolean
  }>(),
  {
    modelValue: false,
    viewInfo: null,
    dashboardInfo: null,
    allowStaticApply: false,
    canEditSql: false,
  }
)

const emits = defineEmits(['update:modelValue', 'applied'])
const { t } = useI18n()
const sqlEditorPermissionMessage = '当前账号没有 SQL 明细权限，无法编辑图表配置。'
type ChartDataSourceType = 'sql' | 'external_mcp'
type DashboardDateParameterType = '' | 'date' | 'yyyymmdd_number' | 'yyyymmdd_text' | 'timestamp'
const SQL_EDITOR_TIME_FIELD = 'dt'
const SQL_EDITOR_TIME_GRAIN = 'day'
const SQL_EDITOR_DATE_PARAMETER_TYPE: DashboardDateParameterType = 'yyyymmdd_number'
type ExecutionDatasourceOption = {
  id: number
  name: string
  role: 'bound' | 'roi'
}
type PreviewResultSnapshot = {
  fields: string[]
  data: Array<Record<string, any>>
  status: string
  message: string
  raw?: any
}
type SqlBuilderFilterLogic = 'and' | 'or'
type SqlBuilderFilter = {
  id: string
  type?: 'rule' | 'group'
  field: string
  operator: string
  value: string
  logic?: SqlBuilderFilterLogic
  children?: SqlBuilderFilter[]
}
type SqlBuilderMetricItem = {
  id: string
  field: string
  metric: string
  aggregation: string
  alias: string
  filterLogic: SqlBuilderFilterLogic
  filters: SqlBuilderFilter[]
}
type AnalysisModel = 'event' | 'retention' | 'funnel' | 'distribution' | 'interval' | 'path' | 'revenue' | 'attribution' | 'ranking'
type RetentionEventTarget = 'initial' | 'return'
type IntervalEventTarget = 'start' | 'end'
type SqlBuilderFunnelStep = {
  id: string
  event: string
  alias: string
  filterLogic: SqlBuilderFilterLogic
  filters: SqlBuilderFilter[]
  relatedProperty: string
}
type SqlBuilderAggregation = 'count' | 'sum' | 'avg' | 'max' | 'min' | 'count_distinct'
const RETENTION_ANALYSIS_CONTEXT_CONTENT = '以某段时间做过初始事件的用户为样本，查看在指定日期后用户进行回访事件的留存情况'
type SqlBuilderRetentionConfig = {
  entityField: string
  initialEvent: string
  initialEventAlias: string
  initialEventFilterLogic: SqlBuilderFilterLogic
  initialEventFilters: SqlBuilderFilter[]
  returnEvent: string
  returnEventAlias: string
  returnEventFilterLogic: SqlBuilderFilterLogic
  returnEventFilters: SqlBuilderFilter[]
  simultaneous: {
    enabled: boolean
    event: string
    aggregation: SqlBuilderAggregation
    metricField: string
  }
  relatedProperty: {
    enabled: boolean
    initialProperty: string
    returnProperty: string
    simultaneousProperty: string
    asGroup: boolean
  }
}
type SqlBuilderFunnelConfig = {
  entityField: string
  steps: SqlBuilderFunnelStep[]
  window: FunnelWindowConfig
  relatedPropertyEnabled: boolean
}
type SqlBuilderDistributionConfig = {
  entityField: string
  event: string
  eventFilterLogic: SqlBuilderFilterLogic
  eventFilters: SqlBuilderFilter[]
  metric: DistributionMetricConfig
  interval: DistributionIntervalConfig
  simultaneous: {
    enabled: boolean
    event: string
    aggregation: SqlBuilderAggregation
    metricField: string
  }
}
type SqlBuilderIntervalConfig = {
  entityField: string
  startEvent: string
  startEventFilterLogic: SqlBuilderFilterLogic
  startEventFilters: SqlBuilderFilter[]
  endEvent: string
  endEventFilterLogic: SqlBuilderFilterLogic
  endEventFilters: SqlBuilderFilter[]
  relatedProperty: {
    enabled: boolean
    startProperty: string
    endProperty: string
  }
  limitSeconds: number
}
type SqlBuilderPathConfig = {
  events: PathAnalysisEvent[]
  initialEvent: string
  sessionGapSeconds: number
}
type SqlBuilderRevenueConfig = {
  entityField: string
  initialEvent: string
  paymentEvent: string
  metric: RevenueMetricConfig
  costEnabled: boolean
  costField: string
  observationDays: number
}
type SqlBuilderAttributionEvent = {
  id: string
  event: string
  filterLogic: SqlBuilderFilterLogic
  filters: SqlBuilderFilter[]
}
type SqlBuilderAttributionConfig = {
  entityField: string
  method: AttributionMethod
  window: AttributionWindowConfig
  targetEvent: string
  targetEventFilterLogic: SqlBuilderFilterLogic
  targetEventFilters: SqlBuilderFilter[]
  targetMetric: {
    aggregation: SqlBuilderAggregation
    metricField: string
  }
  includeDirect: boolean
  events: SqlBuilderAttributionEvent[]
}
type SqlBuilderRankingMetric = {
  id: string
  event: string
  alias: string
  aggregation: SqlBuilderAggregation
  metricField: string
  direction: 'asc' | 'desc'
}
type SqlBuilderRankingConfig = {
  entityField: string
  metric: SqlBuilderRankingMetric
  tieHandling: 'default' | 'skip' | 'dense'
  simultaneousMetrics: SqlBuilderRankingMetric[]
  simultaneousProperties: string[]
}
type SqlBuilderCalculatedMetricItem = {
  id: string
  decimalPlaces: number
  alias: string
  tokens: FormulaToken[]
  pendingMetricId: string
  pendingEventField: string
  pendingAggregation: string
  pendingMetricField: string
  formulaCursorIndex: number
}
type BuilderSqlDialect = 'mysql' | 'postgres' | 'generic'
type SchemaFieldOption = {
  label: string
  value: string
  table: string
  tableId?: number | string
  tableLabel?: string
  tableReferenceLabel?: string
  tableRole?: string
  fieldRole?: string
  field: string
  displayName?: string
  type?: string
  comment?: string
  tableComment?: string
  category?: string
  semanticType?: string
  sourceField?: string
  jsonPath?: string
  expression?: string
  isJsonSubfield?: boolean
  kind?: string
  eventName?: string
  eventCategory?: string
  eventDescription?: string
  eventTable?: string
  eventNameField?: string
  propertyName?: string
  propertyType?: string
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
  pivotDateParameterType: SQL_EDITOR_DATE_PARAMETER_TYPE as DashboardDateParameterType,
  pivotGroupValueMode: 'all' as PivotGroupValueMode,
  pivotGroupValues: [] as string[],
  mcpServerId: '',
  mcpTool: '',
  mcpArgumentsObject: {} as Record<string, any>,
  mcpArgumentsText: '{}',
  mcpResultPath: '',
  mcpKeyField: '',
  mcpValueField: '',
})
const donutSeriesFields = ref<string[]>([])
const sqlBuilder = reactive({
  activeTab: 'builder',
  analysisModel: 'event' as AnalysisModel,
  timeField: SQL_EDITOR_TIME_FIELD,
  timeGrain: SQL_EDITOR_TIME_GRAIN,
  timeRange: 'expression',
  timeCustomRange: [] as string[],
  dateExpressionPickerEnabled: true,
  metricDateExpressionEnabled: false,
  timeExpression: defaultDashboardDateExpression(),
  metricItems: [] as SqlBuilderMetricItem[],
  calculatedMetrics: [] as SqlBuilderCalculatedMetricItem[],
  groups: [] as string[],
  globalFilters: [] as SqlBuilderFilter[],
  globalFilterLogic: 'and' as SqlBuilderFilterLogic,
  approximate: false,
  retention: {
    entityField: '',
    initialEvent: '',
    initialEventAlias: '',
    initialEventFilterLogic: 'and',
    initialEventFilters: [],
    returnEvent: '',
    returnEventAlias: '',
    returnEventFilterLogic: 'and',
    returnEventFilters: [],
    simultaneous: {
      enabled: false,
      event: '',
      aggregation: 'count',
      metricField: '',
    },
    relatedProperty: {
      enabled: false,
      initialProperty: '',
      returnProperty: '',
      simultaneousProperty: '',
      asGroup: false,
    },
  } as SqlBuilderRetentionConfig,
  funnel: {
    entityField: '',
    steps: [],
    window: { ...DEFAULT_FUNNEL_WINDOW },
    relatedPropertyEnabled: false,
  } as SqlBuilderFunnelConfig,
  distribution: {
    entityField: '',
    event: '',
    eventFilterLogic: 'and',
    eventFilters: [],
    metric: {
      kind: 'count',
      field: '',
      aggregation: 'sum',
    },
    interval: {
      mode: 'discrete',
      customBounds: [],
    },
    simultaneous: {
      enabled: false,
      event: '',
      aggregation: 'count',
      metricField: '',
    },
  } as SqlBuilderDistributionConfig,
  interval: {
    entityField: '',
    startEvent: '',
    startEventFilterLogic: 'and',
    startEventFilters: [],
    endEvent: '',
    endEventFilterLogic: 'and',
    endEventFilters: [],
    relatedProperty: {
      enabled: false,
      startProperty: '',
      endProperty: '',
    },
    limitSeconds: DEFAULT_INTERVAL_LIMIT_SECONDS,
  } as SqlBuilderIntervalConfig,
  path: {
    events: [{ id: 'path-event-initial', event: '', splitProperties: [] }],
    initialEvent: '',
    sessionGapSeconds: DEFAULT_PATH_SESSION_GAP_SECONDS,
  } as SqlBuilderPathConfig,
  revenue: {
    entityField: '',
    initialEvent: '',
    paymentEvent: '',
    metric: { method: 'count', field: '' },
    costEnabled: false,
    costField: '',
    observationDays: DEFAULT_REVENUE_OBSERVATION_DAYS,
  } as SqlBuilderRevenueConfig,
  attribution: {
    entityField: '',
    method: 'linear',
    window: { ...DEFAULT_ATTRIBUTION_WINDOW },
    targetEvent: '',
    targetEventFilterLogic: 'and',
    targetEventFilters: [],
    targetMetric: {
      aggregation: 'count',
      metricField: '',
    },
    includeDirect: true,
    events: [],
  } as SqlBuilderAttributionConfig,
  ranking: {
    entityField: '',
    metric: {
      id: 'ranking-primary-metric',
      event: '',
      alias: '',
      aggregation: 'count',
      metricField: '',
      direction: 'desc',
    },
    tieHandling: 'default',
    simultaneousMetrics: [],
    simultaneousProperties: [],
  } as SqlBuilderRankingConfig,
})
const retentionFilterExpanded = reactive<Record<RetentionEventTarget, boolean>>({
  initial: false,
  return: false,
})
const retentionAliasEditing = reactive<Record<RetentionEventTarget, boolean>>({
  initial: false,
  return: false,
})
const retentionAliasDraft = reactive<Record<RetentionEventTarget, string>>({
  initial: '',
  return: '',
})
const funnelFilterExpanded = reactive<Record<string, boolean>>({})
const funnelAliasEditing = reactive<Record<string, boolean>>({})
const funnelAliasDraft = reactive<Record<string, string>>({})
const distributionFilterExpanded = ref(false)
const intervalFilterExpanded = reactive<Record<IntervalEventTarget, boolean>>({
  start: false,
  end: false,
})
const attributionTargetFilterExpanded = ref(false)
const attributionEventFilterExpanded = reactive<Record<string, boolean>>({})
const builderAgentAdvice = reactive({
  visible: false,
  severity: '',
  intent: '',
  message: '',
  advice: '',
  issues: [] as string[],
  suggestions: [] as string[],
  raw: '',
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
const builderLoading = ref(false)
const loadingText = ref('')
const mcpServersLoading = ref(false)
const mcpServersError = ref('')
const mcpServers = ref<ExternalMcpServerInfo[]>([])
const mcpToolsLoading = ref(false)
const mcpToolsError = ref('')
const mcpTools = ref<ExternalMcpToolInfo[]>([])
const mcpFilterOptionsLoading = ref(false)
const mcpFilterOptions = ref<Record<string, string[]>>({})
const schemaLoading = ref(false)
const schemaTables = ref<any[]>([])
const trackingConfig = ref<any>(null)
const trackingEventCatalog = ref<any>(null)
const datasourceInfo = ref<any>(null)
const executionDatasourceOptions = ref<ExecutionDatasourceOption[]>([])
const selectedExecutionDatasourceId = ref<number | null>(null)
const executionDatasourceError = ref('')
const activeFormulaMetricId = ref('')
const activeFormulaAtomicMetricKey = ref('')
const previewVersion = ref(0)
const lastPreviewSql = ref('')
const lastPreviewSignature = ref('')
const initializedPivotGroupValueField = ref('')
const dateExpressionConfigError = ref('')
const PIVOT_GROUP_SELECT_ALL_VALUE = '__dashboard_pivot_group_select_all__'
const PIVOT_GROUP_SELECT_NONE_VALUE = '__dashboard_pivot_group_select_none__'
let builderSchemaLoadSeq = 0

async function setLoadingPhase(text: string) {
  builderLoading.value = true
  loadingText.value = text
  await nextTick()
  await new Promise((resolve) => window.setTimeout(resolve, 0))
}

function clearBuilderLoading() {
  builderLoading.value = false
  loadingText.value = ''
}

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
  if (
    !isExternalSnapshotChart(viewInfo)
    && (viewInfo?.sql || viewInfo?.datasource)
    && !sourceTypes.includes('sql')
  ) {
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
  { label: 'grouped_column', value: 'grouped_column' },
  { label: 'bar', value: 'bar' },
  { label: 'line', value: 'line' },
  { label: 'area', value: 'area' },
  { label: 'pie', value: 'pie' },
  { label: 'donut', value: 'donut' },
  { label: 'funnel', value: 'funnel' },
  { label: 'heatmap', value: 'heatmap' },
  { label: 'scatter', value: 'scatter' },
  { label: 'sankey', value: 'sankey' },
  { label: 'treemap', value: 'treemap' },
]

const builderTimeGrainOptions = [
  { label: '按天', value: 'day' },
  { label: '按周', value: 'week' },
  { label: '按月', value: 'month' },
  { label: '不按时间', value: 'none' },
]

const builderAggregationOptions: Array<{ label: string; value: SqlBuilderAggregation }> = [
  { label: '总次数', value: 'count' },
  { label: '求和', value: 'sum' },
  { label: '平均值', value: 'avg' },
  { label: '最大值', value: 'max' },
  { label: '最小值', value: 'min' },
  { label: '去重数', value: 'count_distinct' },
]

const builderCalculationOperatorOptions: Array<{ label: string; value: FormulaOperator }> = [
  { label: '+', value: '+' },
  { label: '-', value: '-' },
  { label: '*', value: '*' },
  { label: '/', value: '/' },
]
const formulaNumberKeys = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '.']
const formulaParenKeys: Array<'(' | ')'> = ['(', ')']

const builderFilterOperatorOptions = [
  { label: '等于', value: 'eq' },
  { label: '不等于', value: 'ne' },
  { label: '包含', value: 'contains' },
  { label: '大于', value: 'gt' },
  { label: '小于', value: 'lt' },
  { label: '范围', value: 'between' },
  { label: '为空', value: 'is_null' },
  { label: '非空', value: 'is_not_null' },
]

const hasSqlSource = computed(() => form.sourceTypes.includes('sql'))
const hasMcpSource = computed(() => form.sourceTypes.includes('external_mcp'))
const sqlSourceEnabled = computed({
  get: () => hasSqlSource.value,
  set: (enabled: boolean) => setSourceTypeEnabled('sql', enabled),
})
const mcpSourceEnabled = computed({
  get: () => hasMcpSource.value,
  set: (enabled: boolean) => setSourceTypeEnabled('external_mcp', enabled),
})
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
function schemaTableName(table: any) {
  return table?.table_name || table?.tableName || table?.name || table?.table || ''
}

function schemaTableLabel(table: any) {
  const tableComment = table?.custom_comment || table?.customComment || table?.table_comment || table?.tableComment || table?.comment || ''
  const tableDisplayName = table?.display_name || table?.displayName || ''
  return tableDisplayName || tableComment || schemaTableName(table)
}

function eventDetailTableLabel(eventTable: string) {
  const table = (schemaTables.value || []).find((item: any) => schemaTableName(item) === eventTable)
  return table ? schemaTableLabel(table) : eventTable
}

const schemaFieldOptions = computed<SchemaFieldOption[]>(() => {
  const options: SchemaFieldOption[] = []
  const seen = new Set<string>()
  ;(schemaTables.value || []).forEach((table: any) => {
    const tableName = schemaTableName(table)
    if (!tableName) return
    const tableComment = table?.custom_comment || table?.customComment || table?.table_comment || table?.tableComment || table?.comment || ''
    const tableLabel = schemaTableLabel(table)
    const tableRole = table?.table_role || table?.tableRole || table?.role || ''
    ;(table?.fields || []).forEach((field: any) => {
      const fieldName = field?.field_name || field?.fieldName || field?.name || field?.column_name || field?.columnName || ''
      if (!fieldName) return
      const value = tableName ? `${tableName}.${fieldName}` : fieldName
      if (seen.has(value)) return
      seen.add(value)
      const type = field?.field_type || field?.fieldType || field?.type || ''
      const semanticType = field?.semantic_type || field?.semanticType || ''
      const comment = field?.custom_comment || field?.customComment || field?.field_comment || field?.fieldComment || field?.comment || ''
      const displayName = field?.display_name || field?.displayName || ''
      const sourceField = field?.source_field || field?.sourceField || ''
      const jsonPath = field?.json_path || field?.jsonPath || ''
      options.push({
        label: displayName || fieldName,
        value,
        table: tableName,
        tableId: table?.id,
        tableLabel,
        tableRole,
        fieldRole: field?.field_role || field?.fieldRole || '',
        field: fieldName,
        displayName,
        type,
        comment,
        tableComment,
        category: field?.category || builderFieldCategory(type, fieldName),
        semanticType,
        sourceField,
        jsonPath,
        expression: field?.expression || '',
        isJsonSubfield: field?.is_json_subfield || field?.isJsonSubfield || false,
      })
    })
  })
  return options
})
const eventFieldScope = computed(() => resolveDashboardBuilderEventScope({
  config: trackingConfig.value,
  datasourceId: selectedExecutionDatasourceId.value,
  tableNames: (schemaTables.value || []).map(schemaTableName).filter(Boolean),
}))
const eventScopedSchemaFieldOptions = computed(() =>
  getEventScopedFields(schemaFieldOptions.value, eventFieldScope.value)
)
const builderFieldOptions = computed(() => eventScopedSchemaFieldOptions.value.filter(isSelectableFieldOption))
const eventUserPropertyOptions = computed(() => {
  if (eventFieldScope.value.status !== 'active') {
    return []
  }
  return builderFieldOptions.value.filter((option) =>
    isEventUserPropertyOption(option, eventFieldScope.value.defaultEventTable)
  )
})
const trackingEventCatalogOptions = computed<SchemaFieldOption[]>(() => {
  const groups = Array.isArray(trackingEventCatalog.value?.groups) ? trackingEventCatalog.value.groups : []
  return groups.flatMap((group: any) => {
    const events = Array.isArray(group?.events) ? group.events : []
    return events.map((event: any) => {
      const eventTable = event?.event_table || event?.eventTable || trackingEventCatalog.value?.event_table || trackingEventCatalog.value?.eventTable || ''
      const eventNameField = event?.event_name_field || event?.eventNameField || trackingEventCatalog.value?.event_name_field || trackingEventCatalog.value?.eventNameField || ''
      const eventName = event?.event_name || event?.eventName || ''
      const displayName = event?.display_name || event?.displayName || eventName
      const category = event?.category || group?.label || '默认分组'
      const tableReferenceLabel = eventDetailTableLabel(eventTable)
      return {
        label: displayName,
        value: event?.value || `tracking-event:${eventTable}.${eventNameField}:${eventName}`,
        table: eventTable,
        tableLabel: '事件参数对照',
        tableReferenceLabel,
        field: eventNameField,
        displayName,
        type: '事件',
        comment: event?.description || '',
        tableComment: '事件参数对照',
        category,
        kind: 'tracking-event',
        eventName,
        eventCategory: category,
        eventDescription: event?.description || '',
        eventTable,
        eventNameField,
      }
    })
  }).filter((option: SchemaFieldOption) => (
    eventFieldScope.value.status === 'active'
    && option.table === eventFieldScope.value.defaultEventTable
  ))
})
const trackingEventPropertyOptions = computed<SchemaFieldOption[]>(() => {
  const groups = Array.isArray(trackingEventCatalog.value?.groups) ? trackingEventCatalog.value.groups : []
  return groups.flatMap((group: any) => {
    const events = Array.isArray(group?.events) ? group.events : []
    return events.flatMap((event: any) => {
      const eventTable = event?.event_table || event?.eventTable || trackingEventCatalog.value?.event_table || trackingEventCatalog.value?.eventTable || ''
      const eventNameField = event?.event_name_field || event?.eventNameField || trackingEventCatalog.value?.event_name_field || trackingEventCatalog.value?.eventNameField || ''
      const eventName = event?.event_name || event?.eventName || ''
      const eventDisplayName = event?.display_name || event?.displayName || eventName
      const tableReferenceLabel = eventDetailTableLabel(eventTable)
      const properties = Array.isArray(event?.properties) ? event.properties : []
      return properties.map((property: any) => {
        const propertyName = property?.property_name || property?.propertyName || property?.field_name || property?.fieldName || ''
        const displayName = property?.display_name || property?.displayName || property?.property_display_name || property?.propertyDisplayName || propertyName
        const sourceField = property?.source_field || property?.sourceField || ''
        const jsonPath = property?.json_path || property?.jsonPath || ''
        const propertyType = property?.property_type || property?.propertyType || property?.type || ''
        return {
          label: displayName,
          value: property?.value || `tracking-property:${eventTable}.${eventNameField}:${eventName}:${propertyName}`,
          table: eventTable,
          tableLabel: `${eventDisplayName} 参数`,
          tableReferenceLabel,
          field: propertyName,
          displayName,
        type: propertyType || '事件参数',
        comment: property?.description || '',
        tableComment: '事件参数对照',
        category: propertyType || '事件参数',
        semanticType: propertyType,
        sourceField,
          jsonPath,
          isJsonSubfield: Boolean(sourceField || jsonPath),
          kind: 'tracking-property',
          eventName,
          eventCategory: event?.category || group?.label || '默认分组',
          eventTable,
          eventNameField,
          propertyName,
          propertyType,
        }
      })
    })
  }).filter((option: SchemaFieldOption) => (
    eventFieldScope.value.status === 'active'
    && option.table === eventFieldScope.value.defaultEventTable
  ))
})
const trackingEventPropertyOptionsByEvent = computed(() => {
  const groups = new Map<string, SchemaFieldOption[]>()
  trackingEventPropertyOptions.value.forEach((option) => {
    const key = option.eventName || ''
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)?.push(option)
  })
  return groups
})
const fieldOptionIndex = computed(() =>
  createFieldOptionIndex({
    trackingEventOptions: trackingEventCatalogOptions.value,
    trackingEventPropertyOptions: trackingEventPropertyOptions.value,
    schemaFieldOptions: schemaFieldOptions.value,
  })
)
const hasTrackingEventCatalog = computed(() =>
  Boolean(
    eventFieldScope.value.status === 'active'
    && trackingEventCatalog.value
    && Array.isArray(trackingEventCatalog.value?.groups)
  )
)
const hasTrackingEventOptions = computed(() => trackingEventCatalogOptions.value.length > 0)
const usesTrackingEventPicker = computed(() => hasTrackingEventCatalog.value || hasTrackingEventOptions.value)
const fallbackAnalysisFieldOptions = computed(() =>
  schemaFieldOptions.value.length ? schemaFieldOptions.value : toFieldOptions(sourcePreview.fields)
)
const analysisFieldOptions = computed(() => {
  if (eventFieldScope.value.mode === 'event') {
    return eventFieldScope.value.status === 'active' ? trackingEventCatalogOptions.value : []
  }
  return fallbackAnalysisFieldOptions.value
})
const analysisFieldPickerMode = computed(() => usesTrackingEventPicker.value ? 'tracking-event' : 'property')
const formulaFieldPickerPlaceholder = computed(() => usesTrackingEventPicker.value ? '选择事件' : '选择字段')
const analysisModelOptions = [
  { label: '事件分析', value: 'event' as AnalysisModel },
  { label: '留存分析', value: 'retention' as AnalysisModel },
  { label: '漏斗分析', value: 'funnel' as AnalysisModel },
  { label: '分布分析', value: 'distribution' as AnalysisModel },
  { label: '间隔分析', value: 'interval' as AnalysisModel },
  { label: '路径分析', value: 'path' as AnalysisModel },
  { label: '收入分析', value: 'revenue' as AnalysisModel },
  { label: '归因分析', value: 'attribution' as AnalysisModel },
  { label: '排行榜', value: 'ranking' as AnalysisModel },
]
const isRetentionAnalysis = computed(() => sqlBuilder.analysisModel === 'retention')
const isFunnelAnalysis = computed(() => sqlBuilder.analysisModel === 'funnel')
const isDistributionAnalysis = computed(() => sqlBuilder.analysisModel === 'distribution')
const isIntervalAnalysis = computed(() => sqlBuilder.analysisModel === 'interval')
const isPathAnalysis = computed(() => sqlBuilder.analysisModel === 'path')
const isRevenueAnalysis = computed(() => sqlBuilder.analysisModel === 'revenue')
const isAttributionAnalysis = computed(() => sqlBuilder.analysisModel === 'attribution')
const isRankingAnalysis = computed(() => sqlBuilder.analysisModel === 'ranking')
const retentionEntityFieldOptions = computed(() => builderFieldOptions.value)
const retentionEventOptions = computed(() => trackingEventCatalogOptions.value)
const funnelEntityFieldOptions = computed(() => builderFieldOptions.value)
const funnelEventOptions = computed(() => trackingEventCatalogOptions.value)
const distributionEntityFieldOptions = computed(() => builderFieldOptions.value)
const distributionEventOptions = computed(() => trackingEventCatalogOptions.value)
const distributionEventPropertyOptions = computed(() => eventFilterFieldOptions(sqlBuilder.distribution.event))
const distributionEventLabel = computed(() => (
  fieldOptionByValue(sqlBuilder.distribution.event)?.displayName
  || fieldOptionByValue(sqlBuilder.distribution.event)?.label
  || '参与事件'
))
const intervalEntityFieldOptions = computed(() => builderFieldOptions.value)
const intervalEventOptions = computed(() => trackingEventCatalogOptions.value)
const intervalStartPropertyOptions = computed(() => eventFilterFieldOptions(sqlBuilder.interval.startEvent))
const intervalEndPropertyOptions = computed(() => {
  const options = eventFilterFieldOptions(sqlBuilder.interval.endEvent)
  const startOption = fieldOptionByValue(sqlBuilder.interval.relatedProperty.startProperty)
  if (!startOption) return options
  const startType = intervalPropertyTypeFamily(startOption)
  return startType ? options.filter((option) => intervalPropertyTypeFamily(option) === startType) : options
})
const pathEventOptions = computed(() => trackingEventCatalogOptions.value)
const pathEventPropertyOptions = (eventValue: string) => eventFilterFieldOptions(eventValue)
const revenueEntityFieldOptions = computed(() => builderFieldOptions.value)
const revenueEventOptions = computed(() => trackingEventCatalogOptions.value)
const revenuePaymentPropertyOptions = computed(() => eventFilterFieldOptions(sqlBuilder.revenue.paymentEvent))
const revenueNumericPropertyOptions = computed(() => revenuePaymentPropertyOptions.value.filter(isNumericFieldOption))
const pathInitialEventOptions = computed(() => sqlBuilder.path.events
  .filter((item) => item.event)
  .map((item) => {
    const option = fieldOptionByValue(item.event)
    return {
      value: item.event,
      label: option?.displayName || option?.label || item.event,
      field: option?.field || item.event,
      table: option?.table || '',
    }
  }))
const attributionEntityFieldOptions = computed(() => builderFieldOptions.value)
const attributionEventOptions = computed(() => trackingEventCatalogOptions.value)
const attributionTargetMetricFieldOptions = computed(() => metricMeasureFieldOptions({
  field: sqlBuilder.attribution.targetEvent,
  aggregation: sqlBuilder.attribution.targetMetric.aggregation,
}))
const rankingEntityFieldOptions = computed(() => builderFieldOptions.value)
const rankingEventOptions = computed(() => trackingEventCatalogOptions.value)
const rankingMetricFieldOptions = (metric: SqlBuilderRankingMetric) => metricMeasureFieldOptions({
  field: metric.event,
  aggregation: metric.aggregation,
})
const builderMetricOptions = computed(() =>
  sqlBuilder.metricItems.map((item, index) => ({
    label: metricOutputAlias(item, index),
    value: item.id,
  }))
)
const fieldOptions = computed(() => toFieldOptions(sourcePreview.fields))
const seriesFieldOptions = computed(() => {
  const excluded = new Set(form.y)
  if (!isRadialPartitionChartType(form.chartType) && form.x) {
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
const pivotGroupFieldOptions = computed(() => {
  const options = new Map<string, string>()
  inferredPivotDimensions().forEach((dimension) => {
    if (dimension.field) {
      options.set(dimension.field, dimension.label || dimension.field)
    }
  })
  ;[form.pivotGroupField, effectiveSeriesField.value]
    .filter((field) => field && sourcePreview.fields.includes(field))
    .forEach((field) => options.set(field, field))
  return Array.from(options.entries()).map(([value, label]) => ({ value, label }))
})
const canUseSqlEditor = computed(() => props.canEditSql === true)
const canRunPreview = computed(() => Boolean(selectedExecutionDatasourceId.value) && hasSqlSource.value && canUseSqlEditor.value)
const canRunEditorPreview = computed(() => {
  if (!hasSqlSource.value && !hasMcpSource.value) {
    return false
  }
  if (hasSqlSource.value && !canUseSqlEditor.value) {
    return false
  }
  if (hasSqlSource.value && !selectedExecutionDatasourceId.value) {
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
const showXAxis = computed(() =>
  !['table', 'metric'].includes(form.chartType) && !isRadialPartitionChartType(form.chartType)
)
const showSeries = computed(() => !['table', 'metric', 'funnel', 'scatter'].includes(form.chartType))
const supportsInsightConfig = computed(() => !['table', 'metric'].includes(form.chartType))
const supportsPivotConfig = computed(() => hasSqlSource.value && !hasMcpSource.value && !['table', 'metric'].includes(form.chartType))
const dateExpressionEnabled = computed(
  () => hasSqlSource.value && sqlBuilder.dateExpressionPickerEnabled === true && shouldUseDashboardDateParameters()
)

function shouldUseDashboardDateParameters() {
  return Boolean(sqlBuilder.timeField)
}

function syncDashboardDateParameterUsage() {
  const enabled = shouldUseDashboardDateParameters()
  sqlBuilder.dateExpressionPickerEnabled = enabled
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  dateExpressionConfigError.value = ''
}
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
  if (form.chartType === 'donut') {
    return form.y.length === 1 ? form.y : []
  }
  return form.y
})
const activePivotGroupValueField = computed(() =>
  form.chartType === 'pie' ? effectiveSeriesField.value || form.x : effectiveSeriesField.value
)
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
  return field && visiblePreviewFields([field], previewDisplayData.value).includes(field) ? [field] : []
})
const showPivotGroupValueConfig = computed(
  () =>
    supportsPivotConfig.value &&
    form.pivotEnabled &&
    Boolean(activePivotGroupValueField.value) &&
    (sourceHasPivotGroupValues.value || form.pivotGroupValues.length > 0)
)
const pivotGroupValueOptions = computed(() => {
  const field = activePivotGroupValueField.value
  if (!field) {
    return []
  }
  const counts = collectPivotGroupValueCounts(field)
  return Array.from(counts.keys())
    .map((value) => ({
      label: value,
      value,
    }))
    .sort((a, b) => a.value.localeCompare(b.value, undefined, { numeric: true, sensitivity: 'base' }))
})
const previewDisplayData = computed(() => {
  let rows = preview.data
  const seriesField = form.chartType === 'pie' ? effectiveSeriesField.value || form.x : effectiveSeriesField.value
  const previewHasSeriesField = !seriesField || visiblePreviewFields([seriesField], rows).includes(seriesField)
  if (!previewHasSeriesField && visiblePreviewFields([seriesField], sourcePreview.data).includes(seriesField)) {
    rows = sourcePreview.data
  }
  if (!showPivotGroupValueConfig.value || !previewHasPivotGroupField.value) {
    return rows
  }
  if (form.pivotGroupValueMode === 'all') {
    return rows
  }
  const field = activePivotGroupValueField.value
  const selected = new Set(unique(form.pivotGroupValues.map(normalizePivotGroupValue)))
  if (!field || selected.size === 0) {
    return []
  }
  return rows.filter((row) => selected.has(normalizePivotGroupValue(row?.[field])))
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
    } catch {
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
  return fields.map((field) => ({
    label: field,
    value: field,
    table: '',
    tableRole: '',
    field,
  }))
}

function builderFieldCategory(type = '', field = '') {
  const option = { label: field, value: field, table: '', field, type }
  if (isTimeFieldOption(option)) return 'time'
  if (isNumericFieldOption(option)) return 'number'
  const text = `${type} ${field}`.toLowerCase()
  if (/date|time|timestamp|dt|day|日期|时间/.test(text)) return 'time'
  if (/int|decimal|double|float|numeric|number|amount|price|count|rate|ratio|score|value/.test(text)) return 'number'
  return 'text'
}

function nodeId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyBuilderFilter(): SqlBuilderFilter {
  return {
    id: nodeId('filter'),
    type: 'rule',
    field: '',
    operator: 'eq',
    value: '',
    logic: 'and',
  }
}

function emptyMetricItem(): SqlBuilderMetricItem {
  return {
    id: nodeId('metric'),
    field: '',
    metric: '',
    aggregation: 'count',
    alias: '',
    filterLogic: 'and',
    filters: [],
  }
}

function createRankingMetric(id = nodeId('ranking-metric')): SqlBuilderRankingMetric {
  return {
    id,
    event: '',
    alias: '',
    aggregation: 'count',
    metricField: '',
    direction: 'desc',
  }
}

function serializeRankingMetric(metric: SqlBuilderRankingMetric) {
  return {
    id: metric.id,
    event: metric.event,
    alias: metric.alias.trim(),
    aggregation: metric.aggregation,
    metricField: metric.aggregation === 'count' ? '' : metric.metricField,
    direction: metric.direction,
  }
}

function restoreRankingMetric(value: any, fallbackId: string) {
  const metric = createRankingMetric(
    typeof value?.id === 'string' && value.id ? value.id : fallbackId,
  )
  metric.event = typeof value?.event === 'string' ? value.event : ''
  metric.alias = typeof value?.alias === 'string' ? value.alias : ''
  metric.aggregation = builderAggregationOptions.some((option) => option.value === value?.aggregation)
    ? value.aggregation
    : 'count'
  metric.metricField = metric.aggregation === 'count'
    ? ''
    : typeof value?.metricField === 'string' ? value.metricField : ''
  metric.direction = value?.direction === 'asc' ? 'asc' : 'desc'
  return metric
}

function emptyCalculatedMetricItem(): SqlBuilderCalculatedMetricItem {
  return {
    id: nodeId('calc-metric'),
    decimalPlaces: 2,
    alias: '',
    tokens: [],
    pendingMetricId: '',
    pendingEventField: '',
    pendingAggregation: 'count',
    pendingMetricField: '',
    formulaCursorIndex: 0,
  }
}

function addMetricItem() {
  const item = emptyMetricItem()
  const numericField = eventScopedSchemaFieldOptions.value.find(isNumericFieldOption)
  item.field = analysisFieldOptions.value[0]?.value || ''
  item.metric = numericField?.value || item.field
  item.alias = `指标${sqlBuilder.metricItems.length + 1}`
  sqlBuilder.metricItems.push(item)
}

function removeMetricItem(index: number) {
  const [removed] = sqlBuilder.metricItems.splice(index, 1)
  if (!removed) {
    return
  }
  sqlBuilder.calculatedMetrics.forEach((item) => {
    item.tokens = item.tokens.filter((token) => token.type !== 'metric' || token.metricId !== removed.id)
    if (item.pendingMetricId === removed.id) {
      item.pendingMetricId = ''
    }
  })
}

function addCalculatedMetricItem() {
  const item = emptyCalculatedMetricItem()
  item.pendingEventField = analysisFieldOptions.value[0]?.value || ''
  item.pendingMetricField = defaultMetricFieldForEvent(item.pendingEventField)
  item.alias = sqlBuilder.calculatedMetrics.length ? `自定义指标${sqlBuilder.calculatedMetrics.length + 1}` : '自定义指标'
  sqlBuilder.calculatedMetrics.push(item)
  activeFormulaMetricId.value = item.id
}

function removeCalculatedMetricItem(index: number) {
  sqlBuilder.calculatedMetrics.splice(index, 1)
}

function metricTitle(item: SqlBuilderMetricItem, index: number) {
  const field = schemaFieldOptions.value.find((option) => option.value === item.field)
  const aggregation = builderAggregationOptions.find((option) => option.value === item.aggregation)
  return `${field?.displayName || field?.label || field?.field || `指标${index + 1}`}.${aggregation?.label || '指标'}`
}

function metricOutputAlias(item: SqlBuilderMetricItem, index: number) {
  return sqlAlias(item.alias || metricTitle(item, index), `指标${index + 1}`)
}

function calculatedMetricTitle(item: SqlBuilderCalculatedMetricItem, index: number) {
  return item.alias || formulaTokensToText(item.tokens, builderMetricOptions.value) || `自定义指标${index + 1}`
}

function calculatedMetricFormulaText(item: SqlBuilderCalculatedMetricItem) {
  return formulaTokensToText(item.tokens, builderMetricOptions.value) || '直接输入运算符或点击选择事件'
}

function calculatedMetricValidation(item: SqlBuilderCalculatedMetricItem) {
  return validateFormulaTokens(item.tokens, builderMetricOptions.value)
}

function appendFormulaToken(item: SqlBuilderCalculatedMetricItem, token: FormulaToken) {
  const cursorIndex = Number.isFinite(Number(item.formulaCursorIndex))
    ? Number(item.formulaCursorIndex)
    : item.tokens.length
  item.tokens = insertFormulaTokenAt(item.tokens, cursorIndex, token)
  item.formulaCursorIndex = Math.min(cursorIndex + 1, item.tokens.length)
  activeFormulaMetricId.value = item.id
  activeFormulaAtomicMetricKey.value = ''
}

function appendFormulaOperator(item: SqlBuilderCalculatedMetricItem, value: FormulaOperator) {
  appendFormulaToken(item, { type: 'operator', value })
}

function appendFormulaParen(item: SqlBuilderCalculatedMetricItem, value: '(' | ')') {
  appendFormulaToken(item, { type: 'paren', value })
}

function formulaAtomicMetricLabel(metric: FormulaAtomicMetric) {
  const field = fieldOptionByValue(metric.field)
  const aggregation = builderAggregationOptions.find((option) => option.value === metric.aggregation)
  const fieldLabel = field?.displayName || field?.label || field?.field || metric.field || '事件'
  return `${fieldLabel}.${aggregation?.label || '指标'}`
}

function formulaAtomicMetricKey(item: SqlBuilderCalculatedMetricItem, tokenIndex: number) {
  return `${item.id}:${tokenIndex}`
}

function syncFormulaAtomicMetric(metric: FormulaAtomicMetric, resetMetric = false) {
  metric.aggregation = metric.aggregation || 'count'
  if (metric.aggregation === 'count') {
    metric.metric = metric.field
  } else if (
    resetMetric ||
    !metric.metric ||
    metric.metric === metric.field ||
    fieldOptionByValue(metric.metric)?.kind === 'tracking-event' ||
    !optionExists(metric.metric, metricMeasureFieldOptions(metric))
  ) {
    metric.metric = defaultMetricFieldForEvent(metric.field)
  }
  const display = normalizeFormulaAtomicMetricDisplay(metric, {
    label: formulaAtomicMetricLabel(metric),
    alias: sqlAlias(formulaAtomicMetricLabel(metric), `事件指标${Date.now()}`),
  })
  metric.label = display.label
  metric.alias = display.alias
}

function startEditFormulaAtomicMetric(item: SqlBuilderCalculatedMetricItem, tokenIndex: number, metric: FormulaAtomicMetric) {
  setFormulaCursor(item, tokenIndex + 1)
  syncFormulaAtomicMetric(metric)
  activeFormulaMetricId.value = item.id
  activeFormulaAtomicMetricKey.value = formulaAtomicMetricKey(item, tokenIndex)
}

function toggleFormulaAtomicMetricFilter(item: SqlBuilderCalculatedMetricItem, tokenIndex: number, metric: FormulaAtomicMetric) {
  startEditFormulaAtomicMetric(item, tokenIndex, metric)
  metric.filterLogic = metric.filterLogic === 'or' ? 'or' : 'and'
  metric.filters = Array.isArray(metric.filters) ? metric.filters : []
  if (!metric.filters.length) {
    metric.filters.push(emptyBuilderFilter())
  }
}

function buildPendingFormulaAtomicMetric(item: SqlBuilderCalculatedMetricItem): FormulaAtomicMetric | null {
  const field = item.pendingEventField || analysisFieldOptions.value[0]?.value || ''
  if (!field) return null
  const aggregation = item.pendingAggregation || 'count'
  const metricField = aggregation === 'count'
    ? field
    : item.pendingMetricField || defaultMetricFieldForEvent(field)
  const alias = sqlAlias(formulaAtomicMetricLabel({
    id: 'preview',
    field,
    metric: metricField,
    aggregation,
    alias: '',
    filterLogic: 'and',
    filters: [],
  }), `事件指标${Date.now()}`)
  return {
    id: nodeId('formula-atomic'),
    field,
    metric: metricField,
    aggregation,
    alias,
    label: formulaAtomicMetricLabel({
      id: 'preview',
      field,
      metric: metricField,
      aggregation,
      alias,
      filterLogic: 'and',
      filters: [],
    }),
    filterLogic: 'and',
    filters: [],
  }
}

function appendFormulaAtomicMetric(item: SqlBuilderCalculatedMetricItem) {
  const metric = buildPendingFormulaAtomicMetric(item)
  if (!metric) {
    ElMessage.warning('请先选择事件')
    return
  }
  appendFormulaToken(item, { type: 'atomicMetric', metric })
}

function appendFormulaNumber(item: SqlBuilderCalculatedMetricItem, value: string) {
  const cursorIndex = Number.isFinite(Number(item.formulaCursorIndex))
    ? Number(item.formulaCursorIndex)
    : item.tokens.length
  const last = item.tokens[cursorIndex - 1]
  if (last?.type === 'number') {
    if (value === '.' && last.value.includes('.')) return
    last.value = `${last.value}${value}`
    return
  }
  appendFormulaToken(item, { type: 'number', value })
}

function deleteFormulaToken(item: SqlBuilderCalculatedMetricItem) {
  const cursorIndex = Number.isFinite(Number(item.formulaCursorIndex))
    ? Number(item.formulaCursorIndex)
    : item.tokens.length
  const last = item.tokens[cursorIndex - 1]
  if (last?.type === 'number' && last.value.length > 1) {
    last.value = last.value.slice(0, -1)
    return
  }
  if (cursorIndex <= 0) return
  item.tokens.splice(cursorIndex - 1, 1)
  item.formulaCursorIndex = Math.max(0, cursorIndex - 1)
  activeFormulaAtomicMetricKey.value = ''
}

function clearFormulaTokens(item: SqlBuilderCalculatedMetricItem) {
  item.tokens = []
  item.formulaCursorIndex = 0
  activeFormulaMetricId.value = item.id
  activeFormulaAtomicMetricKey.value = ''
}

function setFormulaCursor(item: SqlBuilderCalculatedMetricItem, index: number) {
  item.formulaCursorIndex = Math.max(0, Math.min(index, item.tokens.length))
  activeFormulaMetricId.value = item.id
  activeFormulaAtomicMetricKey.value = ''
}

function handleFormulaDisplayClick(event: MouseEvent, item: SqlBuilderCalculatedMetricItem) {
  const editor = event.currentTarget as HTMLElement | null
  if (!editor) {
    setFormulaCursor(item, item.tokens.length)
    return
  }
  const target = event.target as HTMLElement | null
  if (target?.closest('.formula-token, .formula-insert-target')) {
    return
  }
  const tokenElements = Array.from(editor.querySelectorAll<HTMLElement>('.formula-token'))
  const matchedToken = tokenElements.find((tokenElement) => {
    const rect = tokenElement.getBoundingClientRect()
    return event.clientY >= rect.top - 4 && event.clientY <= rect.bottom + 4
  })
  if (matchedToken) {
    const tokenIndex = tokenElements.indexOf(matchedToken)
    setFormulaCursor(item, tokenIndex + 1)
    return
  }
  setFormulaCursor(item, item.tokens.length)
}

function formulaTokenText(token: FormulaToken) {
  return formulaTokensToText([token], builderMetricOptions.value)
}

function formulaMetricPrecisionText(item: SqlBuilderCalculatedMetricItem) {
  const decimalPlaces = Number.isFinite(Number(item.decimalPlaces)) ? Number(item.decimalPlaces) : 2
  return `${decimalPlaces} 位小数`
}

function handleFormulaEditorFocusout(event: FocusEvent, item: SqlBuilderCalculatedMetricItem) {
  const currentTarget = event.currentTarget as HTMLElement | null
  const relatedTarget = event.relatedTarget as Node | null
  if (currentTarget && relatedTarget && currentTarget.contains(relatedTarget)) {
    return
  }
  if (activeFormulaMetricId.value === item.id) {
    activeFormulaMetricId.value = ''
    activeFormulaAtomicMetricKey.value = ''
  }
}

function handleFormulaEditorKeydown(event: KeyboardEvent, item: SqlBuilderCalculatedMetricItem) {
  if (event.key === 'Backspace') {
    event.preventDefault()
    deleteFormulaToken(item)
    return
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    setFormulaCursor(item, item.formulaCursorIndex - 1)
    return
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    setFormulaCursor(item, item.formulaCursorIndex + 1)
    return
  }
  if (builderCalculationOperatorOptions.some((option) => option.value === event.key)) {
    event.preventDefault()
    appendFormulaOperator(item, event.key as FormulaOperator)
    return
  }
  if (event.key === '(' || event.key === ')') {
    event.preventDefault()
    appendFormulaParen(item, event.key)
    return
  }
  if (/^\d$/.test(event.key) || event.key === '.') {
    event.preventDefault()
    appendFormulaNumber(item, event.key)
  }
}

function invalidFormulaMetricItems() {
  return sqlBuilder.calculatedMetrics
    .map((item, index) => ({
      index,
      validation: calculatedMetricValidation(item),
    }))
    .filter((item) => !item.validation.valid)
}

function currentBuilderDialect(): BuilderSqlDialect {
  const rawType = String(
    datasourceInfo.value?.type ||
      datasourceInfo.value?.type_name ||
      datasourceInfo.value?.typeName ||
      ''
  ).toLowerCase()
  if (['pg', 'postgres', 'postgresql'].includes(rawType)) {
    return 'postgres'
  }
  if (['mysql', 'mariadb'].includes(rawType)) {
    return 'mysql'
  }
  return 'generic'
}

function quoteIdentifierPart(value: string) {
  const text = String(value || '').trim()
  if (!text) {
    return ''
  }
  const dialect = currentBuilderDialect()
  if (dialect === 'mysql') {
    return `\`${text.replace(/`/g, '``')}\``
  }
  return `"${text.replace(/"/g, '""')}"`
}

function quoteIdentifier(value: string) {
  return String(value || '')
    .split('.')
    .map((part) => quoteIdentifierPart(part))
    .filter(Boolean)
    .join('.')
}

function resetSqlBuilderState() {
  sqlBuilder.activeTab = 'builder'
  sqlBuilder.analysisModel = 'event'
  sqlBuilder.timeField = SQL_EDITOR_TIME_FIELD
  sqlBuilder.timeGrain = SQL_EDITOR_TIME_GRAIN
  sqlBuilder.timeRange = 'expression'
  sqlBuilder.timeCustomRange = []
  sqlBuilder.dateExpressionPickerEnabled = true
  sqlBuilder.metricDateExpressionEnabled = false
  sqlBuilder.timeExpression = defaultDashboardDateExpression()
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  dateExpressionConfigError.value = ''
  sqlBuilder.metricItems = []
  sqlBuilder.calculatedMetrics = []
  sqlBuilder.groups = []
  sqlBuilder.globalFilters = []
  sqlBuilder.globalFilterLogic = 'and'
  sqlBuilder.approximate = false
  resetRetentionConfig()
  resetFunnelConfig()
  resetDistributionConfig()
  resetIntervalConfig()
  resetPathConfig()
  resetAttributionConfig()
  clearBuilderAgentAdvice()
}

function clearBuilderAgentAdvice() {
  builderAgentAdvice.visible = false
  builderAgentAdvice.severity = ''
  builderAgentAdvice.intent = ''
  builderAgentAdvice.message = ''
  builderAgentAdvice.advice = ''
  builderAgentAdvice.issues = []
  builderAgentAdvice.suggestions = []
  builderAgentAdvice.raw = ''
}

function builderAgentAdviceForSave() {
  return {
    severity: builderAgentAdvice.severity || '',
    intent: builderAgentAdvice.intent || '',
    message: builderAgentAdvice.message || '',
    advice: builderAgentAdvice.advice || '',
    issues: [...builderAgentAdvice.issues],
    suggestions: [...builderAgentAdvice.suggestions],
    raw: builderAgentAdvice.raw || '',
  }
}

function restoreBuilderAgentAdvice(value: any) {
  clearBuilderAgentAdvice()
  if (!value || typeof value !== 'object') {
    return
  }
  builderAgentAdvice.severity = typeof value.severity === 'string' ? value.severity : ''
  builderAgentAdvice.intent = cleanBuilderAdviceText(value.intent)
  builderAgentAdvice.message = cleanBuilderAdviceText(value.message)
  builderAgentAdvice.advice = cleanBuilderAdviceText(value.advice)
  builderAgentAdvice.issues = cleanBuilderAdviceItems(value.issues, 'issue')
  builderAgentAdvice.suggestions = cleanBuilderAdviceItems(value.suggestions, 'suggestion')
  builderAgentAdvice.raw = typeof value.raw === 'string' ? value.raw : ''
}

function setBuilderAgentAdvice(value: {
  severity?: string
  intent?: string
  message?: string
  advice?: string
  issues?: any[]
  suggestions?: any[]
  raw?: string
}) {
  const localIssues = currentBuilderReadableIssues()
  const cleanIssues = cleanBuilderAdviceItems(value.issues, 'issue')
  const actionSuggestions = fallbackBuilderConfigSuggestions()
  const cleanSuggestions = cleanBuilderAdviceItems(value.suggestions, 'suggestion')
  const mergedSuggestions = mergeBuilderSuggestions(actionSuggestions, cleanSuggestions)
  const issues = unique([...localIssues, ...cleanIssues]).slice(0, 3)
  const message = cleanBuilderAdviceText(value.message)
  builderAgentAdvice.severity = value.severity || ''
  builderAgentAdvice.intent = cleanBuilderAdviceText(value.intent) || inferBuilderIntentText()
  builderAgentAdvice.message = issues.length ? issues[0] || message : message
  builderAgentAdvice.advice = issues.length ? '照着下面改，不用在“分组项”里加时间字段。' : ''
  builderAgentAdvice.issues = issues
  builderAgentAdvice.suggestions = mergedSuggestions.slice(0, 5)
  builderAgentAdvice.raw = value.raw || ''
}

const hasBuilderAgentAdvice = computed(() =>
  Boolean(
    builderAgentAdvice.message ||
      builderAgentAdvice.intent ||
      builderAgentAdvice.advice ||
      builderAgentAdvice.issues.length ||
      builderAgentAdvice.suggestions.length
  )
)

function builderLogic(value: any): SqlBuilderFilterLogic {
  return value === 'or' ? 'or' : 'and'
}

function cleanBuilderAdviceText(value: any) {
  const text = String(value || '')
    .replace(/Data Skills?/gi, '系统口径')
    .replace(/selectedFields/gi, '已选字段')
    .replace(/manual-dashboard-context/gi, '当前配置')
    .replace(/分析指标\s+(\d+)/g, '分析指标$1')
    .trim()
  if (/已根据|已按|已自动|自动添加|自动应用|自动转换|已转换|SQL|UTC\+?8|系统口径|JOIN|主表|跨表/i.test(text)) {
    return ''
  }
  return text
}

function shouldHideBuilderAdviceItem(text: string, type: 'issue' | 'suggestion') {
  const value = String(text || '')
  if (!value.trim()) {
    return true
  }
  if (/selectedFields\s*包含|已选字段\s*包含/i.test(value)) {
    return true
  }
  if (/manual-dashboard-context|当前配置.*JSON|raw|schema/i.test(value)) {
    return true
  }
  if (/已根据|已按|已自动|自动添加|自动应用|自动转换|已转换|SQL|UTC\+?8|系统口径|JOIN|主表|跨表/i.test(value)) {
    return true
  }
  if (/配置已转换|生成.*SQL|查询.*SQL/i.test(value)) {
    return true
  }
  if (/分组项.*(\b\w+\.(?:time|dt)\b|事件时间|时间字段|按天|按周|按月)|时间.*分组项|分组项.*时间/i.test(value)) {
    return true
  }
  if (type === 'suggestion' && !/(时间范围|分析指标|筛选条件|分组项|字段选|聚合选|别名填|条件选|值填|值输入框|手动填|添加|改成)/.test(value)) {
    return true
  }
  if (type === 'issue' && /表格无分组维度|仅显示时间.*指标|无法按天|分组维度/i.test(value)) {
    return true
  }
  return false
}

function cleanBuilderAdviceItems(value: any, type: 'issue' | 'suggestion') {
  const rawItems = Array.isArray(value) ? value : []
  const items = unique(
    rawItems
      .map((item) => cleanBuilderAdviceText(item))
      .filter((item) => !shouldHideBuilderAdviceItem(item, type))
  )
  return type === 'suggestion' ? items.sort(builderSuggestionOrder) : items
}

function normalizeBuilderSuggestionKey(value: string) {
  return String(value || '')
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[「」"'`，。；;：:、]/g, '')
}

function builderSuggestionFilterKey(value: string) {
  const text = String(value || '')
  const fieldMatch = text.match(/字段选\s*「([^」]+)」/) || text.match(/字段选\s*([^，。；]+)/)
  const operatorMatch = text.match(/条件选\s*「([^」]+)」/) || text.match(/条件选\s*([^，。；]+)/)
  const valueMatch =
    text.match(/(?:输入框填|手动填|值填|填)\s*「([^」]+)」/) ||
    text.match(/(?:输入框填|手动填|值填|填)\s*([^，。；]+)/)
  const fieldKey = fieldMatch?.[1] ? normalizeBuilderSuggestionKey(fieldMatch[1]) : ''
  const operatorKey = operatorMatch?.[1] ? normalizeBuilderSuggestionKey(operatorMatch[1]) : ''
  const valueKey = valueMatch?.[1] ? normalizeBuilderSuggestionKey(valueMatch[1]) : ''
  const parts = [fieldKey, operatorKey, valueKey].filter(Boolean)
  return parts.length ? parts.join('-') : normalizeBuilderSuggestionKey(text).slice(0, 120)
}

function builderSuggestionSlot(value: string) {
  const text = String(value || '').trim()
  if (text.startsWith('时间范围：')) return 'time'
  const metricFilterMatch = text.match(/^分析指标\s*(\d+)筛选条件：/)
  if (metricFilterMatch) return `metric-${metricFilterMatch[1]}-filter-${builderSuggestionFilterKey(text)}`
  const metricMatch = text.match(/^分析指标\s*(\d+)：/)
  if (metricMatch) return `metric-${metricMatch[1]}`
  if (text.startsWith('全局筛选：')) return `global-filter-${builderSuggestionFilterKey(text)}`
  if (text.startsWith('分组项：')) return 'group'
  return text
}

function builderSuggestionScore(value: string) {
  let score = 0
  if (/字段选/.test(value)) score += 2
  if (/聚合选|条件选|粒度选|范围选/.test(value)) score += 2
  if (/计算字段选|最右侧|输入框|点击/.test(value)) score += 2
  if (/别名填/.test(value)) score += 1
  if (/把最后输入框|改成业务名|没有业务含义/.test(value)) score -= 2
  return score
}

function mergeBuilderSuggestions(primary: string[], secondary: string[]) {
  const bySlot = new Map<string, string>()
  unique([...primary, ...secondary]).forEach((item) => {
    const slot = builderSuggestionSlot(item)
    const existing = bySlot.get(slot)
    if (!existing || builderSuggestionScore(item) > builderSuggestionScore(existing)) {
      bySlot.set(slot, item)
    }
  })
  return Array.from(bySlot.values()).sort(builderSuggestionOrder)
}

function builderSuggestionOrder(a: string, b: string) {
  const rank = (value: string) => {
    if (value.startsWith('时间范围：')) return 0
    if (/^分析指标\d+：/.test(value)) return 1
    if (/^分析指标\s*\d+筛选条件：/.test(value)) return 2
    if (value.startsWith('全局筛选：')) return 3
    if (value.startsWith('分组项：')) return 4
    return 9
  }
  return rank(a) - rank(b)
}

function filterRuleNodes(filters: SqlBuilderFilter[]) {
  const rules: SqlBuilderFilter[] = []
  const visit = (nodes: SqlBuilderFilter[]) => {
    nodes.forEach((node) => {
      if (node.type === 'group' || Array.isArray(node.children)) {
        visit(node.children || [])
      } else if (isEffectiveBuilderFilter(node)) {
        rules.push(node)
      }
    })
  }
  visit(filters || [])
  return rules
}

function currentBuilderReadableIssues() {
  const issues: string[] = []
  const preferredTable = fieldOptionByValue(sqlBuilder.timeField)?.table || ''
  sqlBuilder.metricItems.forEach((item, index) => {
    const metricField = fieldOptionByValue(metricMeasureField(item))
    if (preferredTable && metricField && metricField.table !== preferredTable) {
      issues.push(`分析指标${index + 1}字段和时间字段不在同一张表；请按 Agent 建议改到同一业务明细表。`)
    }
  })
  return unique(issues)
}

function builderFilterOperatorWithoutValue(operator: string) {
  return operator === 'is_null' || operator === 'is_not_null'
}

function builderFilterRuleHasValue(node: Pick<SqlBuilderFilter, 'operator' | 'value'>) {
  if (builderFilterOperatorWithoutValue(node.operator)) {
    return true
  }
  return String(node.value ?? '').trim() !== ''
}

function isEffectiveBuilderFilter(node?: SqlBuilderFilter | null): node is SqlBuilderFilter {
  if (!node) {
    return false
  }
  if (node.type === 'group' || Array.isArray(node.children)) {
    return (node.children || []).some((child) => isEffectiveBuilderFilter(child))
  }
  return Boolean(node.field && builderFilterRuleHasValue(node))
}

function compactBuilderFilters(filters: SqlBuilderFilter[]) {
  return (filters || []).map(cloneBuilderFilterForSave).filter(Boolean) as SqlBuilderFilter[]
}

function hasEffectiveBuilderFilters(filters: SqlBuilderFilter[]) {
  return (filters || []).some((node) => isEffectiveBuilderFilter(node))
}

function fallbackBuilderConfigSuggestions() {
  const suggestions: string[] = []
  if (sqlBuilder.timeField) {
    suggestions.push(`时间范围：固定使用字段「${SQL_EDITOR_TIME_FIELD}」、粒度「按天」和日期格式「YYYYMMDD 数字」。`)
  }
  const preferredTable = fieldOptionByValue(sqlBuilder.timeField)?.table || ''
  sqlBuilder.metricItems.forEach((item, index) => {
    suggestions.push(describeBuilderMetricConfig(item, index, preferredTable))
    filterRuleNodes(item.filters || []).forEach((rule) => {
      if (!rule.field) return
      suggestions.push(`分析指标${index + 1}筛选条件：字段选 ${quotedBuilderFieldLabel(rule.field)}，条件选「${builderFilterOperatorLabel(rule.operator)}」，最右侧输入框填「${rule.value || '筛选值'}」。`)
    })
  })
  if (sqlBuilder.groups.length) {
    suggestions.push(`分组项：${sqlBuilder.groups.filter(Boolean).map((field) => `添加 ${quotedBuilderFieldLabel(field)}`).join('；')}。`)
  } else {
    suggestions.push('分组项：先不填；只有要按国家、渠道、平台拆开看时再添加。')
  }
  return unique(suggestions).sort(builderSuggestionOrder)
}

function cloneBuilderFilterForSave(node: SqlBuilderFilter): SqlBuilderFilter | null {
  const isGroup = node.type === 'group'
  if (isGroup) {
    const children = (node.children || []).map(cloneBuilderFilterForSave).filter(Boolean) as SqlBuilderFilter[]
    if (!children.length) {
      return null
    }
    return {
      id: node.id || nodeId('group'),
      type: 'group',
      field: '',
      operator: 'eq',
      value: '',
      logic: builderLogic(node.logic),
      children,
    }
  }
  if (!node.field || !builderFilterRuleHasValue(node)) {
    return null
  }
  return {
    id: node.id || nodeId('filter'),
    type: 'rule',
    field: node.field || '',
    operator: node.operator || 'eq',
    value: node.value ?? '',
    logic: builderLogic(node.logic),
    children: [],
  }
}

function restoreBuilderFilter(node: any): SqlBuilderFilter | null {
  const isGroup = node?.type === 'group'
  const operator = builderFilterOperatorOptions.some((option) => option.value === node?.operator)
    ? node.operator
    : 'eq'
  if (isGroup) {
    const children = Array.isArray(node?.children)
      ? (node.children.map(restoreBuilderFilter).filter(Boolean) as SqlBuilderFilter[])
      : []
    if (!children.length) {
      return null
    }
    return {
      id: typeof node?.id === 'string' && node.id ? node.id : nodeId('group'),
      type: 'group',
      field: '',
      operator: 'eq',
      value: '',
      logic: builderLogic(node?.logic),
      children,
    }
  }
  const restoredRule = {
    id: typeof node?.id === 'string' && node.id ? node.id : nodeId('filter'),
    type: 'rule' as const,
    field: typeof node?.field === 'string' ? node.field : '',
    operator,
    value: node?.value === undefined || node?.value === null ? '' : String(node.value),
    logic: builderLogic(node?.logic),
    children: [],
  }
  if (!isEffectiveBuilderFilter(restoredRule)) {
    return null
  }
  return {
    ...restoredRule,
  }
}

function restoreBuilderFilters(value: any): SqlBuilderFilter[] {
  return Array.isArray(value)
    ? (value.map(restoreBuilderFilter).filter(Boolean) as SqlBuilderFilter[])
    : []
}

function builderConfigForSave() {
  const usesDashboardDateParameters = shouldUseDashboardDateParameters()
  return {
    analysisModel: sqlBuilder.analysisModel,
    retention: sqlBuilder.analysisModel === 'retention' ? {
      entityField: sqlBuilder.retention.entityField,
      initialEvent: sqlBuilder.retention.initialEvent,
      initialEventAlias: sqlBuilder.retention.initialEventAlias.trim(),
      initialEventFilters: {
        logic: builderLogic(sqlBuilder.retention.initialEventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.retention.initialEventFilters),
      },
      returnEvent: sqlBuilder.retention.returnEvent,
      returnEventAlias: sqlBuilder.retention.returnEventAlias.trim(),
      returnEventFilters: {
        logic: builderLogic(sqlBuilder.retention.returnEventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.retention.returnEventFilters),
      },
      simultaneous: {
        enabled: sqlBuilder.retention.simultaneous.enabled,
        event: sqlBuilder.retention.simultaneous.enabled ? sqlBuilder.retention.simultaneous.event : '',
        aggregation: sqlBuilder.retention.simultaneous.aggregation,
        metricField: sqlBuilder.retention.simultaneous.enabled
          && sqlBuilder.retention.simultaneous.aggregation !== 'count'
          ? sqlBuilder.retention.simultaneous.metricField
          : '',
      },
      relatedProperty: {
        enabled: sqlBuilder.retention.relatedProperty.enabled,
        initialProperty: sqlBuilder.retention.relatedProperty.enabled ? sqlBuilder.retention.relatedProperty.initialProperty : '',
        returnProperty: sqlBuilder.retention.relatedProperty.enabled ? sqlBuilder.retention.relatedProperty.returnProperty : '',
        simultaneousProperty: sqlBuilder.retention.relatedProperty.enabled && sqlBuilder.retention.simultaneous.enabled
          ? sqlBuilder.retention.relatedProperty.simultaneousProperty
          : '',
        asGroup: sqlBuilder.retention.relatedProperty.enabled && sqlBuilder.retention.relatedProperty.asGroup,
      },
    } : undefined,
    funnel: sqlBuilder.analysisModel === 'funnel' ? {
      entityField: sqlBuilder.funnel.entityField,
      window: normalizeFunnelWindow(sqlBuilder.funnel.window),
      relatedPropertyEnabled: sqlBuilder.funnel.relatedPropertyEnabled,
      steps: sqlBuilder.funnel.steps.map((step) => ({
        id: step.id,
        event: step.event,
        alias: step.alias.trim(),
        filters: {
          logic: builderLogic(step.filterLogic),
          rules: compactBuilderFilters(step.filters),
        },
        relatedProperty: sqlBuilder.funnel.relatedPropertyEnabled ? step.relatedProperty : '',
      })),
    } : undefined,
    distribution: sqlBuilder.analysisModel === 'distribution' ? {
      entityField: sqlBuilder.distribution.entityField,
      event: sqlBuilder.distribution.event,
      eventFilters: {
        logic: builderLogic(sqlBuilder.distribution.eventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.distribution.eventFilters),
      },
      metric: {
        kind: sqlBuilder.distribution.metric.kind,
        field: sqlBuilder.distribution.metric.kind === 'property' ? sqlBuilder.distribution.metric.field : '',
        aggregation: sqlBuilder.distribution.metric.aggregation,
      },
      interval: {
        mode: effectiveDistributionInterval().mode,
        customBounds: effectiveDistributionInterval().mode === 'custom'
          ? [...effectiveDistributionInterval().customBounds]
          : [],
      },
      simultaneous: {
        enabled: sqlBuilder.distribution.simultaneous.enabled,
        event: sqlBuilder.distribution.simultaneous.enabled ? sqlBuilder.distribution.simultaneous.event : '',
        aggregation: sqlBuilder.distribution.simultaneous.aggregation,
        metricField: sqlBuilder.distribution.simultaneous.enabled
          && sqlBuilder.distribution.simultaneous.aggregation !== 'count'
          ? sqlBuilder.distribution.simultaneous.metricField
          : '',
      },
    } : undefined,
    interval: sqlBuilder.analysisModel === 'interval' ? {
      entityField: sqlBuilder.interval.entityField,
      startEvent: sqlBuilder.interval.startEvent,
      startEventFilters: {
        logic: builderLogic(sqlBuilder.interval.startEventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.interval.startEventFilters),
      },
      endEvent: sqlBuilder.interval.endEvent,
      endEventFilters: {
        logic: builderLogic(sqlBuilder.interval.endEventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.interval.endEventFilters),
      },
      relatedProperty: {
        enabled: sqlBuilder.interval.relatedProperty.enabled,
        startProperty: sqlBuilder.interval.relatedProperty.enabled
          ? sqlBuilder.interval.relatedProperty.startProperty
          : '',
        endProperty: sqlBuilder.interval.relatedProperty.enabled
          ? sqlBuilder.interval.relatedProperty.endProperty
          : '',
      },
      limitSeconds: clampIntervalLimitSeconds(sqlBuilder.interval.limitSeconds),
    } : undefined,
    path: sqlBuilder.analysisModel === 'path' ? {
      events: sqlBuilder.path.events.map((item) => ({
        id: item.id,
        event: item.event,
        splitProperties: [...item.splitProperties],
      })),
      initialEvent: sqlBuilder.path.initialEvent,
      sessionGapSeconds: clampPathSessionGapSeconds(sqlBuilder.path.sessionGapSeconds),
    } : undefined,
    revenue: sqlBuilder.analysisModel === 'revenue' ? {
      entityField: sqlBuilder.revenue.entityField,
      initialEvent: sqlBuilder.revenue.initialEvent,
      paymentEvent: sqlBuilder.revenue.paymentEvent,
      metric: {
        method: sqlBuilder.revenue.metric.method,
        field: revenueMetricUsesProperty(sqlBuilder.revenue.metric.method) ? sqlBuilder.revenue.metric.field : '',
      },
      costEnabled: sqlBuilder.revenue.costEnabled,
      costField: sqlBuilder.revenue.costEnabled ? sqlBuilder.revenue.costField : '',
      observationDays: clampRevenueObservationDays(sqlBuilder.revenue.observationDays),
    } : null,
    attribution: sqlBuilder.analysisModel === 'attribution' ? {
      entityField: sqlBuilder.attribution.entityField,
      method: sqlBuilder.attribution.method,
      window: normalizeAttributionWindow(sqlBuilder.attribution.window),
      targetEvent: sqlBuilder.attribution.targetEvent,
      targetEventFilters: {
        logic: builderLogic(sqlBuilder.attribution.targetEventFilterLogic),
        rules: compactBuilderFilters(sqlBuilder.attribution.targetEventFilters),
      },
      targetMetric: {
        aggregation: sqlBuilder.attribution.targetMetric.aggregation,
        metricField: sqlBuilder.attribution.targetMetric.aggregation === 'count'
          ? ''
          : sqlBuilder.attribution.targetMetric.metricField,
      },
      includeDirect: sqlBuilder.attribution.includeDirect,
      events: sqlBuilder.attribution.events.map((item) => ({
        id: item.id,
        event: item.event,
        filters: {
          logic: builderLogic(item.filterLogic),
          rules: compactBuilderFilters(item.filters),
        },
      })),
    } : undefined,
    ranking: sqlBuilder.analysisModel === 'ranking' ? {
      entityField: sqlBuilder.ranking.entityField,
      metric: serializeRankingMetric(sqlBuilder.ranking.metric),
      tieHandling: sqlBuilder.ranking.tieHandling,
      simultaneousMetrics: sqlBuilder.ranking.simultaneousMetrics.map(serializeRankingMetric),
      simultaneousProperties: [...sqlBuilder.ranking.simultaneousProperties],
    } : undefined,
    timeField: SQL_EDITOR_TIME_FIELD,
    timeGrain: SQL_EDITOR_TIME_GRAIN,
    timeRange: 'expression',
    timeCustomRange: [],
    dateExpressionPickerEnabled: usesDashboardDateParameters,
    metricDateExpressionEnabled: sqlBuilder.metricDateExpressionEnabled === true,
    timeExpression: usesDashboardDateParameters && sqlBuilder.timeExpression
      ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
      : null,
    groups: [...sqlBuilder.groups],
    globalFilters: compactBuilderFilters(sqlBuilder.globalFilters),
    globalFilterLogic: builderLogic(sqlBuilder.globalFilterLogic),
    approximate: sqlBuilder.approximate === true,
    agentAdvice: builderAgentAdviceForSave(),
  }
}

function restoreSqlBuilderState(value: any) {
  sqlBuilder.timeField = SQL_EDITOR_TIME_FIELD
  sqlBuilder.timeGrain = SQL_EDITOR_TIME_GRAIN
  sqlBuilder.timeRange = 'expression'
  sqlBuilder.timeCustomRange = []
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  if (!value || typeof value !== 'object') {
    return
  }
  sqlBuilder.analysisModel = ['retention', 'funnel', 'distribution', 'interval', 'path', 'revenue', 'attribution', 'ranking'].includes(value.analysisModel)
    ? value.analysisModel
    : 'event'
  const retention = value.retention && typeof value.retention === 'object' ? value.retention : {}
  sqlBuilder.retention.entityField = typeof retention.entityField === 'string' ? retention.entityField : ''
  sqlBuilder.retention.initialEvent = typeof retention.initialEvent === 'string' ? retention.initialEvent : ''
  sqlBuilder.retention.initialEventAlias = typeof retention.initialEventAlias === 'string' ? retention.initialEventAlias : ''
  sqlBuilder.retention.initialEventFilterLogic = builderLogic(retention.initialEventFilters?.logic)
  sqlBuilder.retention.initialEventFilters = restoreBuilderFilters(retention.initialEventFilters?.rules)
  sqlBuilder.retention.returnEvent = typeof retention.returnEvent === 'string' ? retention.returnEvent : ''
  sqlBuilder.retention.returnEventAlias = typeof retention.returnEventAlias === 'string' ? retention.returnEventAlias : ''
  sqlBuilder.retention.returnEventFilterLogic = builderLogic(retention.returnEventFilters?.logic)
  sqlBuilder.retention.returnEventFilters = restoreBuilderFilters(retention.returnEventFilters?.rules)
  const simultaneous = retention.simultaneous && typeof retention.simultaneous === 'object' ? retention.simultaneous : {}
  sqlBuilder.retention.simultaneous.enabled = simultaneous.enabled === true
  sqlBuilder.retention.simultaneous.event = sqlBuilder.retention.simultaneous.enabled && typeof simultaneous.event === 'string'
    ? simultaneous.event
    : ''
  sqlBuilder.retention.simultaneous.aggregation = builderAggregationOptions.some(
    (option) => option.value === simultaneous.aggregation
  ) ? simultaneous.aggregation as SqlBuilderAggregation : 'count'
  sqlBuilder.retention.simultaneous.metricField = sqlBuilder.retention.simultaneous.enabled
    && sqlBuilder.retention.simultaneous.aggregation !== 'count'
    && typeof simultaneous.metricField === 'string'
    ? simultaneous.metricField
    : ''
  const relatedProperty = retention.relatedProperty && typeof retention.relatedProperty === 'object'
    ? retention.relatedProperty
    : {}
  sqlBuilder.retention.relatedProperty.enabled = relatedProperty.enabled === true
  sqlBuilder.retention.relatedProperty.initialProperty = sqlBuilder.retention.relatedProperty.enabled && typeof relatedProperty.initialProperty === 'string'
    ? relatedProperty.initialProperty
    : ''
  sqlBuilder.retention.relatedProperty.returnProperty = sqlBuilder.retention.relatedProperty.enabled && typeof relatedProperty.returnProperty === 'string'
    ? relatedProperty.returnProperty
    : ''
  sqlBuilder.retention.relatedProperty.simultaneousProperty = sqlBuilder.retention.relatedProperty.enabled
    && sqlBuilder.retention.simultaneous.enabled
    && typeof relatedProperty.simultaneousProperty === 'string'
    ? relatedProperty.simultaneousProperty
    : ''
  sqlBuilder.retention.relatedProperty.asGroup = sqlBuilder.retention.relatedProperty.enabled && relatedProperty.asGroup === true
  const funnel = value.funnel && typeof value.funnel === 'object' ? value.funnel : {}
  sqlBuilder.funnel.entityField = typeof funnel.entityField === 'string' ? funnel.entityField : ''
  sqlBuilder.funnel.window = normalizeFunnelWindow(funnel.window, funnel.windowDays)
  sqlBuilder.funnel.relatedPropertyEnabled = funnel.relatedPropertyEnabled === true
  const restoredFunnelSteps = Array.isArray(funnel.steps)
    ? funnel.steps.map((step: any) => {
        const restored = createFunnelStep()
        restored.id = typeof step?.id === 'string' && step.id ? step.id : restored.id
        restored.event = typeof step?.event === 'string' ? step.event : ''
        restored.alias = typeof step?.alias === 'string' ? step.alias : ''
        restored.filterLogic = builderLogic(step?.filterLogic || step?.filters?.logic)
        restored.filters = restoreBuilderFilters(step?.filters?.rules || step?.filters)
        restored.relatedProperty = typeof step?.relatedProperty === 'string' ? step.relatedProperty : ''
        return restored
      })
    : []
  sqlBuilder.funnel.steps = restoredFunnelSteps.length >= 2
    ? restoredFunnelSteps
    : [createFunnelStep(), createFunnelStep(), createFunnelStep()]
  sqlBuilder.funnel.steps.forEach((step) => {
    funnelFilterExpanded[step.id] = false
    funnelAliasEditing[step.id] = false
    funnelAliasDraft[step.id] = ''
  })
  const distribution = value.distribution && typeof value.distribution === 'object' ? value.distribution : {}
  sqlBuilder.distribution.entityField = typeof distribution.entityField === 'string' ? distribution.entityField : ''
  sqlBuilder.distribution.event = typeof distribution.event === 'string' ? distribution.event : ''
  sqlBuilder.distribution.eventFilterLogic = builderLogic(distribution.eventFilters?.logic)
  sqlBuilder.distribution.eventFilters = restoreBuilderFilters(distribution.eventFilters?.rules)
  const distributionMetric = distribution.metric && typeof distribution.metric === 'object' ? distribution.metric : {}
  sqlBuilder.distribution.metric.kind = ['count', 'days', 'hours', 'property'].includes(distributionMetric.kind)
    ? distributionMetric.kind
    : 'count'
  sqlBuilder.distribution.metric.field = sqlBuilder.distribution.metric.kind === 'property'
    && typeof distributionMetric.field === 'string'
    ? distributionMetric.field
    : ''
  sqlBuilder.distribution.metric.aggregation = typeof distributionMetric.aggregation === 'string'
    ? distributionMetric.aggregation
    : 'sum'
  const distributionInterval = distribution.interval && typeof distribution.interval === 'object' ? distribution.interval : {}
  sqlBuilder.distribution.interval.mode = ['auto', 'discrete', 'custom'].includes(distributionInterval.mode)
    ? distributionInterval.mode
    : 'auto'
  sqlBuilder.distribution.interval.customBounds = Array.isArray(distributionInterval.customBounds)
    ? distributionInterval.customBounds.map(Number).filter(Number.isFinite)
    : []
  if (sqlBuilder.distribution.metric.kind === 'count') {
    sqlBuilder.distribution.interval = { mode: 'discrete', customBounds: [] }
  }
  const distributionSimultaneous = distribution.simultaneous && typeof distribution.simultaneous === 'object'
    ? distribution.simultaneous
    : {}
  sqlBuilder.distribution.simultaneous.enabled = distributionSimultaneous.enabled === true
  sqlBuilder.distribution.simultaneous.event = sqlBuilder.distribution.simultaneous.enabled
    && typeof distributionSimultaneous.event === 'string'
    ? distributionSimultaneous.event
    : ''
  sqlBuilder.distribution.simultaneous.aggregation = builderAggregationOptions.some(
    (option) => option.value === distributionSimultaneous.aggregation
  ) ? distributionSimultaneous.aggregation : 'count'
  sqlBuilder.distribution.simultaneous.metricField = sqlBuilder.distribution.simultaneous.enabled
    && sqlBuilder.distribution.simultaneous.aggregation !== 'count'
    && typeof distributionSimultaneous.metricField === 'string'
    ? distributionSimultaneous.metricField
    : ''
  distributionFilterExpanded.value = false
  const interval = value.interval && typeof value.interval === 'object' ? value.interval : {}
  sqlBuilder.interval.entityField = typeof interval.entityField === 'string' ? interval.entityField : ''
  sqlBuilder.interval.startEvent = typeof interval.startEvent === 'string' ? interval.startEvent : ''
  sqlBuilder.interval.startEventFilterLogic = builderLogic(interval.startEventFilters?.logic)
  sqlBuilder.interval.startEventFilters = restoreBuilderFilters(interval.startEventFilters?.rules)
  sqlBuilder.interval.endEvent = typeof interval.endEvent === 'string' ? interval.endEvent : ''
  sqlBuilder.interval.endEventFilterLogic = builderLogic(interval.endEventFilters?.logic)
  sqlBuilder.interval.endEventFilters = restoreBuilderFilters(interval.endEventFilters?.rules)
  const intervalRelatedProperty = interval.relatedProperty && typeof interval.relatedProperty === 'object'
    ? interval.relatedProperty
    : {}
  sqlBuilder.interval.relatedProperty.enabled = intervalRelatedProperty.enabled === true
  sqlBuilder.interval.relatedProperty.startProperty = sqlBuilder.interval.relatedProperty.enabled
    && typeof intervalRelatedProperty.startProperty === 'string'
    ? intervalRelatedProperty.startProperty
    : ''
  sqlBuilder.interval.relatedProperty.endProperty = sqlBuilder.interval.relatedProperty.enabled
    && typeof intervalRelatedProperty.endProperty === 'string'
    ? intervalRelatedProperty.endProperty
    : ''
  sqlBuilder.interval.limitSeconds = clampIntervalLimitSeconds(interval.limitSeconds)
  intervalFilterExpanded.start = false
  intervalFilterExpanded.end = false
  const path = value.path && typeof value.path === 'object' ? value.path : {}
  const restoredPathEvents = Array.isArray(path.events)
    ? path.events.slice(0, PATH_EVENT_LIMIT).map((item: any, index: number) => ({
        id: typeof item?.id === 'string' && item.id ? item.id : `path-event-${index}`,
        event: typeof item?.event === 'string' ? item.event : '',
        splitProperties: Array.isArray(item?.splitProperties)
          ? item.splitProperties.filter((field: any) => typeof field === 'string')
          : [],
      }))
    : []
  sqlBuilder.path.events = restoredPathEvents.length
    ? restoredPathEvents
    : [{ id: 'path-event-initial', event: '', splitProperties: [] }]
  sqlBuilder.path.initialEvent = typeof path.initialEvent === 'string' ? path.initialEvent : ''
  sqlBuilder.path.sessionGapSeconds = clampPathSessionGapSeconds(path.sessionGapSeconds)
  const revenue = value.revenue && typeof value.revenue === 'object' ? value.revenue : {}
  const revenueMetric = revenue.metric && typeof revenue.metric === 'object' ? revenue.metric : {}
  const revenueMetricMethods = [
    'count',
    'entity_count',
    'per_entity_count',
    'period_cumulative_count',
    'period_average_count',
    'period_cumulative_entity_count',
    'period_average_entity_count',
    'property_sum',
    'property_avg',
  ]
  sqlBuilder.revenue.entityField = typeof revenue.entityField === 'string' ? revenue.entityField : ''
  sqlBuilder.revenue.initialEvent = typeof revenue.initialEvent === 'string' ? revenue.initialEvent : ''
  sqlBuilder.revenue.paymentEvent = typeof revenue.paymentEvent === 'string' ? revenue.paymentEvent : ''
  sqlBuilder.revenue.metric.method = revenueMetricMethods.includes(revenueMetric.method)
    ? revenueMetric.method
    : 'count'
  sqlBuilder.revenue.metric.field = revenueMetricUsesProperty(sqlBuilder.revenue.metric.method)
    && typeof revenueMetric.field === 'string'
    ? revenueMetric.field
    : ''
  sqlBuilder.revenue.costEnabled = revenue.costEnabled === true
  sqlBuilder.revenue.costField = sqlBuilder.revenue.costEnabled && typeof revenue.costField === 'string'
    ? revenue.costField
    : ''
  sqlBuilder.revenue.observationDays = clampRevenueObservationDays(revenue.observationDays)
  const attribution = value.attribution && typeof value.attribution === 'object' ? value.attribution : {}
  sqlBuilder.attribution.entityField = typeof attribution.entityField === 'string' ? attribution.entityField : ''
  sqlBuilder.attribution.method = attribution.method === 'linear' ? attribution.method : 'linear'
  sqlBuilder.attribution.window = normalizeAttributionWindow(attribution.window)
  sqlBuilder.attribution.targetEvent = typeof attribution.targetEvent === 'string' ? attribution.targetEvent : ''
  sqlBuilder.attribution.targetEventFilterLogic = builderLogic(attribution.targetEventFilters?.logic)
  sqlBuilder.attribution.targetEventFilters = restoreBuilderFilters(attribution.targetEventFilters?.rules)
  const attributionTargetMetric = attribution.targetMetric && typeof attribution.targetMetric === 'object'
    ? attribution.targetMetric
    : {}
  sqlBuilder.attribution.targetMetric.aggregation = builderAggregationOptions.some(
    (option) => option.value === attributionTargetMetric.aggregation
  ) ? attributionTargetMetric.aggregation : 'count'
  sqlBuilder.attribution.targetMetric.metricField = sqlBuilder.attribution.targetMetric.aggregation !== 'count'
    && typeof attributionTargetMetric.metricField === 'string'
    ? attributionTargetMetric.metricField
    : ''
  sqlBuilder.attribution.includeDirect = attribution.includeDirect !== false
  sqlBuilder.attribution.events = Array.isArray(attribution.events)
    ? attribution.events.slice(0, ATTRIBUTION_EVENT_LIMIT).map((item: any) => ({
        id: typeof item?.id === 'string' && item.id ? item.id : nodeId('attribution-event'),
        event: typeof item?.event === 'string' ? item.event : '',
        filterLogic: builderLogic(item?.filters?.logic),
        filters: restoreBuilderFilters(item?.filters?.rules),
      }))
    : []
  Object.keys(attributionEventFilterExpanded).forEach((key) => { delete attributionEventFilterExpanded[key] })
  sqlBuilder.attribution.events.forEach((item) => { attributionEventFilterExpanded[item.id] = false })
  attributionTargetFilterExpanded.value = false
  const ranking = value.ranking && typeof value.ranking === 'object' ? value.ranking : {}
  sqlBuilder.ranking.entityField = typeof ranking.entityField === 'string' ? ranking.entityField : ''
  sqlBuilder.ranking.metric = restoreRankingMetric(ranking.metric, 'ranking-primary-metric')
  sqlBuilder.ranking.tieHandling = ['default', 'skip', 'dense'].includes(ranking.tieHandling)
    ? ranking.tieHandling
    : 'default'
  sqlBuilder.ranking.simultaneousMetrics = Array.isArray(ranking.simultaneousMetrics)
    ? ranking.simultaneousMetrics.map((item: any, index: number) => restoreRankingMetric(item, `ranking-metric-${index}`))
    : []
  sqlBuilder.ranking.simultaneousProperties = Array.isArray(ranking.simultaneousProperties)
    ? ranking.simultaneousProperties.filter((item: any) => typeof item === 'string')
    : []
  sqlBuilder.dateExpressionPickerEnabled = true
  sqlBuilder.metricDateExpressionEnabled = value.metricDateExpressionEnabled === true
  const timeExpression = normalizeDashboardDateExpression(value.timeExpression)
  sqlBuilder.timeExpression = timeExpression || defaultDashboardDateExpression()
  sqlBuilder.groups = Array.isArray(value.groups)
    ? value.groups.filter((item: any) => typeof item === 'string')
    : []
  sqlBuilder.globalFilters = restoreBuilderFilters(value.globalFilters)
  sqlBuilder.globalFilterLogic = builderLogic(value.globalFilterLogic)
  sqlBuilder.approximate = value.approximate === true
  restoreBuilderAgentAdvice(value.agentAdvice)
}

function formulaTokensReferenceMetricIds(tokens: FormulaToken[], metricIds: Set<string>) {
  return (tokens || []).some((token) => token.type === 'metric' && metricIds.has(token.metricId))
}

function isAutoSeededMetricItem(item: SqlBuilderMetricItem, index: number) {
  const alias = String(item.alias || '').trim()
  return (
    (alias === '' || alias === `指标${index + 1}`) &&
    item.aggregation === 'count' &&
    !hasEffectiveBuilderFilters(item.filters || [])
  )
}

function pruneAutoSeededMetricItemsForFormulaOnlyBuilder() {
  if (!sqlBuilder.calculatedMetrics.length || !sqlBuilder.metricItems.length) {
    return
  }
  const outputFields = new Set([...form.columns, ...form.y].map((item) => String(item || '').trim()).filter(Boolean))
  const metricIds = new Set(sqlBuilder.metricItems.map((item) => item.id))
  const hasMetricTokenReference = sqlBuilder.calculatedMetrics.some((item) =>
    formulaTokensReferenceMetricIds(item.tokens || [], metricIds)
  )
  if (hasMetricTokenReference) {
    return
  }
  const nextItems = sqlBuilder.metricItems.filter((item, index) => {
    if (!isAutoSeededMetricItem(item, index)) {
      return true
    }
    const alias = metricOutputAlias(item, index)
    return outputFields.has(alias) || outputFields.has(item.alias)
  })
  if (nextItems.length !== sqlBuilder.metricItems.length) {
    sqlBuilder.metricItems = nextItems
  }
}

function fieldOptionByValue(value: string) {
  return fieldOptionIndex.value.find(value)
}

function retentionPropertyOptions(eventValue: string) {
  return eventFilterFieldOptions(eventValue)
}

function handleRetentionEventPropertyChange(type: 'initial' | 'return' | 'simultaneous', eventValue: string) {
  if (type === 'initial') {
    const previousEventValue = sqlBuilder.retention.initialEvent
    const hadScopedConfig = Boolean(
      sqlBuilder.retention.initialEventAlias.trim()
      || sqlBuilder.retention.initialEventFilters.length
    )
    sqlBuilder.retention.initialEvent = eventValue
    if (previousEventValue !== eventValue) {
      sqlBuilder.retention.initialEventAlias = ''
      sqlBuilder.retention.initialEventFilters = []
      sqlBuilder.retention.initialEventFilterLogic = 'and'
      retentionFilterExpanded.initial = false
      retentionAliasEditing.initial = false
      retentionAliasDraft.initial = ''
      if (hadScopedConfig) {
        ElMessage.warning('初始事件已切换，原重命名和筛选条件已清除。')
      }
    }
  } else if (type === 'return') {
    const previousEventValue = sqlBuilder.retention.returnEvent
    const hadScopedConfig = Boolean(
      sqlBuilder.retention.returnEventAlias.trim()
      || sqlBuilder.retention.returnEventFilters.length
    )
    sqlBuilder.retention.returnEvent = eventValue
    if (previousEventValue !== eventValue) {
      sqlBuilder.retention.returnEventAlias = ''
      sqlBuilder.retention.returnEventFilters = []
      sqlBuilder.retention.returnEventFilterLogic = 'and'
      retentionFilterExpanded.return = false
      retentionAliasEditing.return = false
      retentionAliasDraft.return = ''
      if (hadScopedConfig) {
        ElMessage.warning('回访事件已切换，原重命名和筛选条件已清除。')
      }
    }
  } else {
    sqlBuilder.retention.simultaneous.event = eventValue
    syncRetentionSimultaneousMetricField()
  }
  const propertyKey = type === 'initial'
    ? 'initialProperty'
    : type === 'return'
      ? 'returnProperty'
      : 'simultaneousProperty'
  const propertyValue = sqlBuilder.retention.relatedProperty[propertyKey]
  if (propertyValue && !optionExists(propertyValue, retentionPropertyOptions(eventValue))) {
    sqlBuilder.retention.relatedProperty[propertyKey] = ''
  }
}

function handleRetentionSimultaneousToggle(enabled: boolean) {
  if (enabled) return
  sqlBuilder.retention.simultaneous.event = ''
  sqlBuilder.retention.simultaneous.aggregation = 'count'
  sqlBuilder.retention.simultaneous.metricField = ''
  sqlBuilder.retention.relatedProperty.simultaneousProperty = ''
}

function retentionSimultaneousMetricFieldOptions() {
  return metricMeasureFieldOptions({
    field: sqlBuilder.retention.simultaneous.event,
    aggregation: sqlBuilder.retention.simultaneous.aggregation,
  })
}

function syncRetentionSimultaneousMetricField() {
  const simultaneous = sqlBuilder.retention.simultaneous
  if (simultaneous.aggregation === 'count') {
    simultaneous.metricField = ''
    return
  }
  if (!optionExists(simultaneous.metricField, retentionSimultaneousMetricFieldOptions())) {
    simultaneous.metricField = ''
  }
}

function handleRetentionRelatedPropertyToggle(enabled: boolean) {
  if (enabled) return
  sqlBuilder.retention.relatedProperty.initialProperty = ''
  sqlBuilder.retention.relatedProperty.returnProperty = ''
  sqlBuilder.retention.relatedProperty.simultaneousProperty = ''
  sqlBuilder.retention.relatedProperty.asGroup = false
}

function builderFieldLabel(value: string) {
  const option = fieldOptionByValue(value)
  if (!option) {
    return value || '未选择'
  }
  const name = option.displayName || option.label || option.comment || option.field || value
  const path = option.value || [option.table, option.field].filter(Boolean).join('.')
  return path && path !== name ? `${name} ${path}` : name
}

function quotedBuilderFieldLabel(value: string) {
  return `「${builderFieldLabel(value)}」`
}

function builderAggregationLabel(value: string) {
  return builderAggregationOptions.find((option) => option.value === value)?.label || value || '未选择'
}

function builderTimeGrainLabel(value: string) {
  return builderTimeGrainOptions.find((option) => option.value === value)?.label || value || '未选择'
}

function builderFilterOperatorLabel(value: string) {
  return builderFilterOperatorOptions.find((option) => option.value === value)?.label || value || '等于'
}

function recommendedMetricField(item: SqlBuilderMetricItem, preferredTable = '') {
  const current = fieldOptionByValue(metricMeasureField(item))
  if (preferredTable && current && current.table !== preferredTable) {
    return fieldOptionByValue(item.field) || current
  }
  return current || fieldOptionByValue(item.field)
}

function eventFilterFieldOptions(eventValue: string) {
  const eventOption = fieldOptionByValue(eventValue)
  return eventScopedPropertyOptions({
    eventOption,
    eventProperties: eventOption?.eventName
      ? trackingEventPropertyOptionsByEvent.value.get(eventOption.eventName) || []
      : [],
    userProperties: eventUserPropertyOptions.value,
    activeEventTable: eventFieldScope.value.status === 'active'
      ? eventFieldScope.value.defaultEventTable
      : '',
  })
}

function metricFilterFieldOptions(item: SqlBuilderMetricItem) {
  return eventFilterFieldOptions(item.field)
}

function retentionEventFilterFieldOptions(target: RetentionEventTarget) {
  return eventFilterFieldOptions(
    target === 'initial' ? sqlBuilder.retention.initialEvent : sqlBuilder.retention.returnEvent
  )
}

function retentionEventDefaultDisplayName(eventValue: string) {
  const option = fieldOptionByValue(eventValue)
  return option?.displayName || option?.label || option?.eventName || '事件名称'
}

function beginRetentionEventRename(target: RetentionEventTarget) {
  const eventValue = target === 'initial' ? sqlBuilder.retention.initialEvent : sqlBuilder.retention.returnEvent
  if (!eventValue) return
  retentionAliasDraft[target] = target === 'initial'
    ? sqlBuilder.retention.initialEventAlias
    : sqlBuilder.retention.returnEventAlias
  retentionAliasEditing[target] = true
}

function finishRetentionEventRename(target: RetentionEventTarget) {
  if (!retentionAliasEditing[target]) return
  const alias = retentionAliasDraft[target].trim()
  if (target === 'initial') {
    sqlBuilder.retention.initialEventAlias = alias
  } else {
    sqlBuilder.retention.returnEventAlias = alias
  }
  retentionAliasEditing[target] = false
}

function cancelRetentionEventRename(target: RetentionEventTarget) {
  retentionAliasEditing[target] = false
  retentionAliasDraft[target] = ''
}

function toggleRetentionEventFilter(target: RetentionEventTarget) {
  const eventValue = target === 'initial' ? sqlBuilder.retention.initialEvent : sqlBuilder.retention.returnEvent
  if (!eventValue) return
  const filters = target === 'initial'
    ? sqlBuilder.retention.initialEventFilters
    : sqlBuilder.retention.returnEventFilters
  if (!retentionFilterExpanded[target] && !filters.length) {
    filters.push(emptyBuilderFilter())
  }
  retentionFilterExpanded[target] = !retentionFilterExpanded[target]
}

function metricMeasureFieldOptions(item: Pick<SqlBuilderMetricItem, 'field'> & { aggregation?: string }) {
  const eventOption = fieldOptionByValue(item.field)
  let options: SchemaFieldOption[]
  if (eventOption?.kind === 'tracking-event' && eventOption.eventName) {
    const eventProperties = trackingEventPropertyOptionsByEvent.value.get(eventOption.eventName) || []
    options = [
      ...eventProperties,
      ...eventDetailFieldOptions(eventOption.eventTable || eventOption.table),
    ]
  } else {
    options = builderFieldOptions.value
  }
  return ['sum', 'avg'].includes(item.aggregation || '')
    ? options.filter(isNumericFieldOption)
    : options
}

function eventDetailFieldOptions(eventTable: string) {
  if (!eventTable) {
    return []
  }
  return builderFieldOptions.value
    .filter((option) => option.table === eventTable)
    .map((option) => ({
      ...option,
      tableReferenceLabel: option.tableReferenceLabel || option.tableLabel || option.tableComment,
    }))
}

function defaultMetricFieldForEvent(field: string) {
  void field
  return ''
}

function recommendedMetricAlias(item: SqlBuilderMetricItem, index: number) {
  const alias = metricOutputAlias(item, index)
  if (!/^指标\d+$/.test(alias)) {
    return alias
  }
  return alias
}

function describeBuilderMetricConfig(item: SqlBuilderMetricItem, index: number, preferredTable = '') {
  const alias = recommendedMetricAlias(item, index)
  const recommendedField = recommendedMetricField(item, preferredTable)
  const field = quotedBuilderFieldLabel(recommendedField?.value || item.field || metricMeasureField(item))
  const aggregation = builderAggregationLabel(item.aggregation)
  const metricField = item.aggregation === 'count'
    ? ''
    : `，计算字段选 ${quotedBuilderFieldLabel(recommendedField?.value || metricMeasureField(item))}`
  return `分析指标${index + 1}：字段选 ${field}，聚合选「${aggregation}」${metricField}，别名填「${alias}」`
}

function inferBuilderIntentText() {
  if (isRevenueAnalysis.value) {
    return `按同期初始事件分析 ${clampRevenueObservationDays(sqlBuilder.revenue.observationDays)} 天收入。`
  }
  const metrics = sqlBuilder.metricItems
    .map((item, index) => metricOutputAlias(item, index))
    .filter(Boolean)
    .join('、')
  const groups = sqlBuilder.groups.filter(Boolean).map(builderFieldLabel).join('、')
  const timeText = sqlBuilder.timeField
    ? `按${builderTimeGrainLabel(sqlBuilder.timeGrain)}看 ${metrics || '指标'}`
    : `看 ${metrics || '当前配置指标'}`
  return groups ? `${timeText}，并按 ${groups} 分组。` : `${timeText}。`
}

function sqlFieldExpression(value: string) {
  const option = fieldOptionByValue(value)
  if (option?.expression) return option.expression
  if (option?.table && option?.field) return `${quoteIdentifier(option.table)}.${quoteIdentifier(option.field)}`
  const [table, ...fieldParts] = String(value || '').split('.')
  const field = fieldParts.join('.')
  if (table && field) return `${quoteIdentifier(table)}.${quoteIdentifier(field)}`
  return value ? quoteIdentifier(value) : ''
}

function sqlAlias(value: string, fallback: string) {
  const clean = String(value || fallback || 'metric').replace(/[^\w\u4e00-\u9fa5]+/g, '_').replace(/^_+|_+$/g, '')
  return clean || fallback
}

function escapeRegExp(value: string) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function normalizeSqlExpressionForMatch(value: string) {
  return String(value || '')
    .replace(/[`"\[\]]/g, '')
    .replace(/\s+/g, '')
    .toLowerCase()
}

function sqlExpressionPattern(expr: string) {
  const compact = normalizeSqlExpressionForMatch(expr)
  if (!compact) {
    return ''
  }
  return compact
    .split('.')
    .map((part) => `[\\\`"\\[]?${escapeRegExp(part)}[\\\`"\\]]?`)
    .join('\\s*\\.\\s*')
}

function decodeSqlLiteral(value: string) {
  const text = String(value || '').trim()
  const quotedMatch = text.match(/^'((?:''|[^'])*)'$/)
  if (quotedMatch) {
    return quotedMatch[1].replace(/''/g, "'")
  }
  return text
}

function recoverFilterFromSqlSegment(field: string, fieldPattern: string, searchSql: string, options: { numeric?: boolean } = {}) {
  const valuePattern = "('(?:''|[^'])*'|-?\\d+(?:\\.\\d+)?)"
  const binaryMatch = searchSql.match(new RegExp(`${fieldPattern}\\s*(=|<>|!=|>|<)\\s*${valuePattern}`, 'i'))
  if (binaryMatch) {
    const rawValue = binaryMatch[2] || ''
    if (!options.numeric && !rawValue.trim().startsWith("'")) {
      return null
    }
    const operatorMap: Record<string, string> = {
      '=': 'eq',
      '<>': 'ne',
      '!=': 'ne',
      '>': 'gt',
      '<': 'lt',
    }
    return {
      ...emptyBuilderFilter(),
      field,
      operator: operatorMap[binaryMatch[1]] || 'eq',
      value: decodeSqlLiteral(binaryMatch[2]),
    }
  }
  const likeMatch = searchSql.match(new RegExp(`${fieldPattern}\\s+LIKE\\s+'%((?:''|[^'])*)%'`, 'i'))
  if (likeMatch) {
    return {
      ...emptyBuilderFilter(),
      field,
      operator: 'contains',
      value: likeMatch[1].replace(/''/g, "'"),
    }
  }
  const nullMatch = searchSql.match(new RegExp(`${fieldPattern}\\s+IS\\s+(NOT\\s+)?NULL`, 'i'))
  if (nullMatch) {
    return {
      ...emptyBuilderFilter(),
      field,
      operator: nullMatch[1] ? 'is_not_null' : 'is_null',
      value: '',
    }
  }
  return null
}

function recoveredFilterFromSql(field: string): SqlBuilderFilter | null {
  const expr = sqlFieldExpression(field)
  const fieldPattern = sqlExpressionPattern(expr)
  if (!fieldPattern || !form.sql.trim()) {
    return null
  }
  const selectMatch = form.sql.match(/\bselect\b([\s\S]*?)\bfrom\b/i)
  const selectSql = selectMatch?.[1] || ''
  if (selectSql.trim()) {
    const selectFilter = recoverFilterFromSqlSegment(field, fieldPattern, selectSql, { numeric: true })
    if (selectFilter) {
      return selectFilter
    }
  }
  return recoverFilterFromSqlSegment(field, fieldPattern, form.sql)
}

function recoverMissingMetricFiltersFromSql() {
  if (!form.sql.trim() || !schemaFieldOptions.value.length) {
    return false
  }
  let recovered = false
  sqlBuilder.metricItems.forEach((item) => {
    if (hasEffectiveBuilderFilters(item.filters || [])) {
      return
    }
    const metricFieldOption = fieldOptionByValue(item.field)
    const candidates = metricFilterRecoveryCandidates({
      metricField: item.field,
      metricMeasureField: metricMeasureField(item),
      metricFieldOption,
      selectableFilterOptions: metricFilterFieldOptions(item),
      schemaFieldOptions: schemaFieldOptions.value,
    })
    const restored = candidates
      .map((field) => recoveredFilterFromSql(field))
      .find((filter) => filter && isEffectiveBuilderFilter(filter))
    if (restored) {
      item.filters = [restored]
      recovered = true
    }
  })
  return recovered
}

function optionExists(value: string, options: Array<{ value: string }>) {
  return !value || options.some((option) => option.value === value)
}

function filterFieldValues(filters: SqlBuilderFilter[]): string[] {
  const fields: string[] = []
  const visit = (nodes: SqlBuilderFilter[]) => {
    nodes.forEach((node) => {
      if (node.field) {
        fields.push(node.field)
      }
      if (Array.isArray(node.children)) {
        visit(node.children)
      }
    })
  }
  visit(filters || [])
  return fields
}

function appendEventScopeFilterIssues(
  filters: SqlBuilderFilter[],
  prefix: string,
  issues: string[]
) {
  ;(filters || []).forEach((filter, index) => {
    const location = `${prefix}[${index}]`
    if (filter.type === 'group' || Array.isArray(filter.children)) {
      appendEventScopeFilterIssues(filter.children || [], `${location}.children`, issues)
      return
    }
    appendEventScopeFieldIssue(filter.field, `${location}.field`, issues)
  })
}

function appendEventScopeFieldIssue(value: string, location: string, issues: string[]) {
  if (!value || eventFieldScope.value.mode !== 'event') {
    return
  }
  if (eventFieldScope.value.status !== 'active') {
    return
  }
  const option = fieldOptionByValue(value)
  if (!option) {
    issues.push(`${location}：字段 ${value} 不在当前可用 Schema 中。`)
    return
  }
  const tableName = option.eventTable || option.table
  if (tableName && tableName !== eventFieldScope.value.defaultEventTable) {
    issues.push(
      `${location}：当前事件模式不允许使用表 ${tableName}，仅允许 ${eventFieldScope.value.defaultEventTable}。`
    )
  }
}

function builderEventScopeIssues() {
  if (eventFieldScope.value.mode !== 'event') {
    return []
  }
  if (eventFieldScope.value.status !== 'active') {
    return [eventFieldScope.value.message || '当前事件配置不可用。']
  }
  const issues: string[] = []
  appendEventScopeFieldIssue(sqlBuilder.timeField, 'time.field', issues)
  sqlBuilder.metricItems.forEach((item, index) => {
    appendEventScopeFieldIssue(item.field, `metric[${index}].field`, issues)
    if (item.aggregation !== 'count') {
      appendEventScopeFieldIssue(item.metric, `metric[${index}].metricField`, issues)
    }
    appendEventScopeFilterIssues(item.filters || [], `metric[${index}].filter`, issues)
  })
  sqlBuilder.calculatedMetrics.forEach((item, formulaIndex) => {
    item.tokens.forEach((token, tokenIndex) => {
      if (token.type !== 'atomicMetric') return
      appendEventScopeFieldIssue(token.metric.field, `formula[${formulaIndex}].token[${tokenIndex}].field`, issues)
      if (token.metric.aggregation !== 'count') {
        appendEventScopeFieldIssue(token.metric.metric, `formula[${formulaIndex}].token[${tokenIndex}].metricField`, issues)
      }
      appendEventScopeFilterIssues(
        (token.metric.filters || []) as SqlBuilderFilter[],
        `formula[${formulaIndex}].token[${tokenIndex}].filter`,
        issues
      )
    })
  })
  if (isRetentionAnalysis.value) {
    if (sqlBuilder.retention.simultaneous.enabled && sqlBuilder.retention.simultaneous.aggregation !== 'count') {
      appendEventScopeFieldIssue(
        sqlBuilder.retention.simultaneous.metricField,
        'retention.simultaneous.metricField',
        issues
      )
    }
    appendEventScopeFilterIssues(sqlBuilder.retention.initialEventFilters, 'retention.initial_event_filter', issues)
    appendEventScopeFilterIssues(sqlBuilder.retention.returnEventFilters, 'retention.return_event_filter', issues)
  }
  if (isDistributionAnalysis.value) {
    if (sqlBuilder.distribution.metric.kind === 'property') {
      appendEventScopeFieldIssue(sqlBuilder.distribution.metric.field, 'distribution.metric.field', issues)
    }
    if (sqlBuilder.distribution.simultaneous.enabled && sqlBuilder.distribution.simultaneous.aggregation !== 'count') {
      appendEventScopeFieldIssue(
        sqlBuilder.distribution.simultaneous.metricField,
        'distribution.simultaneous.metricField',
        issues
      )
    }
    appendEventScopeFilterIssues(sqlBuilder.distribution.eventFilters, 'distribution.event_filter', issues)
  }
  if (isIntervalAnalysis.value) {
    appendEventScopeFieldIssue(sqlBuilder.interval.relatedProperty.startProperty, 'interval.related_property.start', issues)
    appendEventScopeFieldIssue(sqlBuilder.interval.relatedProperty.endProperty, 'interval.related_property.end', issues)
    appendEventScopeFilterIssues(sqlBuilder.interval.startEventFilters, 'interval.start_event_filter', issues)
    appendEventScopeFilterIssues(sqlBuilder.interval.endEventFilters, 'interval.end_event_filter', issues)
  }
  if (isPathAnalysis.value) {
    sqlBuilder.path.events.forEach((item, index) => {
      appendEventScopeFieldIssue(item.event, `path.events[${index}].event`, issues)
      item.splitProperties.forEach((field, splitIndex) => {
        appendEventScopeFieldIssue(field, `path.events[${index}].splitProperties[${splitIndex}]`, issues)
      })
    })
  }
  if (isAttributionAnalysis.value) {
    appendEventScopeFieldIssue(sqlBuilder.attribution.targetMetric.metricField, 'attribution.target_metric.field', issues)
    appendEventScopeFilterIssues(sqlBuilder.attribution.targetEventFilters, 'attribution.target_event_filter', issues)
    sqlBuilder.attribution.events.forEach((item, index) => {
      appendEventScopeFieldIssue(item.event, `attribution.events[${index}].event`, issues)
      appendEventScopeFilterIssues(item.filters, `attribution.events[${index}].filter`, issues)
    })
  }
  if (isRankingAnalysis.value) {
    appendEventScopeFieldIssue(sqlBuilder.ranking.metric.event, 'ranking.metric.event', issues)
    if (sqlBuilder.ranking.metric.aggregation !== 'count') {
      appendEventScopeFieldIssue(sqlBuilder.ranking.metric.metricField, 'ranking.metric.metricField', issues)
    }
    sqlBuilder.ranking.simultaneousMetrics.forEach((item, index) => {
      appendEventScopeFieldIssue(item.event, `ranking.simultaneousMetrics[${index}].event`, issues)
      if (item.aggregation !== 'count') {
        appendEventScopeFieldIssue(item.metricField, `ranking.simultaneousMetrics[${index}].metricField`, issues)
      }
    })
  }
  sqlBuilder.groups.forEach((field, index) => appendEventScopeFieldIssue(field, `group[${index}]`, issues))
  appendEventScopeFilterIssues(sqlBuilder.globalFilters, 'global_filter', issues)
  return unique(issues)
}

function appendFilterRangeIssues(
  filters: SqlBuilderFilter[],
  allowedOptions: SchemaFieldOption[],
  prefix: string,
  issues: string[]
) {
  const allowedValues = new Set(
    allowedOptions.flatMap((option) => [option.value, option.field]).filter(Boolean)
  )
  filterFieldValues(filters).forEach((field, index) => {
    if (!allowedValues.has(field)) {
      issues.push(`${prefix}[${index}].field：字段不属于当前筛选范围：${field}。`)
    }
  })
}

function builderFilterScopeIssues() {
  if (eventFieldScope.value.status !== 'active') {
    return []
  }
  const issues: string[] = []
  sqlBuilder.metricItems.forEach((item, index) => {
    appendFilterRangeIssues(item.filters || [], metricFilterFieldOptions(item), `metric[${index}].filter`, issues)
  })
  sqlBuilder.calculatedMetrics.forEach((item, formulaIndex) => {
    item.tokens.forEach((token, tokenIndex) => {
      if (token.type !== 'atomicMetric') return
      appendFilterRangeIssues(
        (token.metric.filters || []) as SqlBuilderFilter[],
        metricFilterFieldOptions(token.metric as SqlBuilderMetricItem),
        `formula[${formulaIndex}].token[${tokenIndex}].filter`,
        issues
      )
    })
  })
  if (isRetentionAnalysis.value) {
    appendFilterRangeIssues(
      sqlBuilder.retention.initialEventFilters,
      retentionEventFilterFieldOptions('initial'),
      'retention.initial_event_filter',
      issues
    )
    appendFilterRangeIssues(
      sqlBuilder.retention.returnEventFilters,
      retentionEventFilterFieldOptions('return'),
      'retention.return_event_filter',
      issues
    )
  }
  if (isDistributionAnalysis.value) {
    appendFilterRangeIssues(
      sqlBuilder.distribution.eventFilters,
      distributionEventPropertyOptions.value,
      'distribution.event_filter',
      issues
    )
  }
  if (isIntervalAnalysis.value) {
    appendFilterRangeIssues(
      sqlBuilder.interval.startEventFilters,
      intervalEventFilterFieldOptions('start'),
      'interval.start_event_filter',
      issues
    )
    appendFilterRangeIssues(
      sqlBuilder.interval.endEventFilters,
      intervalEventFilterFieldOptions('end'),
      'interval.end_event_filter',
      issues
    )
  }
  if (isAttributionAnalysis.value) {
    appendFilterRangeIssues(
      sqlBuilder.attribution.targetEventFilters,
      eventFilterFieldOptions(sqlBuilder.attribution.targetEvent),
      'attribution.target_event_filter',
      issues
    )
    sqlBuilder.attribution.events.forEach((item, index) => {
      appendFilterRangeIssues(
        item.filters,
        eventFilterFieldOptions(item.event),
        `attribution.events[${index}].filter`,
        issues
      )
    })
  }
  appendFilterRangeIssues(sqlBuilder.globalFilters, eventUserPropertyOptions.value, 'global_filter', issues)
  return unique(issues)
}

function fixedSqlEditorTimeFieldIssue() {
  if (!hasSqlSource.value || schemaLoading.value || schemaFieldOptions.value.length === 0) {
    return ''
  }
  const hasFixedField = schemaFieldOptions.value.some((option) => (
    option.field === SQL_EDITOR_TIME_FIELD || option.value === SQL_EDITOR_TIME_FIELD
  ))
  return hasFixedField ? '' : '当前执行数据源缺少固定时间字段 dt。'
}

function blockMissingFixedTimeField() {
  const issue = fixedSqlEditorTimeFieldIssue()
  if (!issue) {
    return false
  }
  ElMessage.warning(issue)
  return true
}

function builderBlockingScopeIssues() {
  return unique([
    ...builderEventScopeIssues(),
    ...builderFilterScopeIssues(),
  ].filter(Boolean))
}

function resetRetentionConfig() {
  sqlBuilder.retention.entityField = ''
  sqlBuilder.retention.initialEvent = ''
  sqlBuilder.retention.initialEventAlias = ''
  sqlBuilder.retention.initialEventFilterLogic = 'and'
  sqlBuilder.retention.initialEventFilters = []
  sqlBuilder.retention.returnEvent = ''
  sqlBuilder.retention.returnEventAlias = ''
  sqlBuilder.retention.returnEventFilterLogic = 'and'
  sqlBuilder.retention.returnEventFilters = []
  retentionFilterExpanded.initial = false
  retentionFilterExpanded.return = false
  retentionAliasEditing.initial = false
  retentionAliasEditing.return = false
  retentionAliasDraft.initial = ''
  retentionAliasDraft.return = ''
  sqlBuilder.retention.simultaneous.enabled = false
  sqlBuilder.retention.simultaneous.event = ''
  sqlBuilder.retention.simultaneous.aggregation = 'count'
  sqlBuilder.retention.simultaneous.metricField = ''
  sqlBuilder.retention.relatedProperty.enabled = false
  sqlBuilder.retention.relatedProperty.initialProperty = ''
  sqlBuilder.retention.relatedProperty.returnProperty = ''
  sqlBuilder.retention.relatedProperty.simultaneousProperty = ''
  sqlBuilder.retention.relatedProperty.asGroup = false
}

function createFunnelStep(): SqlBuilderFunnelStep {
  return {
    id: nodeId('funnel-step'),
    event: '',
    alias: '',
    filterLogic: 'and',
    filters: [],
    relatedProperty: '',
  }
}

function resetFunnelConfig() {
  sqlBuilder.funnel.entityField = ''
  sqlBuilder.funnel.steps = [createFunnelStep(), createFunnelStep(), createFunnelStep()]
  sqlBuilder.funnel.window = { ...DEFAULT_FUNNEL_WINDOW }
  sqlBuilder.funnel.relatedPropertyEnabled = false
  Object.keys(funnelFilterExpanded).forEach((key) => { delete funnelFilterExpanded[key] })
  Object.keys(funnelAliasEditing).forEach((key) => { delete funnelAliasEditing[key] })
  Object.keys(funnelAliasDraft).forEach((key) => { delete funnelAliasDraft[key] })
  sqlBuilder.funnel.steps.forEach((step) => {
    funnelFilterExpanded[step.id] = false
    funnelAliasEditing[step.id] = false
    funnelAliasDraft[step.id] = ''
  })
}

function resetDistributionConfig() {
  sqlBuilder.distribution.entityField = ''
  sqlBuilder.distribution.event = ''
  sqlBuilder.distribution.eventFilterLogic = 'and'
  sqlBuilder.distribution.eventFilters = []
  sqlBuilder.distribution.metric = { kind: 'count', field: '', aggregation: 'sum' }
  sqlBuilder.distribution.interval = { mode: 'discrete', customBounds: [] }
  sqlBuilder.distribution.simultaneous.enabled = false
  sqlBuilder.distribution.simultaneous.event = ''
  sqlBuilder.distribution.simultaneous.aggregation = 'count'
  sqlBuilder.distribution.simultaneous.metricField = ''
  distributionFilterExpanded.value = false
}

function resetIntervalConfig() {
  sqlBuilder.interval.entityField = ''
  sqlBuilder.interval.startEvent = ''
  sqlBuilder.interval.startEventFilterLogic = 'and'
  sqlBuilder.interval.startEventFilters = []
  sqlBuilder.interval.endEvent = ''
  sqlBuilder.interval.endEventFilterLogic = 'and'
  sqlBuilder.interval.endEventFilters = []
  sqlBuilder.interval.relatedProperty.enabled = false
  sqlBuilder.interval.relatedProperty.startProperty = ''
  sqlBuilder.interval.relatedProperty.endProperty = ''
  sqlBuilder.interval.limitSeconds = DEFAULT_INTERVAL_LIMIT_SECONDS
  intervalFilterExpanded.start = false
  intervalFilterExpanded.end = false
}

function resetPathConfig() {
  sqlBuilder.path.events = [{ id: 'path-event-initial', event: '', splitProperties: [] }]
  sqlBuilder.path.initialEvent = ''
  sqlBuilder.path.sessionGapSeconds = DEFAULT_PATH_SESSION_GAP_SECONDS
}

function resetRevenueConfig() {
  sqlBuilder.revenue.entityField = ''
  sqlBuilder.revenue.initialEvent = ''
  sqlBuilder.revenue.paymentEvent = ''
  sqlBuilder.revenue.metric = { method: 'count', field: '' }
  sqlBuilder.revenue.costEnabled = false
  sqlBuilder.revenue.costField = ''
  sqlBuilder.revenue.observationDays = DEFAULT_REVENUE_OBSERVATION_DAYS
}

function createAttributionEvent(): SqlBuilderAttributionEvent {
  return {
    id: nodeId('attribution-event'),
    event: '',
    filterLogic: 'and',
    filters: [],
  }
}

function resetAttributionConfig() {
  sqlBuilder.attribution.entityField = ''
  sqlBuilder.attribution.method = 'linear'
  sqlBuilder.attribution.window = { ...DEFAULT_ATTRIBUTION_WINDOW }
  sqlBuilder.attribution.targetEvent = ''
  sqlBuilder.attribution.targetEventFilterLogic = 'and'
  sqlBuilder.attribution.targetEventFilters = []
  sqlBuilder.attribution.targetMetric.aggregation = 'count'
  sqlBuilder.attribution.targetMetric.metricField = ''
  sqlBuilder.attribution.includeDirect = true
  sqlBuilder.attribution.events = [createAttributionEvent()]
  attributionTargetFilterExpanded.value = false
  Object.keys(attributionEventFilterExpanded).forEach((key) => { delete attributionEventFilterExpanded[key] })
  sqlBuilder.attribution.events.forEach((item) => { attributionEventFilterExpanded[item.id] = false })
}

function resetRankingConfig() {
  sqlBuilder.ranking.entityField = ''
  sqlBuilder.ranking.metric = createRankingMetric('ranking-primary-metric')
  sqlBuilder.ranking.tieHandling = 'default'
  sqlBuilder.ranking.simultaneousMetrics = []
  sqlBuilder.ranking.simultaneousProperties = []
}

function handleRankingMetricChange(metric: SqlBuilderRankingMetric, eventValue: string) {
  if (metric.event === eventValue) return
  metric.event = eventValue
  metric.metricField = ''
}

function syncRankingMetricField(metric: SqlBuilderRankingMetric) {
  if (metric.aggregation === 'count') {
    metric.metricField = ''
    return
  }
  if (!optionExists(metric.metricField, rankingMetricFieldOptions(metric))) {
    metric.metricField = ''
  }
}

function addRankingMetric() {
  sqlBuilder.ranking.simultaneousMetrics.push(createRankingMetric())
}

function removeRankingMetric(index: number) {
  sqlBuilder.ranking.simultaneousMetrics.splice(index, 1)
}

function handleAnalysisModelChange(model: AnalysisModel) {
  sqlBuilder.analysisModel = ['retention', 'funnel', 'distribution', 'interval', 'path', 'revenue', 'attribution', 'ranking'].includes(model) ? model : 'event'
  if (sqlBuilder.analysisModel === 'retention') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'funnel') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'funnel'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'distribution') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'interval') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'path') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'sankey'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'revenue') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'attribution') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else if (sqlBuilder.analysisModel === 'ranking') {
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    activeFormulaMetricId.value = ''
    form.chartType = 'table'
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
  } else {
    resetRetentionConfig()
    resetFunnelConfig()
    resetDistributionConfig()
    resetIntervalConfig()
    resetPathConfig()
    resetRevenueConfig()
    resetAttributionConfig()
    resetRankingConfig()
    sqlBuilder.metricItems = []
    sqlBuilder.calculatedMetrics = []
    addMetricItem()
  }
  sqlBuilder.groups = sqlBuilder.groups.filter((field) => optionExists(field, builderFieldOptions.value))
  lastPreviewSignature.value = ''
}

function handleRevenuePaymentEventChange(eventValue: string) {
  const changed = sqlBuilder.revenue.paymentEvent !== eventValue
  sqlBuilder.revenue.paymentEvent = eventValue
  if (!changed) return
  sqlBuilder.revenue.metric.field = ''
  sqlBuilder.revenue.costField = ''
}

function updateRevenueMetric(metric: RevenueMetricConfig) {
  sqlBuilder.revenue.metric = { ...metric }
  if (!revenueMetricUsesProperty(metric.method)) {
    sqlBuilder.revenue.metric.field = ''
  }
}

function handleRevenueCostToggle(enabled: boolean) {
  if (!enabled) sqlBuilder.revenue.costField = ''
}

function revenueBlockingIssues() {
  if (!isRevenueAnalysis.value) return []
  const issues: string[] = []
  const revenue = sqlBuilder.revenue
  if (!revenue.entityField) issues.push('收入分析请先选择分析主体。')
  if (!revenue.initialEvent) issues.push('收入分析请先选择同期初始事件。')
  if (!revenue.paymentEvent) issues.push('收入分析请先选择付费事件。')
  if (revenueMetricUsesProperty(revenue.metric.method) && !revenue.metric.field) {
    issues.push('收入分析使用事件属性口径时，请先选择数值属性。')
  }
  if (revenue.costEnabled && !revenue.costField) issues.push('收入分析启用成本数据时，请先选择成本字段。')
  if (revenue.observationDays < REVENUE_OBSERVATION_MIN_DAYS
    || revenue.observationDays > REVENUE_OBSERVATION_MAX_DAYS) {
    issues.push('收入分析观察时长必须在 1 到 365 天之间。')
  }
  return issues
}

function sanitizeRevenueConfig() {
  if (!isRevenueAnalysis.value) return
  const cleared: string[] = []
  const revenue = sqlBuilder.revenue
  if (revenue.entityField && !optionExists(revenue.entityField, revenueEntityFieldOptions.value)) {
    revenue.entityField = ''
    cleared.push('分析主体')
  }
  if (revenue.initialEvent && !optionExists(revenue.initialEvent, revenueEventOptions.value)) {
    revenue.initialEvent = ''
    cleared.push('同期初始事件')
  }
  if (revenue.paymentEvent && !optionExists(revenue.paymentEvent, revenueEventOptions.value)) {
    revenue.paymentEvent = ''
    revenue.metric.field = ''
    revenue.costField = ''
    cleared.push('付费事件')
  }
  if (revenue.metric.field && !optionExists(revenue.metric.field, revenueNumericPropertyOptions.value)) {
    revenue.metric.field = ''
    cleared.push('收入口径属性')
  }
  if (revenue.costField && !optionExists(revenue.costField, revenueNumericPropertyOptions.value)) {
    revenue.costField = ''
    cleared.push('成本字段')
  }
  revenue.observationDays = clampRevenueObservationDays(revenue.observationDays)
  if (cleared.length) ElMessage.warning(`${cleared.join('、')}在当前数据源中无效，已清除，请重新选择。`)
}

function handleDistributionEventChange(eventValue: string) {
  const changed = sqlBuilder.distribution.event !== eventValue
  sqlBuilder.distribution.event = eventValue
  if (!changed) return
  sqlBuilder.distribution.eventFilters = []
  sqlBuilder.distribution.eventFilterLogic = 'and'
  sqlBuilder.distribution.metric = { kind: 'count', field: '', aggregation: 'sum' }
  distributionFilterExpanded.value = false
}

function updateDistributionMetric(metric: DistributionMetricConfig) {
  const previousKind = sqlBuilder.distribution.metric.kind
  sqlBuilder.distribution.metric = { ...metric }
  if (metric.kind === 'count') {
    sqlBuilder.distribution.interval = { mode: 'discrete', customBounds: [] }
  } else if (previousKind === 'count') {
    sqlBuilder.distribution.interval = { mode: 'auto', customBounds: [] }
  }
}

function effectiveDistributionInterval(): DistributionIntervalConfig {
  if (sqlBuilder.distribution.metric.kind === 'count') {
    return { mode: 'discrete', customBounds: [] }
  }
  return {
    mode: sqlBuilder.distribution.interval.mode,
    customBounds: [...sqlBuilder.distribution.interval.customBounds],
  }
}

function updateDistributionInterval(interval: DistributionIntervalConfig) {
  sqlBuilder.distribution.interval = {
    mode: interval.mode,
    customBounds: [...interval.customBounds],
  }
}

function toggleDistributionEventFilter() {
  if (!sqlBuilder.distribution.event) return
  if (!distributionFilterExpanded.value && !sqlBuilder.distribution.eventFilters.length) {
    sqlBuilder.distribution.eventFilters.push(emptyBuilderFilter())
  }
  distributionFilterExpanded.value = !distributionFilterExpanded.value
}

function distributionSimultaneousMetricFieldOptions() {
  return metricMeasureFieldOptions({
    field: sqlBuilder.distribution.simultaneous.event,
    aggregation: sqlBuilder.distribution.simultaneous.aggregation,
  })
}

function syncDistributionSimultaneousMetricField() {
  const simultaneous = sqlBuilder.distribution.simultaneous
  if (simultaneous.aggregation === 'count') {
    simultaneous.metricField = ''
    return
  }
  if (!optionExists(simultaneous.metricField, distributionSimultaneousMetricFieldOptions())) {
    simultaneous.metricField = ''
  }
}

function handleDistributionSimultaneousToggle(enabled: boolean) {
  if (enabled) return
  sqlBuilder.distribution.simultaneous.event = ''
  sqlBuilder.distribution.simultaneous.aggregation = 'count'
  sqlBuilder.distribution.simultaneous.metricField = ''
}

function distributionBlockingIssues() {
  if (!isDistributionAnalysis.value) return []
  const issues: string[] = []
  const distribution = sqlBuilder.distribution
  if (!distribution.entityField) issues.push('分布分析请先选择分析主体。')
  if (!distribution.event) issues.push('分布分析请先选择参与事件。')
  if (distribution.metric.kind === 'property' && !distribution.metric.field) {
    issues.push('分布分析选择事件属性指标时，请先选择事件属性。')
  }
  if (distribution.interval.mode === 'custom') {
    const bounds = distribution.interval.customBounds
    if (bounds.length < 2 || bounds.some((value, index) => index > 0 && value <= bounds[index - 1])) {
      issues.push('分布分析自定义区间至少需要两个严格递增的数字边界。')
    }
  }
  if (distribution.simultaneous.enabled && !distribution.simultaneous.event) {
    issues.push('分布分析使用同时展示时请选择参与事件。')
  }
  if (
    distribution.simultaneous.enabled
    && distribution.simultaneous.aggregation !== 'count'
    && !distribution.simultaneous.metricField
  ) {
    issues.push('分布分析同时展示使用非次数聚合时，请选择计算字段。')
  }
  return issues
}

function sanitizeDistributionConfig() {
  if (!isDistributionAnalysis.value) return
  const distribution = sqlBuilder.distribution
  const cleared: string[] = []
  if (distribution.entityField && !optionExists(distribution.entityField, distributionEntityFieldOptions.value)) {
    distribution.entityField = ''
    cleared.push('分析主体')
  }
  if (distribution.event && !optionExists(distribution.event, distributionEventOptions.value)) {
    distribution.event = ''
    distribution.eventFilters = []
    distribution.metric = { kind: 'count', field: '', aggregation: 'sum' }
    distributionFilterExpanded.value = false
    cleared.push('参与事件')
  }
  if (distribution.metric.kind === 'property'
    && distribution.metric.field
    && !optionExists(distribution.metric.field, distributionEventPropertyOptions.value)) {
    distribution.metric = { kind: 'count', field: '', aggregation: 'sum' }
    cleared.push('分布指标')
  }
  if (filterFieldValues(distribution.eventFilters).some((field) => !optionExists(field, distributionEventPropertyOptions.value))) {
    distribution.eventFilters = []
    distributionFilterExpanded.value = false
    cleared.push('参与事件筛选')
  }
  const simultaneous = distribution.simultaneous
  if (simultaneous.event && !optionExists(simultaneous.event, distributionEventOptions.value)) {
    simultaneous.event = ''
    simultaneous.metricField = ''
    cleared.push('同时展示事件')
  }
  if (simultaneous.metricField && !optionExists(simultaneous.metricField, distributionSimultaneousMetricFieldOptions())) {
    simultaneous.metricField = ''
    cleared.push('同时展示计算字段')
  }
  if (cleared.length) {
    ElMessage.warning(`${cleared.join('、')}在当前数据源中无效，已清除，请重新选择。`)
  }
}

function intervalPropertyTypeFamily(option?: SchemaFieldOption | null) {
  if (!option) return ''
  const typeText = [option.propertyType, option.semanticType, option.type, option.category]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  if (!typeText) return ''
  if (/(int|decimal|numeric|number|float|double|real|money|金额|数值|数字)/.test(typeText)) return 'numeric'
  if (/(date|time|timestamp|datetime|日期|时间)/.test(typeText)) return 'temporal'
  if (/(bool|boolean|布尔)/.test(typeText)) return 'boolean'
  if (/(char|string|text|varchar|enum|文本|字符串)/.test(typeText)) return 'text'
  return typeText
}

function intervalEventFilterFieldOptions(target: IntervalEventTarget) {
  return eventFilterFieldOptions(target === 'start' ? sqlBuilder.interval.startEvent : sqlBuilder.interval.endEvent)
}

function handleIntervalEventChange(target: IntervalEventTarget, eventValue: string) {
  const eventKey = target === 'start' ? 'startEvent' : 'endEvent'
  const filtersKey = target === 'start' ? 'startEventFilters' : 'endEventFilters'
  const logicKey = target === 'start' ? 'startEventFilterLogic' : 'endEventFilterLogic'
  const propertyKey = target === 'start' ? 'startProperty' : 'endProperty'
  const changed = sqlBuilder.interval[eventKey] !== eventValue
  sqlBuilder.interval[eventKey] = eventValue
  if (!changed) return
  sqlBuilder.interval[filtersKey] = []
  sqlBuilder.interval[logicKey] = 'and'
  sqlBuilder.interval.relatedProperty[propertyKey] = ''
  intervalFilterExpanded[target] = false
  if (target === 'start' && sqlBuilder.interval.relatedProperty.endProperty) {
    sqlBuilder.interval.relatedProperty.endProperty = ''
  }
}

function toggleIntervalEventFilter(target: IntervalEventTarget) {
  const event = target === 'start' ? sqlBuilder.interval.startEvent : sqlBuilder.interval.endEvent
  if (!event) return
  const filters = target === 'start' ? sqlBuilder.interval.startEventFilters : sqlBuilder.interval.endEventFilters
  if (!intervalFilterExpanded[target] && !filters.length) filters.push(emptyBuilderFilter())
  intervalFilterExpanded[target] = !intervalFilterExpanded[target]
}

function handleIntervalRelatedPropertyToggle(enabled: boolean) {
  if (enabled) return
  sqlBuilder.interval.relatedProperty.startProperty = ''
  sqlBuilder.interval.relatedProperty.endProperty = ''
}

function handleIntervalStartPropertyChange(value: string) {
  sqlBuilder.interval.relatedProperty.startProperty = value
  if (sqlBuilder.interval.relatedProperty.endProperty
    && !optionExists(sqlBuilder.interval.relatedProperty.endProperty, intervalEndPropertyOptions.value)) {
    sqlBuilder.interval.relatedProperty.endProperty = ''
  }
}

function intervalBlockingIssues() {
  if (!isIntervalAnalysis.value) return []
  const issues: string[] = []
  const interval = sqlBuilder.interval
  if (!interval.entityField) issues.push('间隔分析请先选择分析主体。')
  if (!interval.startEvent) issues.push('间隔分析请先选择起点事件。')
  if (!interval.endEvent) issues.push('间隔分析请先选择终点事件。')
  if (interval.limitSeconds < INTERVAL_LIMIT_MIN_SECONDS || interval.limitSeconds > INTERVAL_LIMIT_MAX_SECONDS) {
    issues.push('间隔分析上限必须在 1 分钟到 180 天之间。')
  }
  if (interval.relatedProperty.enabled) {
    if (!interval.relatedProperty.startProperty) issues.push('使用关联属性时请选择起点事件属性。')
    if (!interval.relatedProperty.endProperty) issues.push('使用关联属性时请选择终点事件属性。')
    const startType = intervalPropertyTypeFamily(fieldOptionByValue(interval.relatedProperty.startProperty))
    const endType = intervalPropertyTypeFamily(fieldOptionByValue(interval.relatedProperty.endProperty))
    if (startType && endType && startType !== endType) issues.push('起点事件属性和终点事件属性的类型必须一致。')
  }
  return issues
}

function sanitizeIntervalConfig() {
  if (!isIntervalAnalysis.value) return
  const interval = sqlBuilder.interval
  const cleared: string[] = []
  if (interval.entityField && !optionExists(interval.entityField, intervalEntityFieldOptions.value)) {
    interval.entityField = ''
    cleared.push('分析主体')
  }
  for (const target of ['start', 'end'] as IntervalEventTarget[]) {
    const eventKey = target === 'start' ? 'startEvent' : 'endEvent'
    const filtersKey = target === 'start' ? 'startEventFilters' : 'endEventFilters'
    const options = intervalEventOptions.value
    if (interval[eventKey] && !optionExists(interval[eventKey], options)) {
      interval[eventKey] = ''
      interval[filtersKey] = []
      intervalFilterExpanded[target] = false
      cleared.push(target === 'start' ? '起点事件' : '终点事件')
    }
    const filterOptions = intervalEventFilterFieldOptions(target)
    if (filterFieldValues(interval[filtersKey]).some((field) => !optionExists(field, filterOptions))) {
      interval[filtersKey] = []
      intervalFilterExpanded[target] = false
      cleared.push(target === 'start' ? '起点事件筛选' : '终点事件筛选')
    }
  }
  if (interval.relatedProperty.startProperty
    && !optionExists(interval.relatedProperty.startProperty, intervalStartPropertyOptions.value)) {
    interval.relatedProperty.startProperty = ''
    cleared.push('起点事件关联属性')
  }
  if (interval.relatedProperty.endProperty
    && !optionExists(interval.relatedProperty.endProperty, intervalEndPropertyOptions.value)) {
    interval.relatedProperty.endProperty = ''
    cleared.push('终点事件关联属性')
  }
  interval.limitSeconds = clampIntervalLimitSeconds(interval.limitSeconds)
  if (cleared.length) ElMessage.warning(`${cleared.join('、')}在当前数据源中无效，已清除，请重新选择。`)
}

function sanitizePathConfig() {
  if (!isPathAnalysis.value) return
  const cleared: string[] = []
  const validEvents = pathEventOptions.value
  sqlBuilder.path.events = sqlBuilder.path.events.slice(0, PATH_EVENT_LIMIT).map((item) => {
    let event = item.event
    let splitProperties = [...item.splitProperties]
    if (event && !optionExists(event, validEvents)) {
      event = ''
      splitProperties = []
      cleared.push('参与事件')
    }
    const allowedProperties = pathEventPropertyOptions(event)
    const nextSplitProperties = splitProperties.filter((field) => optionExists(field, allowedProperties))
    if (nextSplitProperties.length !== splitProperties.length) cleared.push('事件拆分属性')
    return { ...item, event, splitProperties: nextSplitProperties }
  })
  if (!sqlBuilder.path.events.length) {
    sqlBuilder.path.events = [{ id: 'path-event-initial', event: '', splitProperties: [] }]
  }
  if (sqlBuilder.path.initialEvent && !sqlBuilder.path.events.some((item) => item.event === sqlBuilder.path.initialEvent)) {
    sqlBuilder.path.initialEvent = ''
    cleared.push('初始事件')
  }
  sqlBuilder.path.sessionGapSeconds = clampPathSessionGapSeconds(sqlBuilder.path.sessionGapSeconds)
  if (cleared.length) ElMessage.warning(`${unique(cleared).join('、')}在当前数据源中无效，已清除，请重新选择。`)
}

function pathBlockingIssues() {
  if (!isPathAnalysis.value) return []
  const issues: string[] = []
  const path = sqlBuilder.path
  const selectedEvents = path.events.filter((item) => item.event)
  if (!selectedEvents.length) issues.push('路径分析请先选择参与分析的事件。')
  if (path.events.length > PATH_EVENT_LIMIT) issues.push(`路径分析最多支持 ${PATH_EVENT_LIMIT} 个参与事件。`)
  if (!path.initialEvent) issues.push('路径分析请先选择初始事件。')
  if (path.initialEvent && !selectedEvents.some((item) => item.event === path.initialEvent)) {
    issues.push('路径分析初始事件必须来自参与分析的事件。')
  }
  if (path.sessionGapSeconds < PATH_SESSION_GAP_MIN_SECONDS || path.sessionGapSeconds > PATH_SESSION_GAP_MAX_SECONDS) {
    issues.push('路径分析会话间隔必须在 1 秒到 24 小时之间。')
  }
  return issues
}

function handleAttributionTargetEventChange(eventValue: string) {
  const changed = sqlBuilder.attribution.targetEvent !== eventValue
  sqlBuilder.attribution.targetEvent = eventValue
  if (!changed) return
  sqlBuilder.attribution.targetEventFilterLogic = 'and'
  sqlBuilder.attribution.targetEventFilters = []
  sqlBuilder.attribution.targetMetric.aggregation = 'count'
  sqlBuilder.attribution.targetMetric.metricField = ''
  attributionTargetFilterExpanded.value = false
}

function syncAttributionTargetMetricField() {
  if (sqlBuilder.attribution.targetMetric.aggregation === 'count') {
    sqlBuilder.attribution.targetMetric.metricField = ''
    return
  }
  if (!optionExists(sqlBuilder.attribution.targetMetric.metricField, attributionTargetMetricFieldOptions.value)) {
    sqlBuilder.attribution.targetMetric.metricField = ''
  }
}

function toggleAttributionTargetFilter() {
  if (!sqlBuilder.attribution.targetEvent) return
  if (!attributionTargetFilterExpanded.value && !sqlBuilder.attribution.targetEventFilters.length) {
    sqlBuilder.attribution.targetEventFilters.push(emptyBuilderFilter())
  }
  attributionTargetFilterExpanded.value = !attributionTargetFilterExpanded.value
}

function addAttributionEvent() {
  if (sqlBuilder.attribution.events.length >= ATTRIBUTION_EVENT_LIMIT) {
    ElMessage.warning(`归因分析最多支持 ${ATTRIBUTION_EVENT_LIMIT} 个归因事件。`)
    return
  }
  const item = createAttributionEvent()
  sqlBuilder.attribution.events.push(item)
  attributionEventFilterExpanded[item.id] = false
}

function removeAttributionEvent(index: number) {
  const [removed] = sqlBuilder.attribution.events.splice(index, 1)
  if (removed) delete attributionEventFilterExpanded[removed.id]
}

function handleAttributionEventChange(item: SqlBuilderAttributionEvent, eventValue: string) {
  if (item.event === eventValue) return
  item.event = eventValue
  item.filterLogic = 'and'
  item.filters = []
  attributionEventFilterExpanded[item.id] = false
}

function toggleAttributionEventFilter(item: SqlBuilderAttributionEvent) {
  if (!item.event) return
  if (!attributionEventFilterExpanded[item.id] && !item.filters.length) item.filters.push(emptyBuilderFilter())
  attributionEventFilterExpanded[item.id] = !attributionEventFilterExpanded[item.id]
}

function attributionBlockingIssues() {
  if (!isAttributionAnalysis.value) return []
  const issues: string[] = []
  const attribution = sqlBuilder.attribution
  if (!attribution.entityField) issues.push('归因分析请先选择分析主体。')
  if (attribution.method !== 'linear') issues.push('归因分析使用了不支持的归因方式。')
  if (!isValidAttributionWindow(attribution.window)) issues.push('归因分析窗口期配置无效，请重新设置。')
  if (!attribution.targetEvent) issues.push('归因分析请先选择目标事件。')
  if (attribution.targetMetric.aggregation !== 'count' && !attribution.targetMetric.metricField) {
    issues.push('目标事件使用非次数聚合时，请选择计算字段。')
  }
  if (!attribution.events.some((item) => item.event)) issues.push('归因分析请至少选择一个归因事件。')
  if (attribution.events.length > ATTRIBUTION_EVENT_LIMIT) {
    issues.push(`归因分析最多支持 ${ATTRIBUTION_EVENT_LIMIT} 个归因事件。`)
  }
  attribution.events.forEach((item, index) => {
    if (!item.event) issues.push(`归因分析请先选择归因事件${index + 1}。`)
  })
  return issues
}

function sanitizeAttributionConfig() {
  if (!isAttributionAnalysis.value) return
  const attribution = sqlBuilder.attribution
  const cleared: string[] = []
  if (attribution.entityField && !optionExists(attribution.entityField, attributionEntityFieldOptions.value)) {
    attribution.entityField = ''
    cleared.push('分析主体')
  }
  if (attribution.targetEvent && !optionExists(attribution.targetEvent, attributionEventOptions.value)) {
    attribution.targetEvent = ''
    attribution.targetEventFilters = []
    attribution.targetMetric.metricField = ''
    attributionTargetFilterExpanded.value = false
    cleared.push('目标事件')
  }
  if (filterFieldValues(attribution.targetEventFilters).some(
    (field) => !optionExists(field, eventFilterFieldOptions(attribution.targetEvent))
  )) {
    attribution.targetEventFilters = []
    attributionTargetFilterExpanded.value = false
    cleared.push('目标事件筛选')
  }
  syncAttributionTargetMetricField()
  attribution.events = attribution.events.slice(0, ATTRIBUTION_EVENT_LIMIT).map((item) => {
    if (item.event && !optionExists(item.event, attributionEventOptions.value)) {
      item.event = ''
      item.filters = []
      attributionEventFilterExpanded[item.id] = false
      cleared.push('归因事件')
    }
    if (filterFieldValues(item.filters).some((field) => !optionExists(field, eventFilterFieldOptions(item.event)))) {
      item.filters = []
      attributionEventFilterExpanded[item.id] = false
      cleared.push('归因事件筛选')
    }
    return item
  })
  attribution.window = normalizeAttributionWindow(attribution.window)
  if (!attribution.events.length) addAttributionEvent()
  if (cleared.length) ElMessage.warning(`${unique(cleared).join('、')}在当前数据源中无效，已清除，请重新选择。`)
}

function sanitizeRankingConfig() {
  if (!isRankingAnalysis.value) return
  const ranking = sqlBuilder.ranking
  const cleared: string[] = []
  if (ranking.entityField && !optionExists(ranking.entityField, rankingEntityFieldOptions.value)) {
    ranking.entityField = ''
    cleared.push('分析主体')
  }
  const sanitizeMetric = (metric: SqlBuilderRankingMetric, label: string) => {
    if (metric.event && !optionExists(metric.event, rankingEventOptions.value)) {
      metric.event = ''
      metric.metricField = ''
      cleared.push(label)
    }
    if (metric.metricField && !optionExists(metric.metricField, rankingMetricFieldOptions(metric))) {
      metric.metricField = ''
      cleared.push(`${label}计算字段`)
    }
    if (metric.aggregation === 'count') metric.metricField = ''
    if (metric.direction !== 'asc' && metric.direction !== 'desc') metric.direction = 'desc'
  }
  sanitizeMetric(ranking.metric, '排行指标')
  ranking.simultaneousMetrics = ranking.simultaneousMetrics.map((metric) => {
    sanitizeMetric(metric, '同时展示指标')
    return metric
  })
  ranking.simultaneousProperties = ranking.simultaneousProperties.filter((field) => {
    const valid = optionExists(field, rankingEntityFieldOptions.value)
    if (!valid) cleared.push('同时展示属性')
    return valid
  })
  if (!['default', 'skip', 'dense'].includes(ranking.tieHandling)) ranking.tieHandling = 'default'
  if (cleared.length) ElMessage.warning(`${unique(cleared).join('、')}在当前数据源中无效，已清除，请重新选择。`)
}

function rankingBlockingIssues() {
  if (!isRankingAnalysis.value) return []
  const issues: string[] = []
  const ranking = sqlBuilder.ranking
  if (!ranking.entityField) issues.push('排行榜请先选择排行主体。')
  if (!ranking.metric.event) issues.push('排行榜请先选择排行指标。')
  if (ranking.metric.aggregation !== 'count' && !ranking.metric.metricField) {
    issues.push('排行指标使用非次数聚合时，请选择计算字段。')
  }
  const primaryMetricField = fieldOptionByValue(ranking.metric.metricField)
  if (['sum', 'avg'].includes(ranking.metric.aggregation)
    && ranking.metric.metricField
    && primaryMetricField
    && !isNumericFieldOption(primaryMetricField)) {
    issues.push('排行指标使用求和或平均值时，计算字段必须是数值字段。')
  }
  ranking.simultaneousMetrics.forEach((metric, index) => {
    if (!metric.event) issues.push(`同时展示指标${index + 1}请先选择指标。`)
    if (metric.aggregation !== 'count' && !metric.metricField) {
      issues.push(`同时展示指标${index + 1}使用非次数聚合时，请选择计算字段。`)
    }
    const metricField = fieldOptionByValue(metric.metricField)
    if (['sum', 'avg'].includes(metric.aggregation)
      && metric.metricField
      && metricField
      && !isNumericFieldOption(metricField)) {
      issues.push(`同时展示指标${index + 1}使用求和或平均值时，计算字段必须是数值字段。`)
    }
  })
  if (!['default', 'skip', 'dense'].includes(ranking.tieHandling)) issues.push('排行榜并列名次处理方式无效。')
  return issues
}

function sanitizeRetentionConfig() {
  if (!isRetentionAnalysis.value) return
  const cleared: string[] = []
  if (sqlBuilder.retention.entityField && !optionExists(sqlBuilder.retention.entityField, retentionEntityFieldOptions.value)) {
    sqlBuilder.retention.entityField = ''
    cleared.push('分析主体')
  }
  if (sqlBuilder.retention.initialEvent && !optionExists(sqlBuilder.retention.initialEvent, retentionEventOptions.value)) {
    sqlBuilder.retention.initialEvent = ''
    sqlBuilder.retention.initialEventAlias = ''
    sqlBuilder.retention.initialEventFilters = []
    sqlBuilder.retention.initialEventFilterLogic = 'and'
    retentionFilterExpanded.initial = false
    retentionAliasEditing.initial = false
    retentionAliasDraft.initial = ''
    cleared.push('初始事件')
  }
  if (sqlBuilder.retention.returnEvent && !optionExists(sqlBuilder.retention.returnEvent, retentionEventOptions.value)) {
    sqlBuilder.retention.returnEvent = ''
    sqlBuilder.retention.returnEventAlias = ''
    sqlBuilder.retention.returnEventFilters = []
    sqlBuilder.retention.returnEventFilterLogic = 'and'
    retentionFilterExpanded.return = false
    retentionAliasEditing.return = false
    retentionAliasDraft.return = ''
    cleared.push('回访事件')
  }
  ;([
    ['initial', sqlBuilder.retention.initialEventFilters, '初始事件筛选条件'],
    ['return', sqlBuilder.retention.returnEventFilters, '回访事件筛选条件'],
  ] as const).forEach(([target, filters, label]) => {
    const allowedOptions = retentionEventFilterFieldOptions(target)
    const invalidFields = filterFieldValues(filters).filter((field) => !optionExists(field, allowedOptions))
    if (!invalidFields.length) return
    if (target === 'initial') {
      sqlBuilder.retention.initialEventFilters = []
    } else {
      sqlBuilder.retention.returnEventFilters = []
    }
    retentionFilterExpanded[target] = false
    cleared.push(label)
  })
  if (sqlBuilder.retention.simultaneous.event && !optionExists(sqlBuilder.retention.simultaneous.event, retentionEventOptions.value)) {
    sqlBuilder.retention.simultaneous.event = ''
    sqlBuilder.retention.simultaneous.metricField = ''
    cleared.push('同时展示事件')
  }
  if (
    sqlBuilder.retention.simultaneous.metricField
    && !optionExists(
      sqlBuilder.retention.simultaneous.metricField,
      retentionSimultaneousMetricFieldOptions()
    )
  ) {
    sqlBuilder.retention.simultaneous.metricField = ''
    cleared.push('同时展示计算字段')
  }
  const relatedProperty = sqlBuilder.retention.relatedProperty
  ;([
    ['initialProperty', sqlBuilder.retention.initialEvent, '初始事件关联属性'],
    ['returnProperty', sqlBuilder.retention.returnEvent, '回访事件关联属性'],
    ['simultaneousProperty', sqlBuilder.retention.simultaneous.event, '同时展示关联属性'],
  ] as const).forEach(([key, eventValue, label]) => {
    if (relatedProperty[key] && !optionExists(relatedProperty[key], retentionPropertyOptions(eventValue))) {
      relatedProperty[key] = ''
      cleared.push(label)
    }
  })
  if (cleared.length) {
    ElMessage.warning(`${cleared.join('、')}在当前数据源中无效，已清除，请重新选择。`)
  }
}

function retentionBlockingIssues() {
  if (!isRetentionAnalysis.value) return []
  const issues: string[] = []
  if (!sqlBuilder.retention.entityField) issues.push('留存分析请先选择分析主体。')
  if (!sqlBuilder.retention.initialEvent) issues.push('留存分析请先选择初始事件。')
  if (!sqlBuilder.retention.returnEvent) issues.push('留存分析请先选择回访事件。')
  if (!sqlBuilder.timeField) issues.push('留存分析请先选择时间字段。')
  if (sqlBuilder.retention.simultaneous.enabled && !sqlBuilder.retention.simultaneous.event) {
    issues.push('使用同时展示时请选择参与事件。')
  }
  if (
    sqlBuilder.retention.simultaneous.enabled
    && sqlBuilder.retention.simultaneous.aggregation !== 'count'
    && !sqlBuilder.retention.simultaneous.metricField
  ) {
    issues.push(`同时展示使用“${builderAggregationLabel(sqlBuilder.retention.simultaneous.aggregation)}”时请选择计算字段。`)
  }
  if (
    sqlBuilder.retention.simultaneous.enabled
    && ['sum', 'avg'].includes(sqlBuilder.retention.simultaneous.aggregation)
    && sqlBuilder.retention.simultaneous.metricField
  ) {
    const metricField = fieldOptionByValue(sqlBuilder.retention.simultaneous.metricField)
    if (metricField && !isNumericFieldOption(metricField)) {
      issues.push('同时展示使用“求和/平均值”时，计算字段必须是数值字段。')
    }
  }
  if (sqlBuilder.retention.relatedProperty.enabled) {
    if (!sqlBuilder.retention.relatedProperty.initialProperty) issues.push('使用关联属性时请选择初始事件属性。')
    if (!sqlBuilder.retention.relatedProperty.returnProperty) issues.push('使用关联属性时请选择回访事件属性。')
    if (sqlBuilder.retention.simultaneous.enabled && !sqlBuilder.retention.relatedProperty.simultaneousProperty) {
      issues.push('使用关联属性和同时展示时请选择同时展示事件属性。')
    }
  }
  return issues
}

function funnelPropertyOptions(eventValue: string) {
  return retentionPropertyOptions(eventValue)
}

function handleFunnelStepEventChange(step: SqlBuilderFunnelStep, eventValue: string) {
  const changed = step.event !== eventValue
  step.event = eventValue
  if (!changed) return
  const hadScopedConfig = Boolean(step.alias.trim() || step.filters.length || step.relatedProperty)
  step.alias = ''
  step.filters = []
  step.filterLogic = 'and'
  step.relatedProperty = ''
  funnelFilterExpanded[step.id] = false
  funnelAliasEditing[step.id] = false
  funnelAliasDraft[step.id] = ''
  if (hadScopedConfig) {
    ElMessage.warning('漏斗步骤事件已切换，原重命名、筛选和关联属性已清除。')
  }
}

function handleFunnelRelatedPropertyToggle(enabled: boolean) {
  if (enabled) return
  sqlBuilder.funnel.steps.forEach((step) => {
    step.relatedProperty = ''
  })
}

function beginFunnelStepRename(step: SqlBuilderFunnelStep) {
  if (!step.event) return
  funnelAliasDraft[step.id] = step.alias
  funnelAliasEditing[step.id] = true
}

function finishFunnelStepRename(step: SqlBuilderFunnelStep) {
  if (!funnelAliasEditing[step.id]) return
  step.alias = (funnelAliasDraft[step.id] || '').trim()
  funnelAliasEditing[step.id] = false
}

function cancelFunnelStepRename(step: SqlBuilderFunnelStep) {
  funnelAliasEditing[step.id] = false
  funnelAliasDraft[step.id] = ''
}

function toggleFunnelStepFilter(step: SqlBuilderFunnelStep) {
  if (!step.event) return
  if (!funnelFilterExpanded[step.id] && !step.filters.length) {
    step.filters.push(emptyBuilderFilter())
  }
  funnelFilterExpanded[step.id] = !funnelFilterExpanded[step.id]
}

function addFunnelStep() {
  if (sqlBuilder.funnel.steps.length >= 10) {
    ElMessage.warning('漏斗最多支持 10 个步骤。')
    return
  }
  const step = createFunnelStep()
  funnelFilterExpanded[step.id] = false
  funnelAliasEditing[step.id] = false
  funnelAliasDraft[step.id] = ''
  sqlBuilder.funnel.steps.push(step)
}

function removeFunnelStep(index: number) {
  if (sqlBuilder.funnel.steps.length <= 2) {
    ElMessage.warning('漏斗至少需要 2 个步骤。')
    return
  }
  const [removed] = sqlBuilder.funnel.steps.splice(index, 1)
  if (removed) {
    delete funnelFilterExpanded[removed.id]
    delete funnelAliasEditing[removed.id]
    delete funnelAliasDraft[removed.id]
  }
}

function sanitizeFunnelConfig() {
  if (!isFunnelAnalysis.value) return
  const cleared: string[] = []
  if (sqlBuilder.funnel.entityField && !optionExists(sqlBuilder.funnel.entityField, funnelEntityFieldOptions.value)) {
    sqlBuilder.funnel.entityField = ''
    cleared.push('分析主体')
  }
  sqlBuilder.funnel.steps.forEach((step, index) => {
    if (step.event && !optionExists(step.event, funnelEventOptions.value)) {
      step.event = ''
      step.alias = ''
      step.filters = []
      step.relatedProperty = ''
      funnelFilterExpanded[step.id] = false
      cleared.push(`步骤${index + 1}事件`)
    }
    const invalidFilter = filterFieldValues(step.filters).some((field) => !optionExists(field, eventFilterFieldOptions(step.event)))
    if (invalidFilter) {
      step.filters = []
      step.filterLogic = 'and'
      funnelFilterExpanded[step.id] = false
      cleared.push(`步骤${index + 1}筛选条件`)
    }
    if (step.relatedProperty && !optionExists(step.relatedProperty, funnelPropertyOptions(step.event))) {
      step.relatedProperty = ''
      cleared.push(`步骤${index + 1}关联属性`)
    }
  })
  if (cleared.length) {
    ElMessage.warning(`${cleared.join('、')}在当前数据源中无效，已清除，请重新选择。`)
  }
}

function funnelBlockingIssues() {
  if (!isFunnelAnalysis.value) return []
  const issues: string[] = []
  if (!sqlBuilder.funnel.entityField) issues.push('漏斗分析请先选择分析主体。')
  if (!sqlBuilder.timeField) issues.push('漏斗分析请先选择时间字段。')
  if (!isValidFunnelWindow(sqlBuilder.funnel.window)) issues.push('漏斗分析窗口期配置无效，请重新设置。')
  if (sqlBuilder.funnel.steps.length < 2) issues.push('漏斗分析至少需要配置两个步骤。')
  sqlBuilder.funnel.steps.forEach((step, index) => {
    if (!step.event) issues.push(`漏斗分析请先选择步骤${index + 1}事件。`)
    if (sqlBuilder.funnel.relatedPropertyEnabled && !step.relatedProperty) {
      issues.push(`使用关联属性时请选择步骤${index + 1}关联属性。`)
    }
  })
  return issues
}

function metricMeasureField(item: SqlBuilderMetricItem) {
  return item.aggregation === 'count' ? item.field : item.metric || item.field
}

function currentSqlMainTable() {
  const match = String(form.sql || '').match(/\bfrom\s+([`"\[]?[\w.]+[`"\]]?)/i)
  return match?.[1]?.replace(/^[`"\[]|[`"\]]$/g, '') || ''
}

function previewSchemaTables() {
  const tableName = currentSqlMainTable()
  const fields = unique([...sourcePreview.fields, ...preview.fields])
  if (!tableName || !fields.length) return []
  return [
    {
      id: 'current-sql',
      table_name: tableName,
      display_name: '当前 SQL',
      fields: fields.map((field) => ({
        field_name: field,
        field_type: sourcePreview.data.some((row) => typeof row?.[field] === 'number') ? 'number' : '',
        custom_comment: '',
      })),
    },
  ]
}

function fieldOptionPayload(value: string) {
  const option = fieldOptionByValue(value)
  if (!option) {
    return value ? { value } : null
  }
  return {
    value: option.value,
    table: option.table,
    tableLabel: option.tableLabel,
    tableRole: option.tableRole,
    field: option.field,
    displayName: option.displayName || option.label || option.field,
    type: option.type,
    comment: option.comment,
    category: option.category,
    semanticType: option.semanticType,
    sourceField: option.sourceField,
    jsonPath: option.jsonPath,
    expression: option.expression,
    isJsonSubfield: option.isJsonSubfield,
    kind: option.kind,
    eventName: option.eventName,
    eventCategory: option.eventCategory,
    eventDescription: option.eventDescription,
    eventTable: option.eventTable,
    eventNameField: option.eventNameField,
    propertyName: option.propertyName,
    propertyType: option.propertyType,
  }
}

function filterContext(nodes: SqlBuilderFilter[]): any[] {
  return (nodes || []).flatMap((node) => {
    if (node.type === 'group') {
      const children = filterContext(node.children || [])
      if (!children.length) {
        return []
      }
      return {
        type: 'group',
        logic: node.logic || 'and',
        children,
      }
    }
    if (!isEffectiveBuilderFilter(node)) {
      return []
    }
    return {
      type: 'rule',
      field: fieldOptionPayload(node.field),
      operator: node.operator,
      value: node.value,
    }
  })
}

function selectedBuilderFieldValues() {
  const formulaFields = sqlBuilder.calculatedMetrics.flatMap((item) =>
    item.tokens.flatMap((token) => {
      if (token.type !== 'atomicMetric') return []
      return [
        token.metric.field,
        token.metric.metric,
        ...filterFieldValues((token.metric.filters || []) as SqlBuilderFilter[]),
      ]
    })
  )
  return unique([
    sqlBuilder.timeField,
    ...(sqlBuilder.analysisModel === 'retention' ? [
      sqlBuilder.retention.entityField,
      sqlBuilder.retention.initialEvent,
      sqlBuilder.retention.returnEvent,
      sqlBuilder.retention.simultaneous.event,
      sqlBuilder.retention.simultaneous.metricField,
      sqlBuilder.retention.relatedProperty.initialProperty,
      sqlBuilder.retention.relatedProperty.returnProperty,
      sqlBuilder.retention.relatedProperty.simultaneousProperty,
      ...filterFieldValues(sqlBuilder.retention.initialEventFilters),
      ...filterFieldValues(sqlBuilder.retention.returnEventFilters),
    ] : []),
    ...(sqlBuilder.analysisModel === 'funnel' ? [
      sqlBuilder.funnel.entityField,
      ...sqlBuilder.funnel.steps.flatMap((step) => [
        step.event,
        step.relatedProperty,
        ...filterFieldValues(step.filters),
      ]),
    ] : []),
    ...(sqlBuilder.analysisModel === 'distribution' ? [
      sqlBuilder.distribution.entityField,
      sqlBuilder.distribution.event,
      sqlBuilder.distribution.metric.field,
      sqlBuilder.distribution.simultaneous.event,
      sqlBuilder.distribution.simultaneous.metricField,
      ...filterFieldValues(sqlBuilder.distribution.eventFilters),
    ] : []),
    ...(sqlBuilder.analysisModel === 'interval' ? [
      sqlBuilder.interval.entityField,
      sqlBuilder.interval.startEvent,
      sqlBuilder.interval.endEvent,
      sqlBuilder.interval.relatedProperty.startProperty,
      sqlBuilder.interval.relatedProperty.endProperty,
      ...filterFieldValues(sqlBuilder.interval.startEventFilters),
      ...filterFieldValues(sqlBuilder.interval.endEventFilters),
    ] : []),
    ...(sqlBuilder.analysisModel === 'path' ? [
      ...sqlBuilder.path.events.flatMap((item) => [item.event, ...item.splitProperties]),
      sqlBuilder.path.initialEvent,
    ] : []),
    ...(sqlBuilder.analysisModel === 'revenue' ? [
      sqlBuilder.revenue.entityField,
      sqlBuilder.revenue.initialEvent,
      sqlBuilder.revenue.paymentEvent,
      sqlBuilder.revenue.metric.field,
      sqlBuilder.revenue.costField,
    ] : []),
    ...(sqlBuilder.analysisModel === 'attribution' ? [
      sqlBuilder.attribution.entityField,
      sqlBuilder.attribution.targetEvent,
      sqlBuilder.attribution.targetMetric.metricField,
      ...filterFieldValues(sqlBuilder.attribution.targetEventFilters),
      ...sqlBuilder.attribution.events.flatMap((item) => [item.event, ...filterFieldValues(item.filters)]),
    ] : []),
    ...(sqlBuilder.analysisModel === 'ranking' ? [
      sqlBuilder.ranking.entityField,
      sqlBuilder.ranking.metric.event,
      sqlBuilder.ranking.metric.metricField,
      ...sqlBuilder.ranking.simultaneousMetrics.flatMap((item) => [item.event, item.metricField]),
      ...sqlBuilder.ranking.simultaneousProperties,
    ] : []),
    ...sqlBuilder.metricItems.flatMap((item) => [item.field, item.metric]),
    ...sqlBuilder.calculatedMetrics.flatMap((item) => [item.pendingEventField, item.pendingMetricField]),
    ...formulaFields,
    ...sqlBuilder.groups,
    ...filterFieldValues(sqlBuilder.globalFilters),
    ...sqlBuilder.metricItems.flatMap((item) => filterFieldValues(item.filters || [])),
  ])
}

function collectBuilderAiContext() {
  const selectedFields = selectedBuilderFieldValues()
    .map(fieldOptionPayload)
    .filter(Boolean)
  const metricAliasById = new Map<string, string>()
  sqlBuilder.metricItems.forEach((item, index) => {
    metricAliasById.set(item.id, metricOutputAlias(item, index))
  })
  return {
    analysisModel: sqlBuilder.analysisModel,
    retention: sqlBuilder.analysisModel === 'retention' ? {
      content: RETENTION_ANALYSIS_CONTEXT_CONTENT,
      entityField: fieldOptionPayload(sqlBuilder.retention.entityField),
      initialEvent: fieldOptionPayload(sqlBuilder.retention.initialEvent),
      initialEventAlias: sqlBuilder.retention.initialEventAlias.trim(),
      initialEventFilters: {
        logic: sqlBuilder.retention.initialEventFilterLogic,
        rules: filterContext(sqlBuilder.retention.initialEventFilters),
      },
      returnEvent: fieldOptionPayload(sqlBuilder.retention.returnEvent),
      returnEventAlias: sqlBuilder.retention.returnEventAlias.trim(),
      returnEventFilters: {
        logic: sqlBuilder.retention.returnEventFilterLogic,
        rules: filterContext(sqlBuilder.retention.returnEventFilters),
      },
      simultaneous: {
        enabled: sqlBuilder.retention.simultaneous.enabled,
        event: sqlBuilder.retention.simultaneous.enabled
          ? fieldOptionPayload(sqlBuilder.retention.simultaneous.event)
          : null,
        aggregation: sqlBuilder.retention.simultaneous.aggregation,
        metricField: sqlBuilder.retention.simultaneous.enabled
          && sqlBuilder.retention.simultaneous.aggregation !== 'count'
          ? fieldOptionPayload(sqlBuilder.retention.simultaneous.metricField)
          : null,
      },
      relatedProperty: {
        enabled: sqlBuilder.retention.relatedProperty.enabled,
        initialProperty: sqlBuilder.retention.relatedProperty.enabled
          ? fieldOptionPayload(sqlBuilder.retention.relatedProperty.initialProperty)
          : null,
        returnProperty: sqlBuilder.retention.relatedProperty.enabled
          ? fieldOptionPayload(sqlBuilder.retention.relatedProperty.returnProperty)
          : null,
        simultaneousProperty: sqlBuilder.retention.relatedProperty.enabled && sqlBuilder.retention.simultaneous.enabled
          ? fieldOptionPayload(sqlBuilder.retention.relatedProperty.simultaneousProperty)
          : null,
        asGroup: sqlBuilder.retention.relatedProperty.enabled && sqlBuilder.retention.relatedProperty.asGroup,
      },
    } : null,
    funnel: sqlBuilder.analysisModel === 'funnel' ? {
      content: '以某段时间做过步骤1的用户为样本，查看窗口期内，指定步骤下用户的转化情况',
      entityField: fieldOptionPayload(sqlBuilder.funnel.entityField),
      window: normalizeFunnelWindow(sqlBuilder.funnel.window),
      relatedPropertyEnabled: sqlBuilder.funnel.relatedPropertyEnabled,
      steps: sqlBuilder.funnel.steps.map((step, index) => ({
        order: index + 1,
        event: fieldOptionPayload(step.event),
        alias: step.alias.trim(),
        filters: {
          logic: step.filterLogic,
          rules: filterContext(step.filters),
        },
        relatedProperty: sqlBuilder.funnel.relatedPropertyEnabled
          ? fieldOptionPayload(step.relatedProperty)
          : null,
      })),
    } : null,
    ranking: sqlBuilder.analysisModel === 'ranking' ? {
      content: '按排行主体聚合主排行指标并生成名次，同时展示附加指标和属性；并列名次严格使用配置规则',
      entityField: fieldOptionPayload(sqlBuilder.ranking.entityField),
      metric: {
        event: fieldOptionPayload(sqlBuilder.ranking.metric.event),
        alias: sqlBuilder.ranking.metric.alias.trim(),
        aggregation: sqlBuilder.ranking.metric.aggregation,
        metricField: sqlBuilder.ranking.metric.aggregation === 'count'
          ? null
          : fieldOptionPayload(sqlBuilder.ranking.metric.metricField),
        direction: sqlBuilder.ranking.metric.direction,
      },
      tieHandling: sqlBuilder.ranking.tieHandling,
      simultaneousMetrics: sqlBuilder.ranking.simultaneousMetrics.map((item) => ({
        event: fieldOptionPayload(item.event),
        alias: item.alias.trim(),
        aggregation: item.aggregation,
        metricField: item.aggregation === 'count' ? null : fieldOptionPayload(item.metricField),
      })),
      simultaneousProperties: sqlBuilder.ranking.simultaneousProperties.map(fieldOptionPayload).filter(Boolean),
    } : null,
    distribution: sqlBuilder.analysisModel === 'distribution' ? {
      content: '一段时间内，指定用户参与某一事件的总完成次数或属性值按个人聚合后的全员分布情况',
      entityField: fieldOptionPayload(sqlBuilder.distribution.entityField),
      event: fieldOptionPayload(sqlBuilder.distribution.event),
      eventFilters: {
        logic: sqlBuilder.distribution.eventFilterLogic,
        rules: filterContext(sqlBuilder.distribution.eventFilters),
      },
      metric: {
        kind: sqlBuilder.distribution.metric.kind,
        field: sqlBuilder.distribution.metric.kind === 'property'
          ? fieldOptionPayload(sqlBuilder.distribution.metric.field)
          : null,
        aggregation: sqlBuilder.distribution.metric.aggregation,
      },
      interval: {
        mode: effectiveDistributionInterval().mode,
        customBounds: [...effectiveDistributionInterval().customBounds],
      },
      simultaneous: {
        enabled: sqlBuilder.distribution.simultaneous.enabled,
        event: sqlBuilder.distribution.simultaneous.enabled
          ? fieldOptionPayload(sqlBuilder.distribution.simultaneous.event)
          : null,
        aggregation: sqlBuilder.distribution.simultaneous.aggregation,
        metricField: sqlBuilder.distribution.simultaneous.enabled
          && sqlBuilder.distribution.simultaneous.aggregation !== 'count'
          ? fieldOptionPayload(sqlBuilder.distribution.simultaneous.metricField)
          : null,
      },
    } : null,
    interval: sqlBuilder.analysisModel === 'interval' ? {
      content: '分析同一主体依次完成起点事件和终点事件的时间间隔；不同事件按最后一个连续起点匹配后续第一个终点，相同事件按相邻两次匹配',
      entityField: fieldOptionPayload(sqlBuilder.interval.entityField),
      startEvent: fieldOptionPayload(sqlBuilder.interval.startEvent),
      startEventFilters: {
        logic: sqlBuilder.interval.startEventFilterLogic,
        rules: filterContext(sqlBuilder.interval.startEventFilters),
      },
      endEvent: fieldOptionPayload(sqlBuilder.interval.endEvent),
      endEventFilters: {
        logic: sqlBuilder.interval.endEventFilterLogic,
        rules: filterContext(sqlBuilder.interval.endEventFilters),
      },
      relatedProperty: {
        enabled: sqlBuilder.interval.relatedProperty.enabled,
        startProperty: sqlBuilder.interval.relatedProperty.enabled
          ? fieldOptionPayload(sqlBuilder.interval.relatedProperty.startProperty)
          : null,
        endProperty: sqlBuilder.interval.relatedProperty.enabled
          ? fieldOptionPayload(sqlBuilder.interval.relatedProperty.endProperty)
          : null,
        comparison: 'equal',
      },
      limitSeconds: clampIntervalLimitSeconds(sqlBuilder.interval.limitSeconds),
    } : null,
    path: sqlBuilder.analysisModel === 'path' ? {
      content: '按会话追踪参与分析事件的行为顺序，展示初始事件之后的节点流入和流出',
      events: sqlBuilder.path.events.map((item, index) => ({
        order: index + 1,
        event: fieldOptionPayload(item.event),
        splitProperties: item.splitProperties.map(fieldOptionPayload).filter(Boolean),
      })),
      initialEvent: fieldOptionPayload(sqlBuilder.path.initialEvent),
      sessionGapSeconds: clampPathSessionGapSeconds(sqlBuilder.path.sessionGapSeconds),
    } : null,
    revenue: sqlBuilder.analysisModel === 'revenue' ? {
      content: '以同期初始事件形成主体 Cohort，统计其在观察期内参与付费事件产生的每日及累计收入指标',
      entityField: fieldOptionPayload(sqlBuilder.revenue.entityField),
      initialEvent: fieldOptionPayload(sqlBuilder.revenue.initialEvent),
      paymentEvent: fieldOptionPayload(sqlBuilder.revenue.paymentEvent),
      metric: {
        method: sqlBuilder.revenue.metric.method,
        field: revenueMetricUsesProperty(sqlBuilder.revenue.metric.method)
          ? fieldOptionPayload(sqlBuilder.revenue.metric.field)
          : null,
      },
      cost: {
        enabled: sqlBuilder.revenue.costEnabled,
        field: sqlBuilder.revenue.costEnabled ? fieldOptionPayload(sqlBuilder.revenue.costField) : null,
      },
      observationDays: clampRevenueObservationDays(sqlBuilder.revenue.observationDays),
    } : null,
    attribution: sqlBuilder.analysisModel === 'attribution' ? {
      content: '把目标事件发生前窗口期内的归因事件按线性归因方式均分贡献，统计各归因事件获得的目标次数、目标值和贡献占比',
      entityField: fieldOptionPayload(sqlBuilder.attribution.entityField),
      method: sqlBuilder.attribution.method,
      window: normalizeAttributionWindow(sqlBuilder.attribution.window),
      targetEvent: fieldOptionPayload(sqlBuilder.attribution.targetEvent),
      targetEventFilters: {
        logic: sqlBuilder.attribution.targetEventFilterLogic,
        rules: filterContext(sqlBuilder.attribution.targetEventFilters),
      },
      targetMetric: {
        aggregation: sqlBuilder.attribution.targetMetric.aggregation,
        metricField: sqlBuilder.attribution.targetMetric.aggregation === 'count'
          ? null
          : fieldOptionPayload(sqlBuilder.attribution.targetMetric.metricField),
      },
      includeDirect: sqlBuilder.attribution.includeDirect,
      events: sqlBuilder.attribution.events.map((item, index) => ({
        order: index + 1,
        event: fieldOptionPayload(item.event),
        filters: {
          logic: item.filterLogic,
          rules: filterContext(item.filters),
        },
      })),
    } : null,
    chart: {
      title: form.title,
      type: form.chartType,
    },
    datasource: datasourceInfo.value
      ? {
          id: datasourceInfo.value.id,
          name: datasourceInfo.value.name,
          type: datasourceInfo.value.type,
          typeName: datasourceInfo.value.type_name || datasourceInfo.value.typeName,
        }
      : { id: selectedExecutionDatasourceId.value },
    time: {
      field: fieldOptionPayload(sqlBuilder.timeField),
      grain: sqlBuilder.timeGrain,
      range: sqlBuilder.timeRange,
      customRange: sqlBuilder.timeCustomRange,
      dateParameterType: shouldUseDashboardDateParameters()
        ? SQL_EDITOR_DATE_PARAMETER_TYPE
        : '',
      dateExpression: shouldUseDashboardDateParameters() && sqlBuilder.timeExpression
        ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
        : null,
    },
    metrics: sqlBuilder.metricItems.map((item, index) => ({
      id: item.id,
      alias: metricOutputAlias(item, index),
      label: metricTitle(item, index),
      field: fieldOptionPayload(item.field),
      metricField: fieldOptionPayload(metricMeasureField(item)),
      aggregation: item.aggregation,
      filters: {
        logic: item.filterLogic,
        rules: filterContext(item.filters || []),
      },
    })),
    calculatedMetrics: sqlBuilder.calculatedMetrics.map((item, index) => ({
      id: item.id,
      alias: sqlAlias(item.alias || `公式指标${index + 1}`, `公式指标${index + 1}`),
      decimalPlaces: item.decimalPlaces,
      formulaText: formulaTokensToText(item.tokens, builderMetricOptions.value),
      tokens: serializeFormulaTokensForContext(item.tokens, metricAliasById, fieldOptionPayload),
    })),
    formulaMetrics: sqlBuilder.calculatedMetrics.map((item, index) => ({
      id: item.id,
      alias: sqlAlias(item.alias || `公式指标${index + 1}`, `公式指标${index + 1}`),
      decimalPlaces: item.decimalPlaces,
      formulaText: formulaTokensToText(item.tokens, builderMetricOptions.value),
      tokens: serializeFormulaTokensForContext(item.tokens, metricAliasById, fieldOptionPayload),
    })),
    groups: sqlBuilder.groups.map(fieldOptionPayload).filter(Boolean),
    filters: {
      logic: sqlBuilder.globalFilterLogic,
      rules: filterContext(sqlBuilder.globalFilters),
    },
    selectedFields,
    approximate: sqlBuilder.approximate,
  }
}

function generatedSqlMatchesBuilderMetrics(sql: string) {
  const normalized = String(sql || '').toLowerCase()
  return sqlBuilder.metricItems.every((item) => {
    if (item.aggregation === 'count_distinct') {
      return /count\s*\(\s*distinct/i.test(sql)
    }
    if (item.aggregation === 'sum') {
      return /\bsum\s*\(/i.test(sql)
    }
    if (item.aggregation === 'avg') {
      return /\bavg\s*\(/i.test(sql)
    }
    if (item.aggregation === 'max') {
      return /\bmax\s*\(/i.test(sql)
    }
    if (item.aggregation === 'min') {
      return /\bmin\s*\(/i.test(sql)
    }
    if (item.aggregation === 'count') {
      return /\bcount\s*\(/i.test(sql)
    }
    return Boolean(normalized)
  })
}

function collectLocalBuilderConfigIssues() {
  const eventScopeIssues = builderBlockingScopeIssues()
  const retentionIssues = retentionBlockingIssues()
  const funnelIssues = funnelBlockingIssues()
  const distributionIssues = distributionBlockingIssues()
  const intervalIssues = intervalBlockingIssues()
  const pathIssues = pathBlockingIssues()
  const revenueIssues = revenueBlockingIssues()
  const attributionIssues = attributionBlockingIssues()
  const rankingIssues = rankingBlockingIssues()
  const issues: string[] = [
    ...eventScopeIssues,
    ...retentionIssues,
    ...funnelIssues,
    ...distributionIssues,
    ...intervalIssues,
    ...pathIssues,
    ...revenueIssues,
    ...attributionIssues,
    ...rankingIssues,
  ]
  const suggestions: string[] = []
  if (eventScopeIssues.length && eventFieldScope.value.defaultEventTable) {
    suggestions.push(`请重新选择 ${eventFieldScope.value.defaultEventTable} 表中的字段后再生成 SQL。`)
  }
  const selectedOptions = selectedBuilderFieldValues()
    .map(fieldOptionByValue)
    .filter(Boolean) as SchemaFieldOption[]
  const selectedTables = unique(selectedOptions.map((item) => item.table).filter(Boolean))
  if (eventFieldScope.value.mode === 'general' && selectedTables.length > 1) {
    issues.push(`跨表了：当前同时用了 ${selectedTables.join('、')}。`)
    suggestions.push(`先选一个主表：时间范围和分析指标都改到 ${selectedTables[0]} 表；需要跨表时先在数据模型或语义配置里补充明确关联关系。`)
  }
  const timeOption = fieldOptionByValue(sqlBuilder.timeField)
  if (
    eventFieldScope.value.mode === 'general'
    && timeOption
    && selectedTables.length > 1
    && !selectedTables.every((table) => table === timeOption.table)
  ) {
    issues.push(`时间字段在 ${timeOption.table}，指标/筛选字段在其他表。`)
    suggestions.push(`时间范围：字段选 ${quotedBuilderFieldLabel(sqlBuilder.timeField)}，并把分析指标都改成 ${timeOption.table} 表字段。`)
  }
  const aliasList = sqlBuilder.metricItems.map((item, index) => metricOutputAlias(item, index))
  const duplicateAlias = aliasList.find((alias, index) => alias && aliasList.indexOf(alias) !== index)
  if (duplicateAlias) {
    issues.push(`指标别名重复：${duplicateAlias}。`)
    suggestions.push('分析指标：把重复别名改成不同的业务名称。')
  }
  invalidFormulaMetricItems().forEach((item) => {
    const label = sqlBuilder.calculatedMetrics[item.index]?.alias || `公式指标${item.index + 1}`
    issues.push(`${label} 的公式语法错误：${item.validation.message}。`)
    suggestions.push(`${label}：补全公式后再生成，例如选择一个分析指标、运算符，再选择另一个分析指标。`)
  })
  const metricFingerprints = new Set<string>()
  sqlBuilder.metricItems.forEach((item, index) => {
    const alias = metricOutputAlias(item, index)
    const label = alias || `指标${index + 1}`
    const fingerprint = JSON.stringify({
      field: item.field,
      metric: metricMeasureField(item),
      aggregation: item.aggregation,
      filters: filterContext(item.filters || []),
    })
    if (metricFingerprints.has(fingerprint)) {
      issues.push(`${label} 和前面指标配置重复。`)
      suggestions.push(`分析指标${index + 1}：删除这一条，或加不同筛选条件。`)
    }
    metricFingerprints.add(fingerprint)
    if (/^指标\d+$/.test(alias)) {
      suggestions.push(`${describeBuilderMetricConfig(item, index)}。把最后输入框从「${label}」改成业务名。`)
    }
    if (['sum', 'avg'].includes(item.aggregation)) {
      const metricField = fieldOptionByValue(metricMeasureField(item))
      if (metricField && !isNumericFieldOption(metricField)) {
        issues.push(`${label} 使用了“${builderAggregationLabel(item.aggregation)}”，但计算字段不是数值。`)
        suggestions.push(`分析指标${index + 1}：计算字段改选金额/数量类数值字段，或聚合改成「去重数」「总次数」。`)
      }
    }
  })
  return {
    issues: unique(issues),
    suggestions: unique(suggestions),
  }
}

function resultAdviceItems(result: any, key: 'issues' | 'warnings' | 'suggestions') {
  return Array.isArray(result?.[key])
    ? result[key].map((item: any) => String(item || '')).filter(Boolean)
    : []
}

function resultWarningItems(result: any) {
  return resultAdviceItems(result, 'warnings')
}

function isNonBlockingBuilderAdviceItem(value: string) {
  const text = String(value || '')
  return /别名|标题|图表类型|图表标题|业务名称|业务含义|分组维度|信息密度|展示|美观|冗余|selectedFields|已选字段|未使用|国家|渠道|平台|事件筛选条件|事件名筛选|未限定\s*event/.test(text)
}

function resultBlockingIssueItems(result: any) {
  const issues = resultAdviceItems(result, 'issues')
  return result?.success === false
    ? issues
    : issues.filter((item) => !isNonBlockingBuilderAdviceItem(item))
}

function resultNonBlockingIssueItems(result: any) {
  return resultAdviceItems(result, 'issues').filter(isNonBlockingBuilderAdviceItem)
}

function builderAgentBlockingIssues(result: any) {
  const localAdvice = collectLocalBuilderConfigIssues()
  return unique([...localAdvice.issues, ...resultBlockingIssueItems(result)])
}

function stopBuilderExecutionWithAdvice(result: any, generatedSql = '') {
  const localAdvice = collectLocalBuilderConfigIssues()
  const blockingIssues = unique([...localAdvice.issues, ...resultBlockingIssueItems(result)])
  setBuilderAgentAdvice({
    severity: 'warning',
    intent: result?.intent || inferBuilderIntentText(),
    message: result?.message || '配置 Agent 判断当前配置需要调整，未执行 SQL',
    advice: result?.advice || '按下面配置项改完再生成。',
    issues: blockingIssues,
    suggestions: unique([
      ...localAdvice.suggestions,
      ...resultWarningItems(result),
      ...resultNonBlockingIssueItems(result),
      ...resultAdviceItems(result, 'suggestions'),
    ]),
    raw: result?.raw || '',
  })
  if (generatedSql && sqlBuilder.activeTab === 'sql') {
    form.sql = generatedSql
  }
  ElMessage.warning(
    blockingIssues[0] || result?.message || '配置 Agent 发现问题，已停止执行，请查看提示建议'
  )
}

function showLocalBuilderAgentAdvice() {
  const localAdvice = collectLocalBuilderConfigIssues()
  if (!localAdvice.issues.length && !localAdvice.suggestions.length) {
    clearBuilderAgentAdvice()
    return false
  }
  setBuilderAgentAdvice({
    severity: localAdvice.issues.length ? 'warning' : 'info',
    intent: inferBuilderIntentText(),
    message: localAdvice.issues.length ? localAdvice.issues[0] : '当前配置有优化建议',
    advice: '按下面配置项改。',
    issues: localAdvice.issues,
    suggestions: localAdvice.suggestions,
  })
  return true
}

function updateBuilderAgentAdviceFromResult(result: any, fallbackMessage = '') {
  const localAdvice = collectLocalBuilderConfigIssues()
  setBuilderAgentAdvice({
    severity: result?.success === false || localAdvice.issues.length ? 'warning' : 'info',
    intent: result?.intent || inferBuilderIntentText(),
    message: result?.message || fallbackMessage || localAdvice.issues[0] || '',
    advice: result?.advice || (localAdvice.suggestions.length ? '按下面配置项改。' : ''),
    issues: unique([
      ...localAdvice.issues,
      ...resultBlockingIssueItems(result),
    ]),
    suggestions: unique([
      ...localAdvice.suggestions,
      ...resultWarningItems(result),
      ...resultNonBlockingIssueItems(result),
      ...resultAdviceItems(result, 'suggestions'),
    ]),
    raw: result?.raw || '',
  })
}

async function generateBuilderAiSql() {
  if (!canUseSqlEditor.value) {
    ElMessage.warning(sqlEditorPermissionMessage)
    return false
  }
  if (!selectedExecutionDatasourceId.value) {
    ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    return false
  }
  if (blockMissingFixedTimeField()) {
    return false
  }
  const usesDashboardDateParameters = shouldUseDashboardDateParameters()
  if (usesDashboardDateParameters) {
    const validation = validateDashboardDateExpression(
      sqlBuilder.timeExpression,
      new Date(),
      'Asia/Shanghai'
    )
    if (!validation.valid) {
      ElMessage.warning(validation.message)
      return false
    }
  }
  const eventScopeIssues = builderBlockingScopeIssues()
  const retentionIssues = retentionBlockingIssues()
  const funnelIssues = funnelBlockingIssues()
  const distributionIssues = distributionBlockingIssues()
  const intervalIssues = intervalBlockingIssues()
  const pathIssues = pathBlockingIssues()
  const attributionIssues = attributionBlockingIssues()
  const rankingIssues = rankingBlockingIssues()
  if (retentionIssues.length || funnelIssues.length || distributionIssues.length || intervalIssues.length || pathIssues.length || attributionIssues.length || rankingIssues.length) {
    const localAdvice = collectLocalBuilderConfigIssues()
    const analysisIssues = retentionIssues.length
      ? retentionIssues
      : funnelIssues.length
        ? funnelIssues
        : distributionIssues.length
          ? distributionIssues
          : intervalIssues.length
            ? intervalIssues
              : pathIssues.length
                ? pathIssues
              : attributionIssues.length
                ? attributionIssues
                : rankingIssues
    const analysisLabel = retentionIssues.length
      ? '留存'
      : funnelIssues.length
        ? '漏斗'
        : distributionIssues.length
          ? '分布'
          : intervalIssues.length
            ? '间隔'
            : pathIssues.length
              ? '路径'
              : attributionIssues.length
                ? '归因'
                : '排行榜'
    setBuilderAgentAdvice({
      severity: 'warning',
      intent: inferBuilderIntentText(),
      message: analysisIssues[0],
      advice: `请先补全${analysisLabel}分析必填配置，再生成 SQL。`,
      issues: localAdvice.issues,
      suggestions: localAdvice.suggestions,
      raw: '',
    })
    ElMessage.warning(analysisIssues[0])
    return false
  }
  if (eventScopeIssues.length) {
    const localAdvice = collectLocalBuilderConfigIssues()
    setBuilderAgentAdvice({
      severity: 'warning',
      intent: inferBuilderIntentText(),
      message: eventScopeIssues[0],
      advice: '请先处理事件表范围问题，再生成 SQL。',
      issues: localAdvice.issues,
      suggestions: localAdvice.suggestions,
      raw: '',
    })
    ElMessage.warning(eventScopeIssues[0])
    return false
  }
  const invalidFormulaItems = invalidFormulaMetricItems()
  if (invalidFormulaItems.length) {
    const localAdvice = collectLocalBuilderConfigIssues()
    setBuilderAgentAdvice({
      severity: 'warning',
      intent: inferBuilderIntentText(),
      message: '公式指标公式语法错误',
      advice: '请先补全公式指标公式，再生成 SQL。',
      issues: localAdvice.issues,
      suggestions: localAdvice.suggestions,
      raw: '',
    })
    ElMessage.warning(invalidFormulaItems[0].validation.message || '公式指标公式语法错误')
    return false
  }
  let result: any = null
  try {
    await setLoadingPhase('正在分析')
    showLocalBuilderAgentAdvice()
    await setLoadingPhase('正在生成建议')
    result = await dashboardApi.generate_ai_sql({
      datasource: selectedExecutionDatasourceId.value,
      intent: '',
      chart_type: form.chartType,
      title: form.title,
      context: collectBuilderAiContext(),
    }, {
      timeout: 180000,
      requestOptions: { silent: true, retryCount: 0 },
    })
  } catch (error: any) {
    const message = formatRequestErrorMessage(error, '配置 Agent 调用失败')
    const localAdvice = collectLocalBuilderConfigIssues()
    setBuilderAgentAdvice({
      severity: 'warning',
      intent: inferBuilderIntentText(),
      message,
      advice: '先按当前配置问题改，或稍后重试 Agent。',
      issues: [message],
      suggestions: localAdvice.suggestions.length
        ? localAdvice.suggestions
        : sqlBuilder.metricItems.map((item, index) => describeBuilderMetricConfig(item, index)),
    })
    ElMessage.warning(`${message}，请查看提示建议`)
    return false
  } finally {
    clearBuilderLoading()
  }
  updateBuilderAgentAdviceFromResult(result)
  const generatedSql = String(result?.sql || '').trim()
  const blockingIssues = builderAgentBlockingIssues(result)
  if (blockingIssues.length > 0) {
    stopBuilderExecutionWithAdvice(result, generatedSql)
    return false
  }
  if (!generatedSql) {
    stopBuilderExecutionWithAdvice({
      ...result,
      message: result?.message || '配置 Agent 未生成 SQL',
      advice: result?.advice || '按下面配置项补全后再生成。',
      issues: unique(['配置 Agent 未返回可执行 SQL。', ...resultAdviceItems(result, 'issues')]),
    })
    return false
  }
  if (!generatedSqlMatchesBuilderMetrics(generatedSql)) {
    stopBuilderExecutionWithAdvice({
      ...result,
      severity: 'warning',
      message: 'AI SQL 与当前指标配置不一致',
      advice: result?.advice || '按当前指标配置重新生成，不执行这条 SQL。',
      issues: unique(['生成 SQL 的聚合方式与当前分析指标不一致。', ...resultAdviceItems(result, 'issues')]),
      raw: result?.raw || '',
    }, generatedSql)
    return false
  }
  form.sql = generatedSql
  sqlBuilder.activeTab = 'sql'
  if (result.title && !form.title) {
    form.title = result.title
  }
  const nextChartType = result.chart_type || result.chartType
  if (nextChartType && chartTypes.some((item) => item.value === nextChartType)) {
    form.chartType = nextChartType
  }
  if (sqlBuilder.analysisModel === 'funnel' || result.analysis_model === 'funnel') {
    const resultConfig = result.result_config || result.resultConfig || {}
    form.chartType = 'funnel'
    form.x = String(resultConfig.step_field || resultConfig.stepField || 'step_name')
    const valueField = String(resultConfig.value_field || resultConfig.valueField || 'step_count')
    form.y = [valueField]
  }
  if (sqlBuilder.analysisModel === 'distribution' || result.analysis_model === 'distribution') {
    form.chartType = 'table'
    form.columns = [DISTRIBUTION_DATE_COLUMN, DISTRIBUTION_TOTAL_COLUMN]
  }
  if (sqlBuilder.analysisModel === 'interval' || result.analysis_model === 'interval') {
    const resultConfig = result.result_config || result.resultConfig || {}
    form.chartType = 'table'
    form.columns = [
      String(resultConfig.date_field || resultConfig.dateField || 'interval_date'),
      String(resultConfig.entity_count_field || resultConfig.entityCountField || 'entity_count'),
      String(resultConfig.interval_count_field || resultConfig.intervalCountField || 'interval_count'),
      String(resultConfig.max_field || resultConfig.maxField || 'max_interval_seconds'),
      String(resultConfig.p75_field || resultConfig.p75Field || 'p75_interval_seconds'),
      String(resultConfig.median_field || resultConfig.medianField || 'median_interval_seconds'),
      String(resultConfig.p25_field || resultConfig.p25Field || 'p25_interval_seconds'),
      String(resultConfig.min_field || resultConfig.minField || 'min_interval_seconds'),
      String(resultConfig.avg_field || resultConfig.avgField || 'avg_interval_seconds'),
    ]
  }
  if (sqlBuilder.analysisModel === 'path' || result.analysis_model === 'path') {
    const resultConfig = result.result_config || result.resultConfig || {}
    form.chartType = 'sankey'
    form.x = String(resultConfig.source_field || resultConfig.sourceField || 'path_source')
    form.y = [String(resultConfig.value_field || resultConfig.valueField || 'path_value')]
    form.series = String(resultConfig.target_field || resultConfig.targetField || 'path_target')
    form.columns = [
      String(resultConfig.step_field || resultConfig.stepField || 'path_step'),
      form.x,
      form.series,
      form.y[0],
    ]
  }
    if (sqlBuilder.analysisModel === 'revenue' || result.analysis_model === 'revenue') {
    const resultConfig = result.result_config || result.resultConfig || {}
    const observationDays = clampRevenueObservationDays(
      resultConfig.observation_days || resultConfig.observationDays || sqlBuilder.revenue.observationDays
    )
    form.chartType = 'table'
    form.columns = [
      String(resultConfig.cohort_date_field || resultConfig.cohortDateField || 'cohort_date'),
      String(resultConfig.cohort_size_field || resultConfig.cohortSizeField || 'cohort_size'),
      ...Array.from({ length: observationDays + 1 }, (_, day) => `day_${day}`),
      ...(resultConfig.cost_value_field || resultConfig.costValueField
        ? [String(resultConfig.cost_value_field || resultConfig.costValueField)]
        : []),
      ...(resultConfig.roi_field || resultConfig.roiField
        ? [String(resultConfig.roi_field || resultConfig.roiField)]
        : []),
    ]
  }
  if (sqlBuilder.analysisModel === 'attribution' || result.analysis_model === 'attribution') {
    const resultConfig = result.result_config || result.resultConfig || {}
    form.chartType = 'table'
    form.columns = [
      String(resultConfig.event_field || resultConfig.eventField || 'attribution_event'),
      String(resultConfig.target_count_field || resultConfig.targetCountField || 'target_count'),
      String(resultConfig.attributed_value_field || resultConfig.attributedValueField || 'attributed_value'),
      String(resultConfig.contribution_rate_field || resultConfig.contributionRateField || 'contribution_rate'),
    ]
  }
  if (sqlBuilder.analysisModel === 'ranking' || result.analysis_model === 'ranking') {
    const resultConfig = result.result_config || result.resultConfig || {}
    form.chartType = 'table'
    form.columns = [
      String(resultConfig.rank_field || resultConfig.rankField || 'rank'),
      String(resultConfig.entity_field || resultConfig.entityField || 'ranking_entity'),
      String(resultConfig.metric_field || resultConfig.metricField || 'ranking_value'),
      ...(Array.isArray(resultConfig.simultaneous_metric_fields || resultConfig.simultaneousMetricFields)
        ? (resultConfig.simultaneous_metric_fields || resultConfig.simultaneousMetricFields).map(String)
        : []),
      ...(Array.isArray(resultConfig.property_fields || resultConfig.propertyFields)
        ? (resultConfig.property_fields || resultConfig.propertyFields).map(String)
        : []),
    ]
  }
  syncDashboardDateParameterUsage()
  if (result.success) {
    ElMessage.success('已生成 SQL')
  } else {
    ElMessage.warning(result.message || 'AI 生成的 SQL 需要调整，已放入 SQL 明细')
  }
  await previewAndPersistBuilderDraft()
  return result.success !== false
}

async function calculateBuilderSql() {
  if (sqlBuilder.activeTab === 'sql') {
    if (!form.sql.trim()) {
      ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
      return
    }
    await previewAndPersistBuilderDraft()
    return
  }
  await generateBuilderAiSql()
}

function isCurrentBuilderSchemaLoad(startViewInfo: any, requestSeq: number) {
  return (
    requestSeq === builderSchemaLoadSeq &&
    visible.value &&
    props.viewInfo === startViewInfo &&
    sqlBuilder.activeTab === 'builder'
  )
}

async function loadSchemaTables(startViewInfo: any, requestSeq: number) {
  function isCurrentSchemaLoad() {
    return (
      requestSeq === builderSchemaLoadSeq &&
      visible.value &&
      props.viewInfo === startViewInfo &&
      sqlBuilder.activeTab === 'builder'
    )
  }
  const datasourceId = selectedExecutionDatasourceId.value
  const tenantId = currentExternalMcpTenantId.value
  if (!datasourceId) {
    if (!isCurrentSchemaLoad()) {
      return
    }
    datasourceInfo.value = null
    schemaTables.value = previewSchemaTables()
    trackingConfig.value = null
    trackingEventCatalog.value = null
    return
  }
  if (!isCurrentSchemaLoad()) {
    return
  }
  schemaLoading.value = true
  try {
    const cacheKey = buildDashboardBuilderMetadataCacheKey({
      datasourceId,
      tenantId,
    })
    const metadata = await getCachedDashboardBuilderMetadata(cacheKey, async () => {
      const [metadata, trackingConfigResult, trackingEventCatalogResult] = await Promise.all([
        dashboardApi.execution_datasource_metadata(datasourceId),
        trackingConfigApi.get(),
        trackingConfigApi.eventCatalog(),
      ])
      const trackingTableRoleByName = new Map<string, string>()
      ;(Array.isArray(trackingConfigResult?.tables) ? trackingConfigResult.tables : []).forEach((table: any) => {
        const tableName = String(table?.table_name || table?.tableName || '').trim()
        const tableRole = String(table?.table_role || table?.tableRole || '').trim()
        if (tableName && tableRole) {
          trackingTableRoleByName.set(tableName, tableRole)
        }
      })
      const datasource = metadata || null
      const tables: any[] = metadata?.tables
      const normalizedTables = Array.isArray(tables) ? tables : []
      const defaultEventTable = String(
        trackingConfigResult?.default_event_table || trackingConfigResult?.defaultEventTable || '',
      ).trim()
      const tablesWithFields = await Promise.all(
        normalizedTables.map(async (table) => {
          const tableName = table?.table_name || table?.tableName || table?.name || table?.table || ''
          const tableRole = table?.table_role || table?.tableRole || trackingTableRoleByName.get(tableName) || ''
          const tableWithRole = tableRole ? { ...table, tableRole } : table
          if (tableName !== defaultEventTable || !table?.id) {
            return Array.isArray(table?.fields) ? tableWithRole : { ...tableWithRole, fields: [] }
          }
          try {
            const fields = await datasourceApi.fieldList(table.id, { fieldName: '', excludeContainerFields: false })
            return { ...tableWithRole, fields: Array.isArray(fields) ? fields : table.fields || [] }
          } catch {
            return Array.isArray(table?.fields) ? tableWithRole : { ...tableWithRole, fields: [] }
          }
        })
      )
      return {
        datasource,
        schemaTables: tablesWithFields,
        trackingConfig: trackingConfigResult,
        trackingEventCatalog: trackingEventCatalogResult,
      }
    }, (cachedMetadata) => Object.prototype.hasOwnProperty.call(cachedMetadata, 'trackingEventCatalog'))
    if (!isCurrentSchemaLoad()) {
      return
    }
    datasourceInfo.value = metadata.datasource
    trackingConfig.value = metadata.trackingConfig
    trackingEventCatalog.value = metadata.trackingEventCatalog
    schemaTables.value = metadata.schemaTables.length ? metadata.schemaTables : previewSchemaTables()
    sanitizeRetentionConfig()
    sanitizeFunnelConfig()
    sanitizeDistributionConfig()
    sanitizeIntervalConfig()
    sanitizePathConfig()
    sanitizeRevenueConfig()
    sanitizeAttributionConfig()
    sanitizeRankingConfig()
    if (sqlBuilder.analysisModel === 'event') {
      if (!sqlBuilder.metricItems.length && !sqlBuilder.calculatedMetrics.length) {
        addMetricItem()
      }
    }
  } catch {
    if (!isCurrentSchemaLoad()) {
      return
    }
    datasourceInfo.value = null
    schemaTables.value = previewSchemaTables()
    trackingConfig.value = null
    trackingEventCatalog.value = null
  } finally {
    if (requestSeq === builderSchemaLoadSeq) {
      schemaLoading.value = false
    }
  }
}

function ensureBuilderSchemaLoaded() {
  if (sqlBuilder.activeTab !== 'builder') {
    return
  }
  const startViewInfo = props.viewInfo
  const requestSeq = ++builderSchemaLoadSeq
  void loadSchemaTables(startViewInfo, requestSeq).then(() => {
    if (!isCurrentBuilderSchemaLoad(startViewInfo, requestSeq)) {
      return
    }
    const recoveredFilters = recoverMissingMetricFiltersFromSql()
    if (recoveredFilters) {
      persistEditorDraftToViewInfo()
    }
  })
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
  if (!isRadialPartitionChartType(form.chartType) && field === form.x) {
    return ''
  }
  return field
}

function sanitizeSeriesSelection() {
  if (form.chartType === 'donut') {
    return
  }
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

function normalizePivotGranularity(value: any, fallback: PivotGranularity = 'day'): PivotGranularity {
  return value === 'week' || value === 'month' || value === 'day' ? value : fallback
}

function defaultPivotGranularity(): PivotGranularity {
  const detected = detectTrendAxisGranularity(sourcePreview.data, form.pivotTimeField)
  return detected === 'week' || detected === 'month' ? detected : 'day'
}

function defaultPivotAggregation() {
  return defaultPivotAggregationForAxes(toAxes(form.y, { metrics: true }), sourcePreview.data)
}

function configuredDashboardTimeField() {
  return String(sqlBuilder.timeField || form.pivotTimeField || '').trim()
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
    timeField: form.pivotTimeField,
    metricFields: form.y,
  })
}

function sanitizePivotTimeField() {
  const timeFields = pivotTimeFieldOptions.value.map((item) => item.value)
  if (!form.pivotTimeField || !timeFields.includes(form.pivotTimeField)) {
    form.pivotTimeField = ''
  }
  return timeFields.length > 0
}

function normalizePivotSelections() {
  sanitizeSeriesSelection()
  const hasSelectableTimeField = sanitizePivotTimeField()
  const fields = sourcePreview.fields
  if (form.pivotGroupField && (!fields.length || !fields.includes(form.pivotGroupField))) form.pivotGroupField = ''
  if (!hasSelectableTimeField) {
    form.pivotEnabled = false
    form.pivotGroupValueMode = 'all'
    form.pivotGroupValues = []
    form.pivotGroupEnabled = false
    return
  }
  if (!form.pivotGroupField) {
    form.pivotGroupEnabled = false
  }
}

function alignSeriesAndPivotGroupFields() {
  if (!form.pivotEnabled || !showSeries.value) {
    return false
  }
  const timeFields = pivotTimeFieldOptions.value.map((item) => item.value)
  if (!form.pivotTimeField || !timeFields.includes(form.pivotTimeField)) {
    return false
  }
  const seriesField = effectiveSeriesField.value
  const groupField = form.pivotGroupField
  if (!seriesField || !groupField || seriesField === groupField) {
    return false
  }
  if (!sourcePreview.fields.includes(seriesField) || !sourcePreview.fields.includes(groupField)) {
    return false
  }
  const seriesValueCount = collectPivotGroupValueCounts(seriesField).size
  const groupValueCount = collectPivotGroupValueCounts(groupField).size
  const looksSwapped =
    groupValueCount > 0 &&
    groupValueCount <= 20 &&
    seriesValueCount >= Math.max(groupValueCount * 2, groupValueCount + 10)
  if (!looksSwapped) {
    return false
  }
  form.series = groupField
  form.pivotGroupField = seriesField
  form.pivotGroupEnabled = true
  return true
}

function initPivotConfig(pivot?: any) {
  form.pivotEnabled = pivot?.enabled === true
  form.pivotTimeField = pivot?.time_field || ''
  form.pivotGroupField = pivot?.group_field || ''
  form.pivotGroupEnabled =
    typeof pivot?.group_enabled === 'boolean' ? pivot.group_enabled : Boolean(form.pivotGroupField)
  form.pivotRangeEnabled = pivot?.range_enabled !== false
  form.pivotGranularity = normalizePivotGranularity(pivot?.granularity)
  form.pivotRange = pivot?.range || 'source'
  form.pivotCustomStart = pivot?.custom_start || ''
  form.pivotCustomEnd = pivot?.custom_end || ''
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  const pivotDateExpression = null
  if (dateExpressionEnabled.value) {
    if (!sqlBuilder.timeExpression) {
      dateExpressionConfigError.value = '日期表达式配置无效'
    } else if (
      pivotDateExpression &&
      JSON.stringify(sqlBuilder.timeExpression) !== JSON.stringify(pivotDateExpression)
    ) {
      dateExpressionConfigError.value = '日期表达式配置不一致'
    } else {
      dateExpressionConfigError.value = ''
    }
  } else {
    dateExpressionConfigError.value = ''
  }
  form.pivotGroupValues = []
  form.pivotGroupValueMode = normalizePivotGroupValueMode(pivot)
  initializedPivotGroupValueField.value = ''
  normalizePivotSelections()
  if (!form.pivotEnabled) {
    form.pivotGroupValues = []
    form.pivotGroupValueMode = 'all'
    initializedPivotGroupValueField.value = ''
    return
  }
  form.pivotGroupValues = form.pivotGroupValueMode === 'custom' && Array.isArray(pivot?.group_values)
    ? unique(pivot.group_values.map(normalizePivotGroupValue))
    : pivotGroupValueOptions.value.map((item) => item.value)
  initializedPivotGroupValueField.value = activePivotGroupValueField.value
  syncPivotGroupValues()
  if (!pivot?.granularity) {
    form.pivotGranularity = defaultPivotGranularity()
  }
}

function buildPivotConfig(options: { includeGroupValues?: boolean } = {}) {
  if (!supportsPivotConfig.value || !form.pivotEnabled) {
    return { enabled: false }
  }
  const groupField = activePivotGroupValueField.value
  const pivotGroupValues = groupField ? unique(form.pivotGroupValues.map(normalizePivotGroupValue)) : []
  const config: Record<string, any> = {
    enabled: supportsPivotConfig.value && form.pivotEnabled,
    client_filter_only: props.viewInfo?.pivot?.client_filter_only === true,
    time_field: form.pivotTimeField,
    range_enabled: form.pivotRangeEnabled,
  }
  Object.assign(config, {
    metric_fields: [...form.y],
    metric_aggregations: resolvePivotMetricAggregations(toAxes(form.y, { metrics: true }), sourcePreview.data),
    metric_field: form.y[0] || '',
    group_field: groupField,
    group_enabled: Boolean(
      groupField &&
      (form.pivotGroupEnabled ||
        (form.pivotGroupValueMode === 'custom' && pivotGroupValues.length > 0))
    ),
    dimensions: inferredPivotDimensions(),
    granularity: form.pivotGranularity,
    range: form.pivotRange,
    custom_start: form.pivotCustomStart,
    custom_end: form.pivotCustomEnd,
    aggregation: defaultPivotAggregation(),
  })
  if (options.includeGroupValues !== false) {
    Object.assign(
      config,
      buildPersistedPivotGroupValueSelection(form.pivotGroupValueMode, pivotGroupValues)
    )
  }
  return config
}

function previewPivotPayload() {
  if (!supportsPivotConfig.value || !form.pivotEnabled) {
    return undefined
  }
  return buildPivotConfig({ includeGroupValues: false })
}

function sourcePreviewPivotPayload() {
  const pivot = previewPivotPayload()
  return pivot ? buildDashboardDateSourcePreviewPivot(pivot) : undefined
}

function dashboardDateFilterConfigForWrite() {
  const expression = sqlBuilder.timeExpression
    ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
    : undefined
  return buildDashboardDateFilterConfig(
    form.sql,
    SQL_EDITOR_DATE_PARAMETER_TYPE,
    expression
  )
}

function dashboardDateFilterRequestPayload() {
  const customRange = form.pivotRangeEnabled && form.pivotRange === 'custom'
    ? [form.pivotCustomStart, form.pivotCustomEnd] as [string, string]
    : undefined
  return buildDashboardDateFilterRequest(dashboardDateFilterConfigForWrite(), customRange)
}

function dashboardDateParameterValidationErrorKey() {
  if (!hasSqlSource.value) {
    return ''
  }
  const activeTokens = scanDashboardDateParameterTokens(form.sql)
  if (activeTokens.length === 0) {
    return ''
  }
  try {
    dashboardDateFilterConfigForWrite()
    return ''
  } catch {
    return 'dashboard.pivot_date_parameter_type_invalid'
  }
}

function dateExpressionValidationError() {
  if (!dateExpressionEnabled.value) {
    return ''
  }
  if (dateExpressionConfigError.value) {
    return dateExpressionConfigError.value
  }
  const validation = validateDashboardDateExpression(
    sqlBuilder.timeExpression,
    new Date(),
    'Asia/Shanghai'
  )
  if (!validation.valid) {
    return validation.message
  }
  if (
    form.pivotEnabled &&
    !configuredDashboardTimeField() &&
    eventFieldScope.value.status !== 'datasource-mismatch'
  ) {
    return '请选择时间字段'
  }
  const activeDateTokens = scanDashboardDateParameterTokens(form.sql)
  if (activeDateTokens.length === 0) {
    return t('dashboard.date_expression_parameter_hint')
  }
  return ''
}

function applyDateExpression(value: DashboardDateExpression) {
  sqlBuilder.timeExpression = cloneDashboardDateExpression(value)
  sqlBuilder.timeRange = 'expression'
  dateExpressionConfigError.value = ''
}

function currentPreviewSignature() {
  return JSON.stringify({
    analysisModel: sqlBuilder.analysisModel,
    retention: sqlBuilder.analysisModel === 'retention' ? sqlBuilder.retention : null,
    funnel: sqlBuilder.analysisModel === 'funnel' ? sqlBuilder.funnel : null,
    distribution: sqlBuilder.analysisModel === 'distribution' ? sqlBuilder.distribution : null,
    interval: sqlBuilder.analysisModel === 'interval' ? sqlBuilder.interval : null,
    path: sqlBuilder.analysisModel === 'path' ? sqlBuilder.path : null,
    revenue: sqlBuilder.analysisModel === 'revenue' ? sqlBuilder.revenue : null,
    attribution: sqlBuilder.analysisModel === 'attribution' ? sqlBuilder.attribution : null,
    ranking: sqlBuilder.analysisModel === 'ranking' ? sqlBuilder.ranking : null,
    sources: [...form.sourceTypes],
    sql: hasSqlSource.value
      ? {
          datasource: selectedExecutionDatasourceId.value,
          sql: form.sql.trim(),
          pivot: previewPivotPayload() || { enabled: false },
          dateFilter: dashboardDateFilterRequestPayload(),
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
  } catch {
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
  } catch {
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

function setSourceTypeEnabled(type: ChartDataSourceType, enabled: boolean) {
  const nextSources = enabled
    ? Array.from(new Set([...form.sourceTypes, type]))
    : form.sourceTypes.filter((item) => item !== type)
  handleSourceTypesChange(nextSources as ChartDataSourceType[])
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
  } catch {
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
    form.pivotGroupValueMode = 'all'
    form.pivotGroupValues = sourceValues
  } else if (form.pivotGroupValueMode === 'all') {
    form.pivotGroupValues = sourceValues
  } else {
    form.pivotGroupValues = selected.filter((value) => optionValues.includes(value))
  }
  initializedPivotGroupValueField.value = field
}

function selectAllPivotGroupValues() {
  form.pivotGroupValueMode = 'all'
  syncPivotGroupValues({ forceAll: true })
  previewVersion.value += 1
}

function clearPivotGroupValues() {
  form.pivotGroupValueMode = 'custom'
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
  const selected = unique(values.map(normalizePivotGroupValue))
  const available = pivotGroupValueOptions.value.map((item) => item.value)
  const selectedSet = new Set(selected)
  form.pivotGroupValueMode =
    available.length > 0 && available.every((value) => selectedSet.has(value)) ? 'all' : 'custom'
  form.pivotGroupValues = form.pivotGroupValueMode === 'all' ? available : selected
}

function resetFieldSelections() {
  const fields = sourcePreview.fields
  if (!fields.length) {
    form.columns = []
    if (form.chartType !== 'donut') {
      form.x = ''
      form.y = []
      form.series = ''
    }
    return
  }
  form.columns = form.columns.filter((field) => fields.includes(field))
  if (isRetentionAnalysis.value || isDistributionAnalysis.value) {
    form.columns = [...fields]
  } else if (form.columns.length === 0) {
    form.columns = fields.slice(0, 8)
  }
  if (form.chartType !== 'donut') {
    form.y = form.y.filter((field) => fields.includes(field))
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
  resetSqlBuilderState()
  restoreSqlBuilderState(sourceConfig.sql?.builder || sourceConfig.builder)
  normalizeDistributionTableViewInfo(viewInfo)
  const normalizedConfig = normalizeDashboardChartConfig(viewInfo)
  const pivotDateExpression = normalizeDashboardDateExpression(normalizedConfig.dateFilter?.expression)
  if (pivotDateExpression) {
    sqlBuilder.timeExpression = cloneDashboardDateExpression(pivotDateExpression)
  }
  const fields = collectFields(viewInfo)
  const currentFields = collectCurrentPreviewFields(viewInfo)
  form.sourceTypes = sourceTypes
  form.primarySource = sourceTypes.includes('external_mcp') && !sourceTypes.includes('sql') ? 'external_mcp' : 'sql'
  form.sql = viewInfo.sql || ''
  form.title = chart.title || ''
  form.chartType = isRetentionAnalysis.value
    ? 'table'
    : isFunnelAnalysis.value
      ? 'funnel'
      : isDistributionAnalysis.value
        ? 'table'
      : isIntervalAnalysis.value
        ? 'table'
      : isPathAnalysis.value
        ? 'sankey'
      : isAttributionAnalysis.value
        ? 'table'
      : isRankingAnalysis.value
        ? 'table'
      : (chart.sourceType || chart.type || 'table')
  form.columns = axisValues(chart.columns)
  form.x = axisValues(chart.xAxis)[0] || ''
  form.y = axisValues(chart.yAxis)
  pruneAutoSeededMetricItemsForFormulaOnlyBuilder()
  const persistedSeries = axisValues(chart.series)
  donutSeriesFields.value = persistedSeries
  form.series = persistedSeries[0] || ''
  form.multiQuotaName = t('dashboard.metric_type')
  sourcePreview.fields = fields
  sourcePreview.data = viewInfo.data?.source_data || viewInfo.data?.data || []
  preview.fields = currentFields.length ? currentFields : fields
  preview.data = viewInfo.data?.data || []
  preview.status = 'success'
  preview.message = ''
  preview.raw = viewInfo.data?.raw
  setSourceResult('sql', normalizePreviewResultSnapshot(
    shapeDistributionTableResult(sourceConfig.sql?.lastResult || {}, sqlBuilder)
  ))
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
  executionDatasourceOptions.value = []
  selectedExecutionDatasourceId.value = normalizeExecutionDatasourceId(viewInfo?.datasource)
  executionDatasourceError.value = ''
  lastPreviewSql.value = form.sql.trim()
  resetFieldSelections()
  initInsightConfig(chart.insight)
  initForecastConfig(chart.forecast)
  initPivotConfig(normalizedConfig.pivot)
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  lastPreviewSignature.value = currentPreviewSignature()
  previewVersion.value += 1
  if (hasMcpSource.value) {
    void loadMcpServers().then(() => loadMcpTools())
  } else {
    mcpServers.value = []
    mcpTools.value = []
    mcpFilterOptions.value = {}
  }
  if (hasSqlSource.value) {
    void loadExecutionDatasources(viewInfo)
  } else {
    ensureBuilderSchemaLoaded()
  }
}

function normalizeExecutionDatasourceId(value: unknown) {
  const datasourceId = Number(value)
  return Number.isInteger(datasourceId) && datasourceId > 0 ? datasourceId : null
}

async function loadExecutionDatasources(viewInfo: any) {
  const initialPreviewSignature = currentPreviewSignature()
  const initialRecordedPreviewSignature = lastPreviewSignature.value
  try {
    const options = await dashboardApi.execution_datasources()
    executionDatasourceOptions.value = Array.isArray(options) ? options : []
    const savedDatasourceId = normalizeExecutionDatasourceId(viewInfo?.datasource)
    const legacyDatasourceId = normalizeExecutionDatasourceId(
      chartSourceConfig(viewInfo)?.sql?.datasource
    )
    if (savedDatasourceId && legacyDatasourceId && savedDatasourceId !== legacyDatasourceId) {
      const savedName = executionDatasourceOptions.value.find((item) => item.id === savedDatasourceId)?.name || savedDatasourceId
      const legacyName = executionDatasourceOptions.value.find((item) => item.id === legacyDatasourceId)?.name || legacyDatasourceId
      selectedExecutionDatasourceId.value = null
      executionDatasourceError.value = `图表执行数据源配置冲突：外层为 ${savedName}，旧配置为 ${legacyName}。请重新选择数据源并预览后保存。`
      return
    }
    if (!savedDatasourceId && legacyDatasourceId) {
      selectedExecutionDatasourceId.value = null
      executionDatasourceError.value = '图表只有旧版执行数据源配置，需完成数据源与 Schema 校验后迁移。'
      return
    }
    if (!savedDatasourceId && !legacyDatasourceId && String(viewInfo?.sql || '').trim()) {
      selectedExecutionDatasourceId.value = null
      executionDatasourceError.value = '图表未配置执行数据源，请重新选择数据源并预览后保存。'
      return
    }
    if (savedDatasourceId && !executionDatasourceOptions.value.some((item) => item.id === savedDatasourceId)) {
      selectedExecutionDatasourceId.value = null
      executionDatasourceError.value = '当前图表选择的数据源已不在此空间可用范围内。'
      return
    }
    const canRebaseAutoSelectedDatasource =
      !savedDatasourceId &&
      currentPreviewSignature() === initialPreviewSignature &&
      lastPreviewSignature.value === initialRecordedPreviewSignature
    selectedExecutionDatasourceId.value = savedDatasourceId ||
      executionDatasourceOptions.value.find((item) => item.role === 'bound')?.id || null
    if (!selectedExecutionDatasourceId.value) {
      executionDatasourceError.value = '当前空间未配置可用于图表 SQL 的数据源。'
      return
    }
    if (canRebaseAutoSelectedDatasource) {
      lastPreviewSignature.value = currentPreviewSignature()
    }
    ensureBuilderSchemaLoaded()
  } catch {
    executionDatasourceOptions.value = []
    selectedExecutionDatasourceId.value = null
    executionDatasourceError.value = '图表执行数据源加载失败。'
  }
}

function resetExecutionDatasourceDependentState() {
  form.sql = ''
  form.columns = []
  form.x = ''
  form.y = []
  form.series = ''
  form.pivotEnabled = false
  form.pivotTimeField = ''
  form.pivotGroupField = ''
  form.pivotGroupValueMode = 'all'
  form.pivotGroupValues = []
  sourcePreview.fields = []
  sourcePreview.data = []
  preview.fields = []
  preview.data = []
  preview.status = 'success'
  preview.message = ''
  preview.raw = undefined
  setSourceResult('sql', createEmptyPreviewResultSnapshot())
  clearMergeState()
  resetSqlBuilderState()
  datasourceInfo.value = null
  schemaTables.value = []
  trackingConfig.value = null
  trackingEventCatalog.value = null
  lastPreviewSql.value = ''
  lastPreviewSignature.value = ''
  previewVersion.value += 1
}

function handleExecutionDatasourceChange() {
  executionDatasourceError.value = ''
  resetExecutionDatasourceDependentState()
  ensureBuilderSchemaLoaded()
}

watch(
  () => sqlBuilder.activeTab,
  (activeTab) => {
    if (activeTab === 'builder') {
      ensureBuilderSchemaLoaded()
    }
  }
)

watch(
  () => activePivotGroupValueField.value,
  (field, previousField) => {
    if (!form.pivotEnabled || !field || field === previousField) {
      return
    }
    syncPivotGroupValues({ forceAll: true })
  }
)

watch(
  () => form.pivotEnabled,
  (enabled) => {
    if (!enabled) {
      return
    }
    sanitizePivotTimeField()
    if (form.pivotGroupField && !sourcePreview.fields.includes(form.pivotGroupField)) {
      form.pivotGroupField = ''
      form.pivotGroupValueMode = 'all'
      form.pivotGroupValues = []
      form.pivotGroupEnabled = false
    }
  }
)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      try {
        initEditor()
      } catch (error) {
        if ((error as Error)?.message !== DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED) {
          throw error
        }
        ElMessage.error('图表配置已过期，请重新配置')
        visible.value = false
      }
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
    form.pivotDateParameterType,
    form.pivotGroupValues.join('|'),
    sqlBuilder.dateExpressionPickerEnabled,
    JSON.stringify(sqlBuilder.timeExpression),
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
  if (!selectedExecutionDatasourceId.value) {
    ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    return null
  }
  if (!form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return null
  }
  const expressionValidationError = dateExpressionValidationError()
  if (expressionValidationError) {
    ElMessage.warning(expressionValidationError)
    return null
  }
  const dateParameterValidationError = dashboardDateParameterValidationErrorKey()
  if (dateParameterValidationError) {
    ElMessage.warning(t(dateParameterValidationError))
    return null
  }
  const shouldPreviewPivot = supportsPivotConfig.value && form.pivotEnabled
  if (shouldPreviewPivot) {
    const sourceResult = await dashboardApi.preview_sql({
      datasource: selectedExecutionDatasourceId.value,
      sql: form.sql.trim(),
      pivot: sourcePreviewPivotPayload(),
      date_filter: dashboardDateFilterRequestPayload(),
    })
    const sourceSnapshot = previewResultSnapshot(shapeDistributionTableResult(sourceResult, sqlBuilder))
    setSourceResult('sql', sourceSnapshot)
    updateSourcePreviewResult(sourceSnapshot)
    resetFieldSelections()
    normalizePivotSelections()
    if (alignSeriesAndPivotGroupFields()) {
      syncPivotGroupValues({ forceAll: true })
    } else {
      syncPivotGroupValues()
    }
    if (sourceSnapshot.status === 'failed') {
      return sourceSnapshot
    }
  }
  const result = await dashboardApi.preview_sql({
    datasource: selectedExecutionDatasourceId.value,
    sql: form.sql.trim(),
    pivot: previewPivotPayload(),
    date_filter: dashboardDateFilterRequestPayload(),
  })
  const snapshot = previewResultSnapshot(shapeDistributionTableResult(result, sqlBuilder))
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
  } catch {
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

async function runPreview(options: { useGlobalLoading?: boolean } = {}) {
  if (!hasSqlSource.value && !hasMcpSource.value) {
    ElMessage.warning(mt('chart_source_required'))
    return false
  }
  if (hasSqlSource.value && !canUseSqlEditor.value) {
    ElMessage.warning(sqlEditorPermissionMessage)
    return false
  }
  if (blockMissingFixedTimeField()) {
    return false
  }
  const useGlobalLoading = options.useGlobalLoading !== false
  if (useGlobalLoading) {
    loadingText.value = loadingText.value || '正在执行'
    loading.value = true
  }
  try {
    clearMergeState()
    let nextPreview: PreviewResultSnapshot | null = null
    if (isMixedSource.value) {
      const sqlResult = await previewSqlSource()
      if (!sqlResult) {
        return false
      }
      const mcpResult = await previewMcpSource()
      if (!mcpResult) {
        return false
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
      return false
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
      setBuilderAgentAdvice({
        severity: 'warning',
        intent: inferBuilderIntentText(),
        message: 'SQL 执行失败',
        advice: '当前 SQL 数据库执行失败。',
        issues: [preview.message || t('dashboard.sql_editor_preview_failed')],
        suggestions: [
          'SQL 明细：检查 SELECT、WHERE、GROUP BY 里的字段是否都在当前数据源。',
          '超时：时间范围缩短，或加产品/事件/国家等筛选。',
          '字段不存在：回到图表配置，用数据字典重新选择字段。',
        ],
      })
      ElMessage.error(preview.message || t('dashboard.sql_editor_preview_failed'))
    } else {
      ElMessage.success(t('dashboard.sql_editor_preview_success'))
      await nextTick()
    }
    return true
  } finally {
    if (useGlobalLoading) {
      loading.value = false
      loadingText.value = ''
    }
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

  if (form.chartType === 'donut') {
    chart.yAxis = toAxes(form.y, { metrics: true })
    chart.series = toAxes(donutSeriesFields.value)
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

function donutFieldMappingValidationErrorKey() {
  if (form.chartType !== 'donut') {
    return ''
  }
  if (form.y.length === 0) {
    return 'dashboard.sql_editor_donut_value_required'
  }
  if (form.y.length !== 1) {
    return 'dashboard.sql_editor_donut_single_value'
  }
  if (!sourcePreview.fields.includes(form.y[0])) {
    return 'dashboard.sql_editor_donut_value_invalid'
  }
  if (donutSeriesFields.value.length === 0) {
    return 'dashboard.sql_editor_donut_category_required'
  }
  if (donutSeriesFields.value.length !== 1) {
    return 'dashboard.sql_editor_donut_single_category'
  }
  const categoryField = donutSeriesFields.value[0]
  if (!sourcePreview.fields.includes(categoryField) || !normalizeSeriesField(categoryField)) {
    return 'dashboard.sql_editor_donut_category_invalid'
  }
  return ''
}

function validateDonutFieldMapping() {
  const errorKey = donutFieldMappingValidationErrorKey()
  if (!errorKey) {
    return true
  }
  ElMessage.warning(t(errorKey))
  return false
}

function validateBeforeApply() {
  if (form.sourceTypes.length === 0) {
    ElMessage.warning(mt('chart_source_required'))
    return false
  }
  if (hasSqlSource.value && !canUseSqlEditor.value) {
    ElMessage.warning(sqlEditorPermissionMessage)
    return false
  }
  if (hasSqlSource.value && !selectedExecutionDatasourceId.value) {
    ElMessage.warning(executionDatasourceError.value || '请选择图表执行数据源。')
    return false
  }
  if (blockMissingFixedTimeField()) {
    return false
  }
  if (hasSqlSource.value && !form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return false
  }
  const expressionValidationError = dateExpressionValidationError()
  if (expressionValidationError) {
    ElMessage.warning(expressionValidationError)
    return false
  }
  const dateParameterValidationError = dashboardDateParameterValidationErrorKey()
  if (dateParameterValidationError) {
    ElMessage.warning(t(dateParameterValidationError))
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
  if (!validateDonutFieldMapping()) {
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
  if (!isRadialPartitionChartType(form.chartType) && !form.x) {
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
  if (
    showPivotGroupValueConfig.value &&
    form.pivotGroupEnabled &&
    form.pivotGroupValueMode === 'custom' &&
    form.pivotGroupValues.length === 0
  ) {
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
    ...(result.raw !== undefined ? { raw: result.raw } : {}),
  }
}

function currentMcpArgumentsForSave(strict: boolean) {
  if (!hasMcpSource.value) {
    return {}
  }
  try {
    return cleanMcpArguments(parseJsonObject(form.mcpArgumentsText))
  } catch {
    if (strict) {
      ElMessage.warning(mt('mcp_editor_invalid_arguments'))
      return null
    }
    const sourceConfig = chartSourceConfig(props.viewInfo)
    const previousArguments = sourceConfig.mcp?.arguments || props.viewInfo?.mcp?.arguments || {}
    return previousArguments && typeof previousArguments === 'object' && !Array.isArray(previousArguments)
      ? { ...previousArguments }
      : {}
  }
}

function writeEditorStateToViewInfo(options: {
  strictMcpArguments?: boolean
  emit?: boolean
  close?: boolean
  notify?: boolean
  message?: string
} = {}) {
  if (!props.viewInfo) {
    return false
  }
  if (!validateDonutFieldMapping()) {
    return false
  }
  const strictMcpArguments = options.strictMcpArguments !== false
  const mcpArgumentsValue = currentMcpArgumentsForSave(strictMcpArguments)
  if (mcpArgumentsValue === null) {
    return false
  }
  const existingSourceConfig = chartSourceConfig(props.viewInfo)
  const { builder: _legacyBuilder, ...sourceConfigBase } = existingSourceConfig
  const {
    datasource: _legacySqlDatasource,
    ...sourceSqlConfigBase
  } = existingSourceConfig.sql || {}
  void _legacyBuilder
  void _legacySqlDatasource
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
  delete props.viewInfo.status
  delete props.viewInfo.dataState
  props.viewInfo.loadingProgress = 100
  delete props.viewInfo.message
  const normalizedConfig = normalizeDashboardChartConfig({
    ...props.viewInfo,
    sql: props.viewInfo.sql,
    pivot: buildPivotConfig(),
    dateFilter: dashboardDateFilterConfigForWrite(),
  })
  props.viewInfo.chart = buildChart()
  props.viewInfo.configVersion = normalizedConfig.configVersion
  props.viewInfo.dateFilter = normalizedConfig.dateFilter
  props.viewInfo.pivot = normalizedConfig.pivot
  if (hasSqlSource.value) {
    props.viewInfo.datasource = selectedExecutionDatasourceId.value
  } else {
    props.viewInfo.datasource = null
  }
  props.viewInfo.sourceConfig = {
    ...sourceConfigBase,
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
          ...sourceSqlConfigBase,
          sql: form.sql.trim(),
          builder: builderConfigForSave(),
          lastResult: sourceResultForSave('sql'),
        }
      : null,
    mcp: hasMcpSource.value
      ? {
          ...(existingSourceConfig.mcp || {}),
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
  if (options.emit !== false) {
    emits('applied', props.viewInfo)
  }
  if (options.close) {
    visible.value = false
  }
  if (options.notify) {
    ElMessage.success(options.message || t('dashboard.sql_editor_applied'))
  }
  return true
}

function persistEditorDraftToViewInfo() {
  return writeEditorStateToViewInfo({
    strictMcpArguments: false,
    emit: true,
  })
}

async function previewAndPersistBuilderDraft() {
  let previewCompleted = false
  try {
    await setLoadingPhase('正在执行')
    previewCompleted = await runPreview({ useGlobalLoading: false })
  } catch (error: any) {
    const message = error?.message || t('dashboard.sql_editor_preview_failed')
    const failedSnapshot = {
      fields: [] as string[],
      data: [] as Array<Record<string, any>>,
      status: 'failed',
      message,
    }
    updatePreviewResult(failedSnapshot)
    if (hasSqlSource.value) {
      setSourceResult('sql', failedSnapshot)
    }
    ElMessage.error(message)
    previewCompleted = true
  } finally {
    clearBuilderLoading()
    if (previewCompleted) {
      persistEditorDraftToViewInfo()
    }
  }
}

function applyChange() {
  if (!props.viewInfo || !validateBeforeApply()) return
  writeEditorStateToViewInfo({
    strictMcpArguments: true,
    emit: true,
    close: true,
    notify: true,
  })
}

function handleChartTypeChange(chartType: ChartTypes) {
  if (chartType === 'donut') {
    donutSeriesFields.value = form.series ? [form.series] : []
  }
}

function handleSeriesFieldChange(series: string) {
  if (form.chartType === 'donut') {
    donutSeriesFields.value = series ? [series] : []
  }
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
        <div v-if="!hasSqlSource && canUseSqlEditor" class="source-section-toggle">
          <div class="source-section-title">SQL 数据源</div>
          <el-checkbox v-model="sqlSourceEnabled" class="source-inline-checkbox">SQL</el-checkbox>
        </div>
        <div v-if="hasSqlSource && canUseSqlEditor" class="sql-builder-panel">
          <div class="sql-builder-header">
            <div class="sql-builder-tabs">
              <button
                type="button"
                :class="{ active: sqlBuilder.activeTab === 'builder' }"
                @click="sqlBuilder.activeTab = 'builder'"
              >
                图表配置
              </button>
              <button
                type="button"
                :class="{ active: sqlBuilder.activeTab === 'sql' }"
                @click="sqlBuilder.activeTab = 'sql'"
              >
                SQL 明细
              </button>
            </div>
            <div class="sql-builder-header-actions">
              <el-tooltip
                v-if="hasBuilderAgentAdvice"
                content="查看配置 Agent 建议"
                placement="bottom"
              >
                <button
                  type="button"
                  class="builder-advice-button"
                  :class="{ warning: builderAgentAdvice.severity === 'warning' }"
                  @click="builderAgentAdvice.visible = true"
                >
                  <el-icon><WarningFilled /></el-icon>
                </button>
              </el-tooltip>
              <el-checkbox v-model="sqlSourceEnabled" class="source-inline-checkbox">SQL</el-checkbox>
            </div>
          </div>

          <div v-if="sqlBuilder.activeTab === 'builder'" class="sql-builder-builder-pane">
            <el-alert
              v-if="eventFieldScope.mode === 'event' && eventFieldScope.status !== 'active'"
              class="event-scope-alert"
              :title="eventFieldScope.message"
              type="warning"
              :closable="false"
              show-icon
            />
            <div
              v-loading="schemaLoading || builderLoading"
              :element-loading-text="builderLoading ? loadingText : ''"
              class="sql-builder-content"
              @click="activeFormulaMetricId = ''"
            >
            <section class="builder-section analysis-model-section">
              <div class="analysis-model-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>分析模型</span>
                  </div>
                </div>
                <el-select
                  v-model="sqlBuilder.analysisModel"
                  class="analysis-model-select"
                  @change="handleAnalysisModelChange"
                >
                  <el-option
                    v-for="option in analysisModelOptions"
                    :key="option.value"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
              </div>
            </section>

            <section v-if="!isRetentionAnalysis && !isFunnelAnalysis && !isDistributionAnalysis && !isIntervalAnalysis && !isPathAnalysis && !isRevenueAnalysis && !isAttributionAnalysis && !isRankingAnalysis" class="builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>分析指标</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加指标" @click="addMetricItem">
                    <el-icon><Plus /></el-icon>
                  </button>
                  <button type="button" class="builder-icon-button formula-entry-button" title="添加公式指标" @click.stop="addCalculatedMetricItem">
                    Σ
                  </button>
                </div>
              </div>
              <div class="metric-list">
                <div
                  v-for="(item, index) in sqlBuilder.metricItems"
                  :key="item.id"
                  class="metric-item"
                >
                  <div class="metric-index">{{ index + 1 }}</div>
                  <div class="metric-body">
                    <el-input
                      v-model="item.alias"
                      class="metric-title-input"
                      size="small"
                      clearable
                      :placeholder="metricTitle(item, index)"
                    />
                    <div
                      class="metric-chip-row"
                      :class="{ 'has-metric-field': item.aggregation !== 'count' }"
                    >
                      <BuilderFieldPicker
                        v-model="item.field"
                        class="metric-field-select"
                        :options="analysisFieldOptions"
                        :loading="schemaLoading"
                        :mode="analysisFieldPickerMode"
                        :placeholder="formulaFieldPickerPlaceholder"
                      />
                      <span class="metric-of">的</span>
                        <el-select
                          v-model="item.aggregation"
                          size="small"
                          class="metric-aggregation"
                          @change="item.metric = optionExists(item.metric, metricMeasureFieldOptions(item)) ? item.metric : ''"
                        >
                        <el-option
                          v-for="option in builderAggregationOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                      <BuilderFieldPicker
                        v-if="item.aggregation !== 'count'"
                        v-model="item.metric"
                        :options="metricMeasureFieldOptions(item)"
                        :loading="schemaLoading"
                        mode="metric"
                        placeholder="计算字段"
                      />
                      <button type="button" class="builder-icon-button danger" @click="removeMetricItem(index)">
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                    <BuilderFilterTree
                      v-if="item.filters.length"
                      :nodes="item.filters"
                      :logic="item.filterLogic"
                      :field-options="metricFilterFieldOptions(item)"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="false"
                      empty-text="暂无指标筛选"
                      @update:logic="item.filterLogic = $event"
                    />
                    <div class="builder-inline-actions">
                      <button type="button" class="builder-add-link" @click="item.filters.push(emptyBuilderFilter())">
                        <el-icon><Plus /></el-icon>
                        <span>筛选条件</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="sqlBuilder.calculatedMetrics.length" class="metric-list formula-metric-list">
                <div
                  v-for="(item, index) in sqlBuilder.calculatedMetrics"
                  :key="item.id"
                  class="metric-item formula-metric-item"
                  @click.stop
                >
                  <div class="metric-index formula-metric-index">
                    {{ sqlBuilder.metricItems.length + index + 1 }}
                  </div>
                  <div class="metric-body">
                    <div class="formula-metric-head">
                      <div class="formula-metric-title-wrap">
                        <el-input
                          v-model="item.alias"
                          class="formula-metric-title-input"
                          size="small"
                          clearable
                          :placeholder="calculatedMetricTitle(item, index)"
                        />
                        <span class="formula-decimal-pill">{{ formulaMetricPrecisionText(item) }}</span>
                      </div>
                      <div class="formula-metric-actions">
                        <button type="button" class="formula-icon-button" title="筛选条件">
                          <el-icon><Filter /></el-icon>
                        </button>
                        <button type="button" class="formula-icon-button" title="公式指标" @click="setFormulaCursor(item, item.tokens.length)">
                          Σ
                        </button>
                        <button type="button" class="formula-icon-button" title="复制公式指标" @click="addCalculatedMetricItem">
                          <el-icon><CopyDocument /></el-icon>
                        </button>
                        <el-dropdown trigger="click" placement="bottom-end">
                          <button type="button" class="formula-icon-button" title="更多操作">
                            <el-icon><MoreFilled /></el-icon>
                          </button>
                          <template #dropdown>
                            <el-dropdown-menu>
                              <el-dropdown-item @click="removeCalculatedMetricItem(index)">
                                删除公式指标
                              </el-dropdown-item>
                            </el-dropdown-menu>
                          </template>
                        </el-dropdown>
                      </div>
                    </div>
                    <div
                      class="formula-editor"
                      @focusin="activeFormulaMetricId = item.id"
                      @focusout="handleFormulaEditorFocusout($event, item)"
                    >
                      <div
                        class="formula-display"
                        :class="{ 'is-empty': !item.tokens.length, 'is-invalid': item.tokens.length && !calculatedMetricValidation(item).valid }"
                        contenteditable="true"
                        spellcheck="false"
                        role="textbox"
                        tabindex="0"
                        @click="handleFormulaDisplayClick($event, item)"
                        @keydown.stop="handleFormulaEditorKeydown($event, item)"
                        @beforeinput.prevent
                        @paste.prevent
                      >
                        <span
                          v-if="!item.tokens.length"
                          class="formula-placeholder"
                        >
                          {{ calculatedMetricFormulaText(item) }}
                        </span>
                        <template v-for="(token, tokenIndex) in item.tokens" :key="`${item.id}-${tokenIndex}`">
                          <span
                            v-if="tokenIndex === 0 && item.formulaCursorIndex === 0"
                            class="formula-cursor"
                          />
                          <template v-if="token.type === 'atomicMetric'">
                            <span
                              class="formula-token-stack"
                              contenteditable="false"
                              @click.stop="startEditFormulaAtomicMetric(item, tokenIndex, token.metric)"
                            >
                              <span class="formula-token-flow">
                                <span
                                  class="formula-token formula-token-atomicMetric"
                                >
                                  <span
                                    class="formula-token-editor-row"
                                    @click.stop="startEditFormulaAtomicMetric(item, tokenIndex, token.metric)"
                                  >
                                    <BuilderFieldPicker
                                      v-model="token.metric.field"
                                      :options="analysisFieldOptions"
                                      :loading="schemaLoading"
                                      :mode="analysisFieldPickerMode"
                                      :placeholder="formulaFieldPickerPlaceholder"
                                      @update:modelValue="syncFormulaAtomicMetric(token.metric, true)"
                                    />
                                    <button
                                      type="button"
                                      class="formula-token-filter"
                                      title="事件筛选"
                                      tabindex="-1"
                                      @click.stop="toggleFormulaAtomicMetricFilter(item, tokenIndex, token.metric)"
                                    >
                                      <el-icon><Filter /></el-icon>
                                    </button>
                                    <span class="formula-token-of">的</span>
                                    <el-select
                                      v-model="token.metric.aggregation"
                                      size="small"
                                      class="formula-token-aggregation"
                                      @change="syncFormulaAtomicMetric(token.metric)"
                                    >
                                      <el-option
                                        v-for="option in builderAggregationOptions"
                                        :key="option.value"
                                        :label="option.label"
                                        :value="option.value"
                                      />
                                    </el-select>
                                    <BuilderFieldPicker
                                      v-if="token.metric.aggregation !== 'count'"
                                      v-model="token.metric.metric"
                                      :options="metricMeasureFieldOptions(token.metric as any)"
                                      :loading="schemaLoading"
                                      mode="metric"
                                      placeholder="计算字段"
                                      @update:modelValue="syncFormulaAtomicMetric(token.metric)"
                                    />
                                  </span>
                                </span>
                                <span
                                  class="formula-insert-target"
                                  :class="{ 'is-active': item.formulaCursorIndex === tokenIndex + 1 }"
                                  contenteditable="false"
                                  @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                                >
                                  <span
                                    v-if="item.formulaCursorIndex === tokenIndex + 1"
                                    class="formula-cursor"
                                  />
                                </span>
                              </span>
                              <BuilderFilterTree
                                v-if="token.metric.filters.length"
                                class="formula-token-filter-tree"
                                :nodes="token.metric.filters"
                                :logic="token.metric.filterLogic"
                                :field-options="metricFilterFieldOptions(token.metric as any)"
                                :operator-options="builderFilterOperatorOptions"
                                :schema-loading="schemaLoading"
                                picker-mode="filter-property"
                                :filter-property-tabs="['all', 'event', 'user']"
                                :show-toolbar="true"
                                empty-text="暂无事件筛选"
                                @update:logic="token.metric.filterLogic = $event"
                              />
                            </span>
                          </template>
                          <template v-else>
                            <span
                              class="formula-token"
                              :class="`formula-token-${token.type}`"
                              contenteditable="false"
                              @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                            >
                              {{ formulaTokenText(token) }}
                            </span>
                          </template>
                          <span
                            v-if="token.type !== 'atomicMetric'"
                            class="formula-insert-target"
                            :class="{ 'is-active': item.formulaCursorIndex === tokenIndex + 1 }"
                            contenteditable="false"
                            @click.stop="setFormulaCursor(item, tokenIndex + 1)"
                          >
                            <span
                              v-if="item.formulaCursorIndex === tokenIndex + 1"
                              class="formula-cursor"
                            />
                          </span>
                        </template>
                      </div>
                      <div
                        v-if="item.tokens.length && !calculatedMetricValidation(item).valid"
                        class="formula-error"
                      >
                        {{ calculatedMetricValidation(item).message }}
                      </div>
                      <div v-if="activeFormulaMetricId === item.id" class="formula-toolbar">
                        <div class="formula-toolbar-panel">
                          <div class="formula-keyboard-layout">
                            <div class="formula-number-pad">
                              <button
                                v-for="numberKey in formulaNumberKeys"
                                :key="numberKey"
                                type="button"
                                class="formula-key-button formula-number-key"
                                @click="appendFormulaNumber(item, numberKey)"
                              >
                                {{ numberKey }}
                              </button>
                            </div>
                            <div class="formula-operator-pad">
                              <button
                                v-for="option in builderCalculationOperatorOptions"
                                :key="option.value"
                                type="button"
                                class="formula-key-button"
                                @click="appendFormulaOperator(item, option.value)"
                              >
                                {{ option.label }}
                              </button>
                              <button
                                v-for="paren in formulaParenKeys"
                                :key="paren"
                                type="button"
                                class="formula-key-button"
                                @click="appendFormulaParen(item, paren)"
                              >
                                {{ paren }}
                              </button>
                              <button type="button" class="formula-key-button formula-delete-key" @click="deleteFormulaToken(item)">
                                ← Del
                              </button>
                            </div>
                            <div class="formula-command-panel">
                              <button type="button" class="formula-action-button" @click="appendFormulaAtomicMetric(item)">
                                <el-icon><Plus /></el-icon>
                                <span>插入事件</span>
                              </button>
                              <span class="formula-shortcut-hint">Ctrl+E</span>
                              <button type="button" class="formula-action-button" @click="clearFormulaTokens(item)">
                                <el-icon><Delete /></el-icon>
                                <span>清空</span>
                              </button>
                              <span class="formula-shortcut-hint">Ctrl+D</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section v-else-if="isRankingAnalysis" class="builder-section ranking-builder-section">
              <div class="ranking-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>排行榜</span>
                  </div>
                </div>
                <div class="ranking-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.ranking.entityField"
                    :options="rankingEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择排行主体"
                  />
                  <span>进行排名</span>
                </div>
              </div>

              <div class="ranking-metric-block">
                <span class="ranking-config-label">按指标排名</span>
                <div class="ranking-metric-editor">
                  <div class="ranking-metric-row">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.ranking.metric.event"
                      :options="rankingEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择排名指标"
                      @update:modelValue="handleRankingMetricChange(sqlBuilder.ranking.metric, $event)"
                    />
                    <span>的</span>
                    <el-select
                      v-model="sqlBuilder.ranking.metric.aggregation"
                      class="ranking-aggregation-select"
                      @change="syncRankingMetricField(sqlBuilder.ranking.metric)"
                    >
                      <el-option
                        v-for="option in builderAggregationOptions"
                        :key="option.value"
                        :label="option.label"
                        :value="option.value"
                      />
                    </el-select>
                    <BuilderFieldPicker
                      v-if="sqlBuilder.ranking.metric.aggregation !== 'count'"
                      v-model="sqlBuilder.ranking.metric.metricField"
                      :options="rankingMetricFieldOptions(sqlBuilder.ranking.metric)"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="计算字段"
                    />
                    <el-select v-model="sqlBuilder.ranking.metric.direction" class="ranking-direction-select">
                      <el-option label="降序" value="desc" />
                      <el-option label="升序" value="asc" />
                    </el-select>
                  </div>
                </div>
              </div>

              <div class="ranking-tie-block">
                <span class="ranking-config-label">并列名次处理</span>
                <div class="ranking-tie-row">
                  <span>当出现相同值时，将</span>
                  <el-select v-model="sqlBuilder.ranking.tieHandling" class="ranking-tie-select">
                    <el-option label="按默认排序" value="default" />
                    <el-option label="并列且跳过" value="skip" />
                    <el-option label="并列不跳过" value="dense" />
                  </el-select>
                </div>
              </div>

              <div class="ranking-extra-block">
                <div class="ranking-extra-heading">
                  <span class="ranking-config-label">同时展示指标</span>
                  <button type="button" class="builder-add-link" @click="addRankingMetric">
                    <el-icon><Plus /></el-icon>
                    <span>指标</span>
                  </button>
                </div>
                <div v-for="(metric, index) in sqlBuilder.ranking.simultaneousMetrics" :key="metric.id" class="ranking-extra-row">
                  <span class="ranking-extra-index">{{ index + 1 }}</span>
                  <el-input v-model="metric.alias" class="ranking-alias-input" clearable maxlength="80" placeholder="指标名称" />
                  <BuilderFieldPicker
                    :model-value="metric.event"
                    :options="rankingEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择指标"
                    @update:modelValue="handleRankingMetricChange(metric, $event)"
                  />
                  <el-select v-model="metric.aggregation" class="ranking-aggregation-select" @change="syncRankingMetricField(metric)">
                    <el-option
                      v-for="option in builderAggregationOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                  <BuilderFieldPicker
                    v-if="metric.aggregation !== 'count'"
                    v-model="metric.metricField"
                    :options="rankingMetricFieldOptions(metric)"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                  <button type="button" class="builder-icon-button danger" :title="`删除同时展示指标${index + 1}`" @click="removeRankingMetric(index)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.ranking.simultaneousMetrics.length" class="builder-empty">暂无同时展示指标</div>
              </div>

              <div class="ranking-extra-block">
                <div class="ranking-extra-heading">
                  <span class="ranking-config-label">同时展示属性</span>
                  <button type="button" class="builder-add-link" @click="sqlBuilder.ranking.simultaneousProperties.push('')">
                    <el-icon><Plus /></el-icon>
                    <span>属性</span>
                  </button>
                </div>
                <div v-for="(_, index) in sqlBuilder.ranking.simultaneousProperties" :key="index" class="ranking-extra-row ranking-property-row">
                  <span class="ranking-extra-index">{{ index + 1 }}</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.ranking.simultaneousProperties[index]"
                    :options="rankingEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择展示属性"
                  />
                  <button type="button" class="builder-icon-button danger" :title="`删除同时展示属性${index + 1}`" @click="sqlBuilder.ranking.simultaneousProperties.splice(index, 1)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.ranking.simultaneousProperties.length" class="builder-empty">暂无同时展示属性</div>
              </div>
            </section>

            <section v-else-if="isDistributionAnalysis" class="builder-section distribution-builder-section">
              <div class="distribution-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>分布分析</span>
                  </div>
                </div>
                <div class="distribution-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.distribution.entityField"
                    :options="distributionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="distribution-event-block">
                <span class="distribution-config-label">参与事件</span>
                <div class="distribution-event-editor" :class="{ 'is-active': distributionFilterExpanded }">
                  <div class="distribution-event-row">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.distribution.event"
                      :options="distributionEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择参与事件"
                      @update:modelValue="handleDistributionEventChange"
                    />
                    <span>的</span>
                    <DistributionMetricPicker
                      :model-value="sqlBuilder.distribution.metric"
                      :event-label="distributionEventLabel"
                      :property-options="distributionEventPropertyOptions"
                      :loading="schemaLoading"
                      :disabled="!sqlBuilder.distribution.event"
                      @update:modelValue="updateDistributionMetric"
                    />
                    <DistributionIntervalSettings
                      :model-value="sqlBuilder.distribution.interval"
                      :disabled="!sqlBuilder.distribution.event || sqlBuilder.distribution.metric.kind === 'count'"
                      @update:modelValue="updateDistributionInterval"
                    />
                    <button
                      type="button"
                      class="retention-event-action"
                      :class="{ 'is-active': distributionFilterExpanded || hasEffectiveBuilderFilters(sqlBuilder.distribution.eventFilters) }"
                      title="筛选参与事件"
                      aria-label="筛选参与事件"
                      :disabled="!sqlBuilder.distribution.event"
                      @click="toggleDistributionEventFilter"
                    >
                      <el-icon><Filter /></el-icon>
                    </button>
                  </div>
                </div>
                <div v-if="distributionFilterExpanded" class="retention-event-filter-panel">
                  <BuilderFilterTree
                    :nodes="sqlBuilder.distribution.eventFilters"
                    :logic="sqlBuilder.distribution.eventFilterLogic"
                    :field-options="distributionEventPropertyOptions"
                    :operator-options="builderFilterOperatorOptions"
                    :schema-loading="schemaLoading"
                    picker-mode="filter-property"
                    :filter-property-tabs="['all', 'event', 'user']"
                    :show-toolbar="true"
                    empty-text="暂无参与事件筛选"
                    @update:logic="sqlBuilder.distribution.eventFilterLogic = $event"
                    @empty="distributionFilterExpanded = false"
                  />
                </div>
              </div>

              <div class="distribution-simultaneous-block">
                <div class="distribution-switch-row">
                  <span>使用同时展示</span>
                  <el-switch
                    v-model="sqlBuilder.distribution.simultaneous.enabled"
                    @change="handleDistributionSimultaneousToggle"
                  />
                </div>
                <div v-if="sqlBuilder.distribution.simultaneous.enabled" class="distribution-simultaneous-flow">
                  <span>同时展示区间内主体参与</span>
                  <div class="distribution-simultaneous-core-controls">
                    <BuilderFieldPicker
                      v-model="sqlBuilder.distribution.simultaneous.event"
                      :options="distributionEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择参与事件"
                      @update:modelValue="syncDistributionSimultaneousMetricField"
                    />
                    <span>的</span>
                    <el-select
                      v-model="sqlBuilder.distribution.simultaneous.aggregation"
                      size="small"
                      @change="syncDistributionSimultaneousMetricField"
                    >
                      <el-option
                        v-for="option in builderAggregationOptions"
                        :key="option.value"
                        :label="option.label"
                        :value="option.value"
                      />
                    </el-select>
                  </div>
                  <BuilderFieldPicker
                    v-if="sqlBuilder.distribution.simultaneous.aggregation !== 'count'"
                    v-model="sqlBuilder.distribution.simultaneous.metricField"
                    :options="distributionSimultaneousMetricFieldOptions()"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                </div>
              </div>
            </section>

            <section v-else-if="isIntervalAnalysis" class="builder-section interval-builder-section">
              <div class="interval-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>间隔分析</span>
                  </div>
                </div>
                <div class="interval-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.interval.entityField"
                    :options="intervalEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="interval-event-stack">
                <div class="interval-event-block">
                  <span class="interval-config-label">起点事件</span>
                  <div class="interval-event-editor" :class="{ 'is-active': intervalFilterExpanded.start }">
                    <div class="interval-event-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.interval.startEvent"
                        :options="intervalEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择起点事件"
                        @update:modelValue="handleIntervalEventChange('start', $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': intervalFilterExpanded.start || hasEffectiveBuilderFilters(sqlBuilder.interval.startEventFilters) }"
                        title="筛选起点事件"
                        aria-label="筛选起点事件"
                        :disabled="!sqlBuilder.interval.startEvent"
                        @click="toggleIntervalEventFilter('start')"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                    </div>
                  </div>
                  <div v-if="intervalFilterExpanded.start" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.interval.startEventFilters"
                      :logic="sqlBuilder.interval.startEventFilterLogic"
                      :field-options="intervalEventFilterFieldOptions('start')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无起点事件筛选"
                      @update:logic="sqlBuilder.interval.startEventFilterLogic = $event"
                      @empty="intervalFilterExpanded.start = false"
                    />
                  </div>
                </div>

                <div class="interval-event-block">
                  <span class="interval-config-label">终点事件</span>
                  <div class="interval-event-editor" :class="{ 'is-active': intervalFilterExpanded.end }">
                    <div class="interval-event-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.interval.endEvent"
                        :options="intervalEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择终点事件"
                        @update:modelValue="handleIntervalEventChange('end', $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': intervalFilterExpanded.end || hasEffectiveBuilderFilters(sqlBuilder.interval.endEventFilters) }"
                        title="筛选终点事件"
                        aria-label="筛选终点事件"
                        :disabled="!sqlBuilder.interval.endEvent"
                        @click="toggleIntervalEventFilter('end')"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                    </div>
                  </div>
                  <div v-if="intervalFilterExpanded.end" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.interval.endEventFilters"
                      :logic="sqlBuilder.interval.endEventFilterLogic"
                      :field-options="intervalEventFilterFieldOptions('end')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无终点事件筛选"
                      @update:logic="sqlBuilder.interval.endEventFilterLogic = $event"
                      @empty="intervalFilterExpanded.end = false"
                    />
                  </div>
                </div>
              </div>

              <div class="interval-option-block">
                <div class="interval-switch-row">
                  <span>使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.interval.relatedProperty.enabled"
                    @change="handleIntervalRelatedPropertyToggle"
                  />
                </div>
                <div v-if="sqlBuilder.interval.relatedProperty.enabled" class="interval-property-match">
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.interval.relatedProperty.startProperty"
                    :options="intervalStartPropertyOptions"
                    :loading="schemaLoading"
                    mode="filter-property"
                    placeholder="起点事件属性"
                    @update:modelValue="handleIntervalStartPropertyChange"
                  />
                  <span>的值与</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.interval.relatedProperty.endProperty"
                    :options="intervalEndPropertyOptions"
                    :loading="schemaLoading"
                    mode="filter-property"
                    placeholder="终点事件属性"
                  />
                  <span>相等</span>
                </div>
              </div>

              <div class="interval-limit-row">
                <span class="interval-config-label">间隔上限</span>
                <div class="interval-limit-content">
                  <p>起点事件到终点事件的间隔不超过</p>
                  <IntervalLimitPicker v-model="sqlBuilder.interval.limitSeconds" />
                </div>
              </div>
            </section>

            <section v-else-if="isPathAnalysis" class="builder-section path-builder-section">
              <div class="path-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>路径分析</span>
                  </div>
                </div>
              </div>

              <div class="path-config-block">
                <span class="path-config-label">参与分析的事件</span>
                <PathEventList
                  v-model="sqlBuilder.path.events"
                  :event-options="pathEventOptions"
                  :property-options="pathEventPropertyOptions"
                  :loading="schemaLoading"
                  :max-events="PATH_EVENT_LIMIT"
                />
              </div>

              <div class="path-config-block path-initial-event-block">
                <span class="path-config-label">分析路径仪</span>
                <div class="path-initial-event-row">
                  <span class="path-initial-event-tag">
                    <el-icon><FolderOpened /></el-icon>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.path.initialEvent"
                      :options="pathInitialEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择初始事件"
                    />
                  </span>
                  <span>作为</span>
                  <span class="path-role-tag">初始事件</span>
                </div>
              </div>

              <div class="path-session-block">
                <span class="path-config-label">会话间隔时长</span>
                  <div class="path-session-row">
                    <PathSessionGapPicker v-model="sqlBuilder.path.sessionGapSeconds" />
                  </div>
              </div>
            </section>

            <section v-else-if="isRevenueAnalysis" class="builder-section revenue-builder-section">
              <div class="revenue-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>收入分析</span>
                  </div>
                </div>
                <div class="revenue-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.revenue.entityField"
                    :options="revenueEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="revenue-config-stack">
                <div class="revenue-config-block">
                  <span class="revenue-config-label">同期群</span>
                  <div class="revenue-event-flow">
                    <span>按初始事件</span>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.revenue.initialEvent"
                      :options="revenueEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择初始事件"
                    />
                  </div>
                </div>

                <div class="revenue-config-block">
                  <span class="revenue-config-label">付费事件</span>
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.revenue.paymentEvent"
                    :options="revenueEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择付费事件"
                    @update:modelValue="handleRevenuePaymentEventChange"
                  />
                </div>

                <div class="revenue-config-block">
                  <span class="revenue-config-label">收入口径</span>
                  <div class="revenue-metric-flow">
                    <BuilderFieldPicker
                      :model-value="sqlBuilder.revenue.paymentEvent"
                      :options="revenueEventOptions"
                      :loading="schemaLoading"
                      mode="tracking-event"
                      placeholder="选择付费事件"
                      @update:modelValue="handleRevenuePaymentEventChange"
                    />
                    <span>的</span>
                    <RevenueMetricPicker
                      :model-value="sqlBuilder.revenue.metric"
                      :disabled="!sqlBuilder.revenue.paymentEvent"
                      @update:modelValue="updateRevenueMetric"
                    />
                    <BuilderFieldPicker
                      v-if="revenueMetricUsesProperty(sqlBuilder.revenue.metric.method)"
                      v-model="sqlBuilder.revenue.metric.field"
                      :options="revenueNumericPropertyOptions"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="选择数值属性"
                    />
                  </div>
                </div>

                <div class="revenue-cost-block">
                  <div class="revenue-switch-row">
                    <span>成本数据</span>
                    <el-switch
                      v-model="sqlBuilder.revenue.costEnabled"
                      @change="handleRevenueCostToggle"
                    />
                  </div>
                  <div v-if="sqlBuilder.revenue.costEnabled" class="revenue-cost-field-row">
                    <span>成本字段</span>
                    <BuilderFieldPicker
                      v-model="sqlBuilder.revenue.costField"
                      :options="revenueNumericPropertyOptions"
                      :loading="schemaLoading"
                      mode="metric"
                      placeholder="选择成本字段"
                    />
                  </div>
                </div>

                <div class="revenue-observation-row">
                  <span class="revenue-config-label">观察时长</span>
                  <div>
                    <el-input-number
                      v-model="sqlBuilder.revenue.observationDays"
                      :min="REVENUE_OBSERVATION_MIN_DAYS"
                      :max="REVENUE_OBSERVATION_MAX_DAYS"
                      :precision="0"
                      :controls="false"
                      aria-label="收入分析观察天数"
                    />
                    <span>天</span>
                  </div>
                </div>
              </div>
            </section>

            <section v-else-if="isAttributionAnalysis" class="builder-section attribution-builder-section">
              <div class="attribution-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>归因分析</span>
                  </div>
                </div>
                <div class="attribution-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.attribution.entityField"
                    :options="attributionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>

              <div class="attribution-settings">
                <div class="attribution-method-row">
                  <span>归因方式</span>
                  <el-select v-model="sqlBuilder.attribution.method" class="attribution-method-select">
                    <el-option label="线性归因" value="linear" />
                  </el-select>
                </div>
                <AttributionWindowPicker v-model="sqlBuilder.attribution.window" />
              </div>

              <div class="attribution-divider" />

              <div class="attribution-event-block">
                <span class="attribution-config-label">目标事件</span>
                <div class="attribution-target-row">
                  <BuilderFieldPicker
                    :model-value="sqlBuilder.attribution.targetEvent"
                    :options="attributionEventOptions"
                    :loading="schemaLoading"
                    mode="tracking-event"
                    placeholder="选择目标事件"
                    @update:modelValue="handleAttributionTargetEventChange"
                  />
                  <span>的</span>
                  <el-select
                    v-model="sqlBuilder.attribution.targetMetric.aggregation"
                    class="attribution-metric-select"
                    @change="syncAttributionTargetMetricField"
                  >
                    <el-option
                      v-for="option in builderAggregationOptions"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-select>
                  <BuilderFieldPicker
                    v-if="sqlBuilder.attribution.targetMetric.aggregation !== 'count'"
                    v-model="sqlBuilder.attribution.targetMetric.metricField"
                    :options="attributionTargetMetricFieldOptions"
                    :loading="schemaLoading"
                    mode="metric"
                    placeholder="计算字段"
                  />
                  <button
                    type="button"
                    class="retention-event-action"
                    :class="{ 'is-active': attributionTargetFilterExpanded || hasEffectiveBuilderFilters(sqlBuilder.attribution.targetEventFilters) }"
                    title="筛选目标事件"
                    aria-label="筛选目标事件"
                    :disabled="!sqlBuilder.attribution.targetEvent"
                    @click="toggleAttributionTargetFilter"
                  >
                    <el-icon><Filter /></el-icon>
                  </button>
                </div>
                <div v-if="attributionTargetFilterExpanded" class="retention-event-filter-panel">
                  <BuilderFilterTree
                    :nodes="sqlBuilder.attribution.targetEventFilters"
                    :logic="sqlBuilder.attribution.targetEventFilterLogic"
                    :field-options="eventFilterFieldOptions(sqlBuilder.attribution.targetEvent)"
                    :operator-options="builderFilterOperatorOptions"
                    :schema-loading="schemaLoading"
                    picker-mode="filter-property"
                    :filter-property-tabs="['all', 'event', 'user']"
                    :show-toolbar="true"
                    empty-text="暂无目标事件筛选"
                    @update:logic="sqlBuilder.attribution.targetEventFilterLogic = $event"
                    @empty="attributionTargetFilterExpanded = false"
                  />
                </div>
              </div>

              <el-checkbox v-model="sqlBuilder.attribution.includeDirect" class="attribution-direct-checkbox">
                直接转化参与归因计算
                <el-tooltip content="没有匹配归因事件的目标转化将作为直接转化计入结果。" placement="top">
                  <span class="attribution-info-icon" aria-label="直接转化说明">i</span>
                </el-tooltip>
              </el-checkbox>

              <div class="attribution-event-block attribution-source-block">
                <span class="attribution-config-label">归因事件</span>
                <div v-for="(item, index) in sqlBuilder.attribution.events" :key="item.id" class="attribution-source-item">
                  <span class="attribution-event-index">{{ index + 1 }}</span>
                  <div class="attribution-source-content">
                    <div class="attribution-source-row">
                      <BuilderFieldPicker
                        :model-value="item.event"
                        :options="attributionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择归因事件"
                        @update:modelValue="handleAttributionEventChange(item, $event)"
                      />
                      <button
                        type="button"
                        class="retention-event-action"
                        :class="{ 'is-active': attributionEventFilterExpanded[item.id] || hasEffectiveBuilderFilters(item.filters) }"
                        :title="`筛选归因事件${index + 1}`"
                        :aria-label="`筛选归因事件${index + 1}`"
                        :disabled="!item.event"
                        @click="toggleAttributionEventFilter(item)"
                      >
                        <el-icon><Filter /></el-icon>
                      </button>
                      <button
                        type="button"
                        class="retention-event-action"
                        :title="`删除归因事件${index + 1}`"
                        :aria-label="`删除归因事件${index + 1}`"
                        @click="removeAttributionEvent(index)"
                      >
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                    <div v-if="attributionEventFilterExpanded[item.id]" class="retention-event-filter-panel">
                      <BuilderFilterTree
                        :nodes="item.filters"
                        :logic="item.filterLogic"
                        :field-options="eventFilterFieldOptions(item.event)"
                        :operator-options="builderFilterOperatorOptions"
                        :schema-loading="schemaLoading"
                        picker-mode="filter-property"
                        :filter-property-tabs="['all', 'event', 'user']"
                        :show-toolbar="true"
                        :empty-text="`暂无归因事件${index + 1}筛选`"
                        @update:logic="item.filterLogic = $event"
                        @empty="attributionEventFilterExpanded[item.id] = false"
                      />
                    </div>
                  </div>
                </div>
                <button type="button" class="builder-add-link attribution-add-event" @click="addAttributionEvent">
                  <el-icon><Plus /></el-icon>
                  <span>归因事件</span>
                </button>
              </div>
            </section>

            <section v-else-if="isFunnelAnalysis" class="builder-section funnel-builder-section">
              <div class="funnel-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>漏斗分析</span>
                  </div>
                </div>
                <div class="funnel-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.funnel.entityField"
                    :options="funnelEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>
              <div class="funnel-step-list">
                <div v-for="(step, index) in sqlBuilder.funnel.steps" :key="step.id" class="funnel-step-block">
                  <span class="funnel-step-index">{{ index + 1 }}</span>
                  <div class="funnel-step-content">
                    <div
                      class="funnel-step-editor"
                      :class="{
                        'is-active': funnelAliasEditing[step.id] || funnelFilterExpanded[step.id],
                        'has-alias': Boolean(step.alias.trim()),
                      }"
                    >
                      <div v-if="funnelAliasEditing[step.id] || step.alias.trim()" class="funnel-step-alias-row">
                        <el-input
                          v-if="funnelAliasEditing[step.id]"
                          v-model="funnelAliasDraft[step.id]"
                          class="funnel-step-alias-input"
                          clearable
                          maxlength="80"
                          :placeholder="retentionEventDefaultDisplayName(step.event)"
                          :aria-label="`重命名步骤${index + 1}`"
                          autofocus
                          @keydown.stop
                          @keyup.stop
                          @keydown.enter.prevent="finishFunnelStepRename(step)"
                          @keydown.esc.prevent="cancelFunnelStepRename(step)"
                          @blur="finishFunnelStepRename(step)"
                        />
                        <span v-else class="funnel-step-alias-text">{{ step.alias.trim() }}</span>
                      </div>
                      <div class="funnel-step-main-row">
                        <BuilderFieldPicker
                          :model-value="step.event"
                          :options="funnelEventOptions"
                          :loading="schemaLoading"
                          mode="tracking-event"
                          :placeholder="`选择步骤${index + 1}事件`"
                          @update:modelValue="handleFunnelStepEventChange(step, $event)"
                        />
                        <div class="funnel-step-actions">
                          <button
                            type="button"
                            class="retention-event-action"
                            :title="`重命名步骤${index + 1}`"
                            :aria-label="`重命名步骤${index + 1}`"
                            :disabled="!step.event"
                            @click="beginFunnelStepRename(step)"
                          >
                            <el-icon><EditPen /></el-icon>
                          </button>
                          <button
                            type="button"
                            class="retention-event-action"
                            :class="{ 'is-active': funnelFilterExpanded[step.id] || hasEffectiveBuilderFilters(step.filters) }"
                            :title="`筛选步骤${index + 1}`"
                            :aria-label="`筛选步骤${index + 1}`"
                            :disabled="!step.event"
                            @click="toggleFunnelStepFilter(step)"
                          >
                            <el-icon><Filter /></el-icon>
                          </button>
                          <button
                            type="button"
                            class="retention-event-action"
                            :title="`删除步骤${index + 1}`"
                            :aria-label="`删除步骤${index + 1}`"
                            @click="removeFunnelStep(index)"
                          >
                            <el-icon><Delete /></el-icon>
                          </button>
                        </div>
                      </div>
                    </div>
                    <div v-if="funnelFilterExpanded[step.id]" class="retention-event-filter-panel">
                      <BuilderFilterTree
                        :nodes="step.filters"
                        :logic="step.filterLogic"
                        :field-options="eventFilterFieldOptions(step.event)"
                        :operator-options="builderFilterOperatorOptions"
                        :schema-loading="schemaLoading"
                        picker-mode="filter-property"
                        :filter-property-tabs="['all', 'event', 'user']"
                        :show-toolbar="true"
                        :empty-text="`暂无步骤${index + 1}筛选`"
                        @update:logic="step.filterLogic = $event"
                        @empty="funnelFilterExpanded[step.id] = false"
                      />
                    </div>
                    <div v-if="sqlBuilder.funnel.relatedPropertyEnabled" class="funnel-step-property-row">
                      <span>关联属性</span>
                      <BuilderFieldPicker
                        v-model="step.relatedProperty"
                        :options="funnelPropertyOptions(step.event)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择步骤属性"
                      />
                    </div>
                  </div>
                </div>
              </div>
              <button type="button" class="builder-add-link funnel-add-step" @click="addFunnelStep">
                <el-icon><Plus /></el-icon>
                <span>添加步骤</span>
              </button>
              <div class="funnel-advanced-options">
                <div class="funnel-option-row">
                  <span>使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.funnel.relatedPropertyEnabled"
                    @change="handleFunnelRelatedPropertyToggle"
                  />
                </div>
                <div class="funnel-option-row">
                  <span>分析窗口期</span>
                  <FunnelWindowPicker v-model="sqlBuilder.funnel.window" />
                </div>
              </div>
            </section>

            <section v-else class="builder-section retention-builder-section">
              <div class="retention-heading-row">
                <div class="builder-section-head">
                  <div class="builder-section-title">
                    <BuilderSectionIcon class="builder-section-icon" />
                    <span>留存分析</span>
                  </div>
                </div>
                <div class="retention-subject-line">
                  <span>对</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.retention.entityField"
                    :options="retentionEntityFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="选择分析主体"
                  />
                  <span>进行分析</span>
                </div>
              </div>
              <div class="retention-event-stack">
                <div class="retention-field-block">
                  <span class="retention-config-label">初始事件</span>
                  <div
                    class="retention-event-editor"
                    :class="{
                      'is-active': retentionAliasEditing.initial || retentionFilterExpanded.initial,
                      'has-alias': Boolean(sqlBuilder.retention.initialEventAlias.trim()),
                    }"
                  >
                    <div
                      v-if="retentionAliasEditing.initial || sqlBuilder.retention.initialEventAlias.trim()"
                      class="retention-event-alias-row"
                    >
                      <el-input
                        v-if="retentionAliasEditing.initial"
                        v-model="retentionAliasDraft.initial"
                        class="retention-event-alias-input"
                        clearable
                        maxlength="80"
                        :placeholder="retentionEventDefaultDisplayName(sqlBuilder.retention.initialEvent)"
                        aria-label="重命名初始事件"
                        autofocus
                        @keydown.stop
                        @keyup.stop
                        @keydown.enter.prevent="finishRetentionEventRename('initial')"
                        @keydown.esc.prevent="cancelRetentionEventRename('initial')"
                        @blur="finishRetentionEventRename('initial')"
                      />
                      <span v-else class="retention-event-alias-text">
                        {{ sqlBuilder.retention.initialEventAlias.trim() }}
                      </span>
                    </div>
                    <div class="retention-event-main-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.retention.initialEvent"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择初始事件"
                        @update:modelValue="handleRetentionEventPropertyChange('initial', $event)"
                      />
                      <div class="retention-event-actions">
                        <button
                          type="button"
                          class="retention-event-action"
                          title="重命名初始事件"
                          aria-label="重命名初始事件"
                          :disabled="!sqlBuilder.retention.initialEvent"
                          @click="beginRetentionEventRename('initial')"
                        >
                          <el-icon><EditPen /></el-icon>
                        </button>
                        <button
                          type="button"
                          class="retention-event-action"
                          :class="{ 'is-active': retentionFilterExpanded.initial || hasEffectiveBuilderFilters(sqlBuilder.retention.initialEventFilters) }"
                          title="筛选初始事件"
                          aria-label="筛选初始事件"
                          :disabled="!sqlBuilder.retention.initialEvent"
                          @click="toggleRetentionEventFilter('initial')"
                        >
                          <el-icon><Filter /></el-icon>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div v-if="retentionFilterExpanded.initial" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.retention.initialEventFilters"
                      :logic="sqlBuilder.retention.initialEventFilterLogic"
                      :field-options="retentionEventFilterFieldOptions('initial')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无初始事件筛选"
                      @update:logic="sqlBuilder.retention.initialEventFilterLogic = $event"
                      @empty="retentionFilterExpanded.initial = false"
                    />
                  </div>
                </div>
                <div class="retention-field-block">
                  <span class="retention-config-label">回访事件</span>
                  <div
                    class="retention-event-editor"
                    :class="{
                      'is-active': retentionAliasEditing.return || retentionFilterExpanded.return,
                      'has-alias': Boolean(sqlBuilder.retention.returnEventAlias.trim()),
                    }"
                  >
                    <div
                      v-if="retentionAliasEditing.return || sqlBuilder.retention.returnEventAlias.trim()"
                      class="retention-event-alias-row"
                    >
                      <el-input
                        v-if="retentionAliasEditing.return"
                        v-model="retentionAliasDraft.return"
                        class="retention-event-alias-input"
                        clearable
                        maxlength="80"
                        :placeholder="retentionEventDefaultDisplayName(sqlBuilder.retention.returnEvent)"
                        aria-label="重命名回访事件"
                        autofocus
                        @keydown.stop
                        @keyup.stop
                        @keydown.enter.prevent="finishRetentionEventRename('return')"
                        @keydown.esc.prevent="cancelRetentionEventRename('return')"
                        @blur="finishRetentionEventRename('return')"
                      />
                      <span v-else class="retention-event-alias-text">
                        {{ sqlBuilder.retention.returnEventAlias.trim() }}
                      </span>
                    </div>
                    <div class="retention-event-main-row">
                      <BuilderFieldPicker
                        :model-value="sqlBuilder.retention.returnEvent"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择回访事件"
                        @update:modelValue="handleRetentionEventPropertyChange('return', $event)"
                      />
                      <div class="retention-event-actions">
                        <button
                          type="button"
                          class="retention-event-action"
                          title="重命名回访事件"
                          aria-label="重命名回访事件"
                          :disabled="!sqlBuilder.retention.returnEvent"
                          @click="beginRetentionEventRename('return')"
                        >
                          <el-icon><EditPen /></el-icon>
                        </button>
                        <button
                          type="button"
                          class="retention-event-action"
                          :class="{ 'is-active': retentionFilterExpanded.return || hasEffectiveBuilderFilters(sqlBuilder.retention.returnEventFilters) }"
                          title="筛选回访事件"
                          aria-label="筛选回访事件"
                          :disabled="!sqlBuilder.retention.returnEvent"
                          @click="toggleRetentionEventFilter('return')"
                        >
                          <el-icon><Filter /></el-icon>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div v-if="retentionFilterExpanded.return" class="retention-event-filter-panel">
                    <BuilderFilterTree
                      :nodes="sqlBuilder.retention.returnEventFilters"
                      :logic="sqlBuilder.retention.returnEventFilterLogic"
                      :field-options="retentionEventFilterFieldOptions('return')"
                      :operator-options="builderFilterOperatorOptions"
                      :schema-loading="schemaLoading"
                      picker-mode="filter-property"
                      :filter-property-tabs="['all', 'event', 'user']"
                      :show-toolbar="true"
                      empty-text="暂无回访事件筛选"
                      @update:logic="sqlBuilder.retention.returnEventFilterLogic = $event"
                      @empty="retentionFilterExpanded.return = false"
                    />
                  </div>
                </div>
              </div>
              <div class="retention-advanced-options">
                <div class="retention-option-block">
                  <span class="retention-option-title">使用同时展示</span>
                  <el-switch
                    v-model="sqlBuilder.retention.simultaneous.enabled"
                    @change="handleRetentionSimultaneousToggle"
                  />
                  <template v-if="sqlBuilder.retention.simultaneous.enabled">
                    <span class="retention-option-description">同时展示回访的用户参与</span>
                    <div
                      class="retention-option-flow"
                      :class="{ 'has-metric-field': sqlBuilder.retention.simultaneous.aggregation !== 'count' }"
                    >
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.simultaneous.event"
                        :options="retentionEventOptions"
                        :loading="schemaLoading"
                        mode="tracking-event"
                        placeholder="选择参与事件"
                        @update:modelValue="handleRetentionEventPropertyChange('simultaneous', $event)"
                      />
                      <span>的</span>
                      <el-select
                        v-model="sqlBuilder.retention.simultaneous.aggregation"
                        size="small"
                        @change="syncRetentionSimultaneousMetricField"
                      >
                        <el-option
                          v-for="option in builderAggregationOptions"
                          :key="option.value"
                          :label="option.label"
                          :value="option.value"
                        />
                      </el-select>
                      <BuilderFieldPicker
                        v-if="sqlBuilder.retention.simultaneous.aggregation !== 'count'"
                        v-model="sqlBuilder.retention.simultaneous.metricField"
                        :options="retentionSimultaneousMetricFieldOptions()"
                        :loading="schemaLoading"
                        mode="metric"
                        placeholder="计算字段"
                      />
                    </div>
                  </template>
                </div>

                <div class="retention-option-block">
                  <span class="retention-option-title">使用关联属性</span>
                  <el-switch
                    v-model="sqlBuilder.retention.relatedProperty.enabled"
                    @change="handleRetentionRelatedPropertyToggle"
                  />
                  <template v-if="sqlBuilder.retention.relatedProperty.enabled">
                    <div class="retention-property-flow">
                      <span>初始事件的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.initialProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.initialEvent)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>与</span>
                    </div>
                    <div class="retention-property-flow">
                      <span>回访事件的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.returnProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.returnEvent)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>{{ sqlBuilder.retention.simultaneous.enabled ? '与' : '的值相等' }}</span>
                    </div>
                    <div v-if="sqlBuilder.retention.simultaneous.enabled" class="retention-property-flow">
                      <span>同时展示的</span>
                      <BuilderFieldPicker
                        v-model="sqlBuilder.retention.relatedProperty.simultaneousProperty"
                        :options="retentionPropertyOptions(sqlBuilder.retention.simultaneous.event)"
                        :loading="schemaLoading"
                        mode="property"
                        placeholder="选择属性"
                      />
                      <span>的值相等</span>
                    </div>
                    <span class="retention-option-title">关联属性作为分组展示</span>
                    <el-switch v-model="sqlBuilder.retention.relatedProperty.asGroup" />
                  </template>
                </div>
              </div>
            </section>

            <section class="builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>全局筛选</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加筛选条件" @click="sqlBuilder.globalFilters.push(emptyBuilderFilter())">
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
              </div>
              <BuilderFilterTree
                :nodes="sqlBuilder.globalFilters"
                :logic="sqlBuilder.globalFilterLogic"
                :field-options="eventUserPropertyOptions"
                :operator-options="builderFilterOperatorOptions"
                :schema-loading="schemaLoading"
                picker-mode="filter-property"
                :filter-property-tabs="['user']"
                :show-toolbar="false"
                empty-text="暂无全局筛选"
                @update:logic="sqlBuilder.globalFilterLogic = $event"
              />
            </section>

            <section class="builder-section">
              <div class="builder-section-head">
                <div class="builder-section-title">
                  <BuilderSectionIcon class="builder-section-icon" />
                  <span>分组项</span>
                </div>
                <div class="builder-section-actions">
                  <button type="button" class="builder-icon-button" title="添加分组项" @click="sqlBuilder.groups.push('')">
                    <el-icon><Plus /></el-icon>
                  </button>
                </div>
              </div>
              <div class="group-list">
                <div v-for="(_, index) in sqlBuilder.groups" :key="index" class="group-row">
                  <span class="group-index">{{ index + 1 }}</span>
                  <BuilderFieldPicker
                    v-model="sqlBuilder.groups[index]"
                    :options="builderFieldOptions"
                    :loading="schemaLoading"
                    mode="property"
                    placeholder="分组字段"
                  />
                  <button type="button" class="builder-icon-button danger" @click="sqlBuilder.groups.splice(index, 1)">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
                <div v-if="!sqlBuilder.groups.length" class="builder-empty">暂无分组项</div>
              </div>
            </section>

            </div>

          </div>

          <div v-if="sqlBuilder.activeTab === 'sql'" class="sql-detail-pane">
            <el-input
              v-model="form.sql"
              type="textarea"
              :autosize="{ minRows: 18, maxRows: 18 }"
              spellcheck="false"
              @keydown.stop
              @keyup.stop
            />
          </div>
          <div class="builder-bottom-bar">
            <div class="builder-bottom-options">
              <el-checkbox v-if="sqlBuilder.activeTab === 'builder' && !isRetentionAnalysis && !isFunnelAnalysis && !isDistributionAnalysis && !isIntervalAnalysis && !isPathAnalysis && !isAttributionAnalysis && !isRankingAnalysis" v-model="sqlBuilder.approximate">
                近似计算
              </el-checkbox>
            </div>
            <el-button
              type="primary"
              :disabled="!canRunEditorPreview"
              :loading="builderLoading"
              @click="calculateBuilderSql"
            >
              {{ sqlBuilder.activeTab === 'sql' ? '执行SQL' : '计算/生成' }}
            </el-button>
          </div>
        </div>
        <el-alert
          v-else-if="hasSqlSource"
          class="editor-alert"
          type="warning"
          :title="sqlEditorPermissionMessage"
          :closable="false"
        />
        <div class="source-section-toggle">
          <div class="source-section-title">MCP 数据源</div>
          <el-checkbox v-model="mcpSourceEnabled" class="source-inline-checkbox">MCP</el-checkbox>
        </div>
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
        <div v-if="!hasSqlSource && hasMcpSource" class="action-row">
          <el-button type="primary" :disabled="!canRunEditorPreview" @click="runPreview">{{ t('dashboard.sql_editor_run_preview') }}</el-button>
          <span v-if="hasSqlSource && !isExternalSnapshot && sqlChangedAfterPreview" class="muted">{{ t('dashboard.sql_editor_changed') }}</span>
          <span v-if="mcpChangedAfterPreview" class="muted">{{ mt('mcp_editor_changed') }}</span>
        </div>
        <el-form-item v-if="hasSqlSource" label="时间范围">
          <DashboardDateExpressionPicker
            class="sql-editor-time-range-picker"
            :model-value="sqlBuilder.timeExpression"
            variant="roi"
            timezone="Asia/Shanghai"
            :disabled="loading || builderLoading || !dateExpressionEnabled"
            @apply="applyDateExpression"
          />
        </el-form-item>
        <el-form-item v-if="hasSqlSource" label="执行数据源">
          <el-select
            v-model="selectedExecutionDatasourceId"
            :disabled="executionDatasourceOptions.length <= 1 && !executionDatasourceError"
            @change="handleExecutionDatasourceChange"
          >
            <el-option
              v-for="item in executionDatasourceOptions"
              :key="item.id"
              :label="`${item.role === 'roi' ? 'ROI 数据源' : '绑定数据源'}：${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-alert
          v-if="executionDatasourceError"
          class="editor-alert"
          type="warning"
          :title="executionDatasourceError"
          :closable="false"
        />
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
            <el-select v-if="!isRetentionAnalysis && !isFunnelAnalysis && !isDistributionAnalysis && !isIntervalAnalysis && !isPathAnalysis && !isRevenueAnalysis && !isAttributionAnalysis && !isRankingAnalysis" v-model="form.chartType" @change="handleChartTypeChange">
              <el-option
                v-for="item in chartTypes"
                :key="item.value"
                :label="t(`chat.chart_type.${item.label}`)"
                :value="item.value"
              />
            </el-select>
            <el-input v-else :model-value="isFunnelAnalysis ? '漏斗图' : isDistributionAnalysis ? '分布表' : isIntervalAnalysis ? '间隔表' : isPathAnalysis ? '桑基图' : isRevenueAnalysis ? '收入表' : isAttributionAnalysis ? '归因表' : isRankingAnalysis ? '排行榜' : '留存表'" disabled />
          </el-form-item>
        </div>
        <el-form-item v-if="form.chartType === 'table' && !isRetentionAnalysis && !isDistributionAnalysis && !isIntervalAnalysis && !isPathAnalysis && !isRevenueAnalysis && !isAttributionAnalysis && !isRankingAnalysis" :label="t('dashboard.sql_editor_columns')">
          <el-select v-model="form.columns" multiple filterable>
            <el-option
              v-for="field in fieldOptions"
              :key="field.value"
              :label="field.label"
              :value="field.value"
            />
          </el-select>
        </el-form-item>
        <div v-else-if="form.chartType !== 'table'" class="config-grid">
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
            <el-select v-model="form.series" filterable clearable @change="handleSeriesFieldChange">
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
            v-if="form.y.length > 1 && !effectiveSeriesField && ['column', 'grouped_column', 'bar', 'line', 'area'].includes(form.chartType)"
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
            <el-form-item :label="t('dashboard.pivot_group_field')">
              <el-select v-model="form.pivotGroupField" filterable clearable>
                <el-option
                  v-for="field in pivotGroupFieldOptions"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value"
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
          :x="form.chartType !== 'table' && form.chartType !== 'metric' && !isRadialPartitionChartType(form.chartType) ? toAxes([form.x]) : []"
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
  <el-dialog
    v-model="builderAgentAdvice.visible"
    title="配置 Agent 建议"
    width="560px"
    append-to-body
  >
    <div class="builder-advice-dialog">
      <div v-if="builderAgentAdvice.intent" class="builder-advice-block">
        <div class="builder-advice-title">用户意图</div>
        <div class="builder-advice-text">{{ builderAgentAdvice.intent }}</div>
      </div>
      <div v-if="builderAgentAdvice.issues.length" class="builder-advice-block">
        <div class="builder-advice-title">出了什么错误</div>
        <div v-if="builderAgentAdvice.message" class="builder-advice-text">{{ builderAgentAdvice.message }}</div>
        <ul class="builder-advice-list">
          <li v-for="item in builderAgentAdvice.issues" :key="item">{{ item }}</li>
        </ul>
      </div>
      <div v-else-if="builderAgentAdvice.message" class="builder-advice-block">
        <div class="builder-advice-title">配置检查</div>
        <div class="builder-advice-text">{{ builderAgentAdvice.message }}</div>
      </div>
      <div v-if="builderAgentAdvice.advice || builderAgentAdvice.suggestions.length" class="builder-advice-block">
        <div class="builder-advice-title">怎么改</div>
        <div v-if="builderAgentAdvice.advice" class="builder-advice-text">{{ builderAgentAdvice.advice }}</div>
        <ul class="builder-advice-list">
          <li v-for="item in builderAgentAdvice.suggestions" :key="item">{{ item }}</li>
        </ul>
      </div>
      <div v-if="!builderAgentAdvice.intent && !builderAgentAdvice.message && !builderAgentAdvice.advice && !builderAgentAdvice.issues.length && !builderAgentAdvice.suggestions.length" class="builder-empty">
        暂无建议
      </div>
    </div>
  </el-dialog>
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

.source-section-toggle {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 12px;
  margin: 0 0 12px;
  border: 1px solid rgba(31, 35, 41, 0.1);
  border-radius: 6px;
  background: #fff;
}

.source-section-title {
  flex: 0 0 auto;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.source-inline-checkbox {
  height: 24px;
  margin-right: 0;
}

.source-inline-checkbox :deep(.el-checkbox__label) {
  font-size: 13px;
}

.sql-builder-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.builder-advice-button {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #eef3ff;
  color: #1f54d8;
  cursor: pointer;
}

.builder-advice-button.warning {
  background: #fff1f0;
  color: #f04438;
}

.builder-advice-button :deep(.el-icon) {
  font-size: 16px;
}

.sql-builder-panel {
  min-height: 580px;
  max-height: 620px;
  margin-bottom: 10px;
  border: 1px solid rgba(31, 35, 41, 0.1);
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sql-builder-header {
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  border-bottom: 1px solid rgba(31, 35, 41, 0.08);
  background: #fff;
}

.sql-builder-tabs {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px;
  border-radius: 6px;
  background: #f4f6fb;
}

.sql-builder-tabs button {
  height: 24px;
  padding: 0 9px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #646a73;
  cursor: pointer;
  font-size: 12px;
}

.sql-builder-tabs button.active {
  background: #fff;
  color: #1f54d8;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(31, 35, 41, 0.08);
}

.builder-advice-dialog {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.builder-advice-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.builder-advice-title {
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.builder-advice-text {
  color: #4e5969;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.builder-advice-list {
  margin: 0;
  padding-left: 18px;
  color: #4e5969;
  font-size: 13px;
  line-height: 1.7;
}

.sql-builder-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 16px 22px 0;
}

.sql-builder-builder-pane {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.builder-section {
  padding: 0 0 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f2f6;
}

.builder-section:last-of-type {
  margin-bottom: 0;
  border-bottom: 0;
}

.builder-section-head {
  min-height: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
}

.builder-section-title {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.builder-section-icon {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  color: #1f2329;
}

.builder-section-actions {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.analysis-model-select {
  width: 220px;
}

.analysis-model-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.analysis-model-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.retention-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.funnel-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.distribution-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.ranking-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.ranking-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.ranking-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.ranking-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.ranking-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.ranking-metric-block,
.ranking-extra-block {
  margin-top: 20px;
}

.ranking-metric-editor {
  display: grid;
  gap: 10px;
  max-width: 980px;
}

.ranking-metric-row,
.ranking-extra-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.ranking-metric-row :deep(.builder-field-picker),
.ranking-extra-row :deep(.builder-field-picker) {
  min-width: 150px;
  flex: 1 1 190px;
}

.ranking-aggregation-select {
  width: 120px;
  flex: 0 0 120px;
}

.ranking-direction-select {
  width: 92px;
  flex: 0 0 92px;
}

.ranking-tie-block {
  margin-top: 22px;
}

.ranking-tie-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #505968;
  font-size: 13px;
}

.ranking-tie-select {
  width: 128px;
}

.ranking-extra-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ranking-extra-heading .ranking-config-label {
  margin: 0;
}

.ranking-extra-row {
  margin-top: 10px;
}

.ranking-extra-index {
  flex: 0 0 20px;
  color: #8a93a3;
  text-align: center;
}

.ranking-alias-input {
  width: 150px;
  flex: 0 1 150px;
}

.ranking-property-row :deep(.builder-field-picker) {
  max-width: 360px;
}

.interval-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.interval-heading-row .builder-section-head {
  width: auto;
  flex: 0 0 auto;
}

.interval-subject-line {
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  width: auto;
  min-width: 0;
  gap: 8px;
  color: #303643;
  font-size: 13px;
}

.interval-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.interval-event-stack {
  display: grid;
  gap: 18px;
  margin-top: 20px;
}

.interval-event-block {
  min-width: 0;
}

.interval-config-label {
  display: block;
  margin-bottom: 7px;
  color: #8a93a3;
  font-size: 12px;
}

.interval-event-editor {
  min-width: 0;
  padding: 5px 24px 7px 0;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.interval-event-editor:hover,
.interval-event-editor:focus-within,
.interval-event-editor.is-active {
  background: #f7f8fa;
}

.interval-event-row {
  display: grid;
  grid-template-columns: minmax(190px, 360px) 30px;
  align-items: center;
  gap: 8px;
}

.interval-event-row :deep(.builder-field-picker),
.interval-property-match :deep(.builder-field-picker) {
  min-width: 0;
}

.interval-option-block {
  display: grid;
  gap: 12px;
  margin-top: 24px;
}

.interval-switch-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: min(100%, 360px);
  color: #4b5563;
  font-size: 13px;
}

.interval-property-match {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) auto minmax(150px, 1fr) auto;
  align-items: center;
  gap: 8px;
  max-width: 760px;
  color: #6b7280;
  font-size: 13px;
}

.interval-limit-row {
  margin-top: 24px;
}

.interval-limit-row .interval-config-label {
  margin-bottom: 7px;
}

.interval-limit-row p {
  margin: 0;
  color: #4b5563;
  font-size: 13px;
}

.interval-limit-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.path-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.path-config-block,
.path-session-block {
  margin-top: 20px;
}

.path-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.path-role-tag {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 6px;
  color: #374151;
  background: #f0f2f6;
  white-space: nowrap;
}

.path-initial-event-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #707988;
  font-size: 13px;
}

.path-initial-event-tag {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  border-radius: 6px;
  color: #374151;
  background: #f0f2f6;
  line-height: 26px;
}

.path-initial-event-tag :deep(.builder-field-picker-trigger) {
  min-height: 24px;
  max-width: 180px;
  padding: 0;
  color: #374151;
  background: transparent;
  line-height: 24px;
}

.path-initial-event-tag :deep(.builder-field-picker-trigger:hover) {
  background: transparent;
}

.path-initial-event-tag :deep(.builder-field-picker-arrow) {
  display: none;
}

.path-session-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #505968;
  font-size: 13px;
}

.path-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid #aab2bf;
  border-radius: 50%;
  color: #8b94a2;
  font-size: 11px;
  font-style: normal;
}

.path-session-exact {
  color: #9aa2af;
  font-size: 12px;
}

.revenue-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
}

.revenue-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.attribution-heading-row {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
}

.attribution-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.revenue-subject-line,
.attribution-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.revenue-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.revenue-config-stack {
  display: grid;
  gap: 20px;
}

.revenue-config-block {
  display: grid;
  justify-items: start;
  gap: 7px;
  min-width: 0;
}

.revenue-config-label,
.attribution-config-label {
  display: block;
  margin-bottom: 8px;
  color: #8a93a3;
  font-size: 12px;
}

.attribution-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.attribution-settings {
  display: grid;
  gap: 14px;
  color: #505968;
  font-size: 13px;
}

.attribution-method-row {
  display: grid;
  grid-template-columns: 64px minmax(100px, 160px);
  align-items: center;
  gap: 8px;
}

.attribution-method-select {
  width: 100%;
}

.attribution-divider {
  height: 1px;
  margin: 18px -22px;
  background: #eef0f4;
}

.attribution-event-block {
  min-width: 0;
}

.revenue-event-flow,
.revenue-metric-flow,
.revenue-cost-field-row,
.revenue-observation-row > div {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.attribution-target-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: #505968;
  font-size: 13px;
}

.revenue-config-block > :deep(.builder-field-picker),
.revenue-event-flow :deep(.builder-field-picker),
.revenue-metric-flow :deep(.builder-field-picker),
.revenue-cost-field-row :deep(.builder-field-picker) {
  min-width: 170px;
  max-width: 300px;
}

.revenue-cost-block {
  display: grid;
  gap: 10px;
  justify-items: start;
}

.revenue-switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #505968;
  font-size: 13px;
}

.revenue-cost-field-row {
  padding-left: 18px;
}

.revenue-observation-row {
  display: grid;
  justify-items: start;
  gap: 7px;
}

.revenue-observation-row :deep(.el-input-number) {
  width: 80px;
  color: #6b7280;
  font-size: 13px;
}

.attribution-target-row :deep(.builder-field-picker) {
  min-width: 150px;
}

.attribution-metric-select {
  width: 104px;
}

.attribution-direct-checkbox {
  margin-top: 14px;
}

.attribution-info-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 4px;
  border: 1px solid #aab2bf;
  border-radius: 50%;
  color: #8b94a2;
  font-size: 10px;
  font-style: normal;
}

.attribution-source-block {
  margin-top: 22px;
}

.attribution-source-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  margin-bottom: 8px;
}

.attribution-event-index {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-top: 3px;
  border-radius: 7px;
  color: #fff;
  background: #252b56;
  font-size: 12px;
}

.attribution-source-content {
  flex: 1 1 auto;
  min-width: 0;
}

.attribution-source-row {
  display: grid;
  grid-template-columns: minmax(190px, 360px) 30px 30px;
  align-items: center;
  gap: 4px;
  min-height: 30px;
}

.attribution-add-event {
  margin: 4px 0 0 34px;
}

.distribution-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.distribution-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

.distribution-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.distribution-event-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}

.distribution-config-label {
  color: #8a93a3;
  font-size: 12px;
}

.distribution-event-editor {
  width: 100%;
  min-width: 0;
  padding: 6px 8px 8px 0;
  transition: background-color 0.16s ease;
}

.distribution-event-editor:hover,
.distribution-event-editor:focus-within,
.distribution-event-editor.is-active {
  background: #f7f8fa;
}

.distribution-event-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 13px;
}

.distribution-event-row :deep(.builder-field-picker) {
  min-width: 0;
}

.distribution-simultaneous-block {
  margin-top: 22px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  color: #505968;
  font-size: 12px;
}

.distribution-switch-row,
.distribution-simultaneous-flow {
  display: flex;
  align-items: center;
  gap: 10px;
}

.distribution-simultaneous-flow {
  flex-wrap: wrap;
}

.distribution-simultaneous-core-controls {
  min-width: 353px;
  display: grid;
  grid-template-columns: minmax(160px, 280px) auto 160px;
  align-items: center;
  gap: 10px;
}

.distribution-simultaneous-core-controls :deep(.builder-field-picker-trigger) {
  width: 100%;
  min-width: 0;
}

.distribution-simultaneous-core-controls :deep(.el-select) {
  width: 160px;
}

.funnel-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.funnel-subject-line {
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

.funnel-subject-line :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.funnel-step-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.funnel-step-block {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
}

.funnel-step-index {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin-top: 5px;
  border-radius: 7px;
  color: #fff;
  background: #252b56;
  font-size: 12px;
}

.funnel-step-content {
  flex: 1 1 auto;
  min-width: 0;
}

.funnel-step-editor {
  width: 100%;
  min-width: 0;
  padding: 5px 0 7px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: background-color 0.16s ease;
}

.funnel-step-editor:hover,
.funnel-step-editor:focus-within,
.funnel-step-editor.is-active {
  background: #f7f8fa;
}

.funnel-step-alias-row,
.funnel-step-main-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
}

.funnel-step-main-row {
  min-height: 28px;
  justify-content: space-between;
  gap: 12px;
}

.funnel-step-main-row :deep(.builder-field-picker) {
  min-width: 0;
}

.funnel-step-alias-input {
  width: min(260px, 100%);
}

.funnel-step-alias-input :deep(.ed-input__wrapper),
.funnel-step-alias-input :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.funnel-step-alias-input :deep(.ed-input__wrapper:hover),
.funnel-step-alias-input :deep(.ed-input__wrapper.is-focus),
.funnel-step-alias-input :deep(.el-input__wrapper:hover),
.funnel-step-alias-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 -1px 0 #2f6bff;
}

.funnel-step-alias-text {
  min-width: 0;
  color: #303643;
  font-size: 14px;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.funnel-step-actions {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.16s ease;
}

.funnel-step-editor:hover .funnel-step-actions,
.funnel-step-editor:focus-within .funnel-step-actions,
.funnel-step-editor.is-active .funnel-step-actions {
  opacity: 1;
  visibility: visible;
}

.funnel-step-property-row {
  display: grid;
  grid-template-columns: auto minmax(140px, 280px);
  align-items: center;
  gap: 10px;
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}

.funnel-step-property-row :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.funnel-add-step {
  margin: 12px 0 0 34px;
}

.funnel-advanced-options {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  margin-top: 24px;
  color: #505968;
  font-size: 12px;
}

.funnel-option-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.funnel-option-row .el-input-number {
  width: 104px;
}

.retention-heading-row .builder-section-head {
  flex: 0 0 96px;
  margin-bottom: 0;
}

.retention-subject-line {
  width: auto;
  flex: 1 1 auto;
  box-sizing: border-box;
  padding: 0;
  display: grid;
  grid-template-columns: auto minmax(160px, 280px) auto;
  align-items: center;
  justify-content: start;
  gap: 10px;
  color: #505968;
  font-size: 13px;
}

@media (max-width: 720px) {
  .analysis-model-row,
  .retention-heading-row,
  .funnel-heading-row,
  .distribution-heading-row,
  .interval-heading-row,
  .revenue-heading-row,
  .ranking-heading-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .attribution-heading-row {
    flex-wrap: wrap;
    gap: 10px;
  }

  .attribution-heading-row .attribution-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .attribution-target-row {
    flex-wrap: wrap;
  }

  .attribution-source-row {
    grid-template-columns: minmax(0, 1fr) 30px 30px;
  }

  .retention-heading-row .retention-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .funnel-heading-row .funnel-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .path-heading-row {
    gap: 10px;
  }

  .distribution-heading-row .distribution-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .interval-heading-row .interval-subject-line {
    width: 100%;
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .revenue-heading-row .revenue-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .ranking-heading-row .ranking-subject-line {
    flex-basis: 100%;
    grid-template-columns: auto minmax(160px, 1fr) auto;
  }

  .revenue-event-flow,
  .revenue-metric-flow,
  .revenue-cost-field-row {
    flex-wrap: wrap;
  }

  .distribution-event-row {
    flex-wrap: wrap;
  }

  .distribution-simultaneous-core-controls {
    width: 100%;
    min-width: 0;
    flex: 1 1 100%;
    grid-template-columns: minmax(120px, 1fr) auto minmax(120px, 160px);
  }

  .distribution-simultaneous-core-controls :deep(.el-select) {
    width: 100%;
  }

  .ranking-metric-row,
  .ranking-extra-row {
    flex-wrap: wrap;
  }

  .ranking-metric-row :deep(.builder-field-picker),
  .ranking-extra-row :deep(.builder-field-picker),
  .ranking-alias-input {
    flex-basis: min(100%, 280px);
  }

  .interval-event-row,
  .interval-property-match {
    grid-template-columns: minmax(0, 1fr);
  }

  .interval-event-row .retention-event-action {
    justify-self: start;
  }

  .interval-limit-row {
    width: 100%;
  }

  .interval-limit-content {
    flex-wrap: wrap;
  }

  .path-initial-event-row {
    max-width: 100%;
    flex-wrap: wrap;
  }

  .path-session-row {
    flex-wrap: wrap;
  }
}

.retention-subject-line :deep(.builder-field-picker-trigger),
.retention-option-flow :deep(.builder-field-picker-trigger),
.retention-property-flow :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.retention-event-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.retention-field-block {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}

.retention-field-block :deep(.builder-field-picker-trigger) {
  width: auto;
  max-width: 100%;
}

.retention-event-editor {
  width: 100%;
  min-width: 0;
  padding: 5px 24px 7px 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  transition: background-color 0.16s ease;
}

.retention-event-editor:hover,
.retention-event-editor:focus-within,
.retention-event-editor.is-active {
  background: #f7f8fa;
}

.retention-event-alias-row,
.retention-event-main-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
}

.retention-event-main-row {
  min-height: 28px;
  justify-content: space-between;
  gap: 12px;
}

.retention-event-main-row :deep(.builder-field-picker) {
  min-width: 0;
}

.retention-event-alias-input {
  width: min(260px, 100%);
}

.retention-event-alias-input :deep(.ed-input__wrapper),
.retention-event-alias-input :deep(.el-input__wrapper) {
  min-height: 28px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.retention-event-alias-input :deep(.ed-input__wrapper:hover),
.retention-event-alias-input :deep(.ed-input__wrapper.is-focus),
.retention-event-alias-input :deep(.el-input__wrapper:hover),
.retention-event-alias-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: inset 0 -1px 0 #2f6bff;
}

.retention-event-alias-text {
  min-width: 0;
  color: #303643;
  font-size: 14px;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.retention-event-actions {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.16s ease;
}

.retention-event-editor:hover .retention-event-actions,
.retention-event-editor:focus-within .retention-event-actions,
.retention-event-editor.is-active .retention-event-actions {
  opacity: 1;
  visibility: visible;
}

.retention-event-action {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #7b8190;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}

.retention-event-action:hover,
.retention-event-action.is-active {
  background: #eef3ff;
  color: #2f6bff;
}

.retention-event-action:disabled {
  background: transparent;
  color: #c4c9d2;
  cursor: not-allowed;
}

.retention-event-filter-panel {
  width: 100%;
  min-width: 0;
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid #edf0f5;
}

.retention-config-label {
  padding: 0;
  color: #6b7280;
  font-size: 12px;
  line-height: 20px;
}

.retention-advanced-options {
  width: 100%;
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 24px;
}

.retention-option-block {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 9px;
  color: #505968;
  font-size: 12px;
}

.retention-option-title {
  color: #4e5969;
  line-height: 20px;
}

.retention-option-description {
  margin-top: 4px;
  color: #667085;
  line-height: 20px;
}

.retention-option-flow {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(120px, 1fr) auto 104px;
  align-items: center;
  gap: 8px;
}

.retention-option-flow.has-metric-field {
  grid-template-columns: minmax(100px, 1fr) auto 104px minmax(100px, 1fr);
}

.retention-property-flow {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(100px, 1fr) auto;
  align-items: center;
  gap: 6px;
  line-height: 24px;
}

.builder-icon-button {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #505968;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.builder-icon-button:hover {
  background: #eef3ff;
  color: #2f6bff;
}

.builder-icon-button.danger:hover {
  background: #fff1f0;
  color: #f04438;
}

.group-row :deep(.builder-field-picker-trigger) {
  width: 100%;
}

.sql-editor-time-range-picker :deep(.date-expression-trigger) {
  width: 100%;
  min-width: 0;
  justify-content: flex-start;
}

.metric-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.metric-item {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.metric-index {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: #171d4f;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
}

.metric-body {
  min-width: 0;
}

.metric-title {
  margin-bottom: 8px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.metric-title-input {
  width: min(288px, 100%);
  margin-bottom: 8px;
}

.metric-title-input :deep(.el-input__wrapper),
.formula-metric-title-input :deep(.el-input__wrapper) {
  min-height: 24px;
  padding: 0 8px;
  box-shadow: none;
  background: #f7f8fb;
  border: 1px solid transparent;
  border-radius: 6px;
}

.metric-title-input :deep(.el-input__wrapper:hover),
.metric-title-input :deep(.el-input__wrapper.is-focus),
.formula-metric-title-input :deep(.el-input__wrapper:hover),
.formula-metric-title-input :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  border-color: #2f6bff;
  box-shadow: none;
}

.metric-title-input :deep(.el-input__inner),
.formula-metric-title-input :deep(.el-input__inner) {
  height: 22px;
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
}

.metric-chip-row {
  display: grid;
  grid-template-columns: minmax(220px, 320px) 18px 104px 24px;
  column-gap: 8px;
  row-gap: 8px;
  align-items: center;
  min-height: 30px;
}

.metric-chip-row.has-metric-field {
  grid-template-columns: minmax(180px, 240px) 18px 104px minmax(112px, 180px) 24px;
}

.metric-chip-row.calculated-metric-row {
  grid-template-columns: 28px 72px 28px minmax(100px, 1fr) 24px;
}

.formula-metric-list {
  margin-top: 10px;
}

.formula-metric-item {
  border-top: 1px solid #edf0f7;
  padding-top: 10px;
}

.formula-metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
  margin-bottom: 6px;
}

.formula-metric-title-wrap {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.formula-metric-title-input {
  width: min(220px, 100%);
  flex: 0 1 220px;
}

.formula-metric-title {
  color: #1f2329;
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.formula-decimal-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 7px;
  background: #f4f6fb;
  color: #1f2329;
  font-size: 12px;
  white-space: nowrap;
}

.formula-metric-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.formula-icon-button {
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #7b8190;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
}

.formula-icon-button:hover {
  background: #eef3ff;
  color: #2f6bff;
}

.formula-icon-button.danger:hover {
  background: #fff0f0;
  color: #f56c6c;
}

.metric-chip-row :deep(.builder-field-picker-trigger) {
  width: 100%;
  max-width: none;
}

.metric-of {
  color: #8f959e;
  font-size: 12px;
  text-align: center;
}

.metric-field-select,
.metric-aggregation {
  width: 100%;
}

.formula-entry-button {
  font-size: 15px;
  font-weight: 700;
  line-height: 1;
}

.calculated-decimal {
  width: 100%;
}

.formula-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 8px;
  max-width: 100%;
}

.formula-display {
  display: flex;
  width: 100%;
  box-sizing: border-box;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 32px;
  padding: 7px 10px;
  border-radius: 6px;
  background: #fff;
  color: #1f2329;
  font-size: 13px;
  line-height: 18px;
  word-break: break-word;
  outline: none;
  cursor: text;
}

.formula-display.is-empty {
  color: #a8abb2;
}

.formula-display.is-invalid {
  background: #fff7f7;
}

.formula-error {
  color: #f56c6c;
  font-size: 12px;
  line-height: 18px;
}

.formula-toolbar {
  max-width: 100%;
}

.formula-toolbar-panel {
  display: inline-flex;
  flex-direction: column;
  gap: 8px;
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 0 0 12px 12px;
  background: #fff;
  box-shadow: 0 14px 32px rgba(31, 35, 41, 0.12);
}

.formula-keyboard-layout {
  display: grid;
  grid-template-columns: 90px 64px 116px;
  gap: 22px;
  align-items: start;
}

.formula-number-pad {
  display: grid;
  grid-template-columns: repeat(3, 26px);
  gap: 6px;
}

.formula-operator-pad {
  display: grid;
  grid-template-columns: repeat(2, 26px);
  gap: 6px;
}

.formula-command-panel {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  justify-items: stretch;
  gap: 2px;
  min-width: 116px;
}

.formula-metric-select {
  width: 88px;
}

.formula-placeholder {
  color: #a8abb2;
  pointer-events: none;
}

.formula-token {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0;
  border-radius: 6px;
  background: transparent;
  color: #1f2329;
  cursor: pointer;
  user-select: none;
  gap: 4px;
}

.formula-token-stack {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  max-width: 100%;
}

.formula-token-flow {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}

.formula-token-atomicMetric,
.formula-token-metric {
  color: #1f3a8a;
}

.formula-token-operator,
.formula-token-paren {
  padding: 2px 7px;
  background: #f5f7fb;
  color: #2f3542;
  font-weight: 700;
}

.formula-token-number {
  padding: 2px 7px;
  background: #f2f5fb;
  color: #1f3a8a;
}

.formula-atomic-event,
.formula-atomic-metric {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border-radius: 7px;
  background: #f4f6fb;
  color: #1f2329;
  font-size: 12px;
  line-height: 18px;
}

.formula-token-editor-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}

.formula-token-editor-row :deep(.builder-field-picker-trigger) {
  width: 160px;
  max-width: 180px;
  background: #f4f6fb;
}

.formula-token-aggregation {
  width: 88px;
}

.formula-token-filter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 7px;
  background: #f4f6fb;
  color: #7b8190;
  cursor: pointer;
}

.formula-token-filter-tree {
  margin: 0 0 2px;
}

.formula-token-of {
  color: #8f959e;
  font-size: 12px;
}

.formula-insert-target {
  width: 10px;
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 10px;
  border-radius: 4px;
  cursor: text;
}

.formula-insert-target:hover {
  background: #eef3ff;
}

.formula-insert-target.is-active {
  background: transparent;
}

.formula-cursor {
  width: 1px;
  height: 20px;
  background: #2f6bff;
  animation: formula-cursor-blink 1s step-end infinite;
}

@keyframes formula-cursor-blink {
  50% {
    opacity: 0;
  }
}

.formula-key-button {
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: #f2f5fb;
  color: #171d4f;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}

.formula-key-button:hover,
.formula-action-button:hover {
  background: #e8efff;
  color: #2f6bff;
}

.formula-number-key:last-child {
  grid-column: span 2;
  width: auto;
}

.formula-delete-key {
  grid-column: span 2;
  width: auto;
  text-align: center;
}

.formula-action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 30px;
  min-width: 116px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: #f2f5fb;
  color: #171d4f;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.formula-shortcut-hint {
  color: #b8beca;
  font-size: 12px;
  line-height: 16px;
  text-align: center;
}

.formula-shortcut-hint + .formula-action-button {
  margin-top: 8px;
}

.builder-add-link {
  height: 24px;
  padding: 0 6px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #2f6bff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.builder-add-link:hover {
  background: #eef3ff;
}

.builder-inline-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 9px;
}

.group-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 26px;
  gap: 6px;
  align-items: center;
}

.group-index {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  background: #f5f6fa;
  color: #8f959e;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.builder-empty {
  padding: 4px 0 2px;
  color: #8f959e;
  font-size: 12px;
}

.builder-bottom-bar {
  flex: 0 0 44px;
  height: 44px;
  padding: 7px 22px;
  border-top: 1px solid rgba(31, 35, 41, 0.08);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.builder-bottom-options {
  display: flex;
  gap: 12px;
  align-items: center;
}

.sql-detail-pane {
  flex: 1;
  min-height: 0;
  padding: 12px;
  display: flex;
}

.sql-detail-pane :deep(.el-textarea),
.sql-detail-pane :deep(.el-textarea__inner) {
  height: 100%;
  min-height: 100% !important;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 12px;
  line-height: 19px;
}

.sql-builder-panel :deep(.el-input__wrapper),
.sql-builder-panel :deep(.el-select__wrapper) {
  min-height: 26px;
  font-size: 12px;
  border-radius: 6px;
}

.sql-builder-panel :deep(.el-input__inner),
.sql-builder-panel :deep(.el-select__placeholder),
.sql-builder-panel :deep(.el-select__selected-item) {
  font-size: 12px;
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
