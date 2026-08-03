<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CopyDocument, Delete, Filter, MoreFilled, Plus, WarningFilled } from '@element-plus/icons-vue'
import { datasourceApi } from '@/api/datasource'
import { dashboardApi } from '@/api/dashboard.ts'
import { externalMcpApi, type ExternalMcpServerInfo, type ExternalMcpToolInfo } from '@/api/externalMcp.ts'
import { trackingConfigApi } from '@/api/system.ts'
import { request } from '@/utils/request.ts'
import { formatRequestErrorMessage } from '@/utils/request.ts'
import BuilderSectionIcon from '@/assets/svg/dv-view.svg'
import BuilderFieldPicker from '@/views/dashboard/common/BuilderFieldPicker.vue'
import BuilderFilterTree from '@/views/dashboard/common/BuilderFilterTree.vue'
import DashboardDateExpressionPicker from '@/views/dashboard/common/DashboardDateExpressionPicker.vue'
import {
  cloneDashboardDateExpression,
  defaultDashboardDateExpression,
  normalizeDashboardDateExpression,
  validateDashboardDateExpression,
  type DashboardDateExpression,
} from '@/views/dashboard/common/dashboardDateExpression.ts'
import {
  isEventUserPropertyOption,
  isNumericFieldOption,
  isSelectableFieldOption,
  isTimeFieldOption,
} from '@/views/dashboard/common/builderFieldPickerOptions.ts'
import {
  buildDashboardBuilderMetadataCacheKey,
  buildTrackingEventCatalogFromConfig,
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
  pivotGroupValues: [] as string[],
  mcpServerId: '',
  mcpTool: '',
  mcpArgumentsObject: {} as Record<string, any>,
  mcpArgumentsText: '{}',
  mcpResultPath: '',
  mcpKeyField: '',
  mcpValueField: '',
})
const sqlBuilder = reactive({
  activeTab: 'builder',
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
})
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

const builderTimeGrainOptions = [
  { label: '按天', value: 'day' },
  { label: '按周', value: 'week' },
  { label: '按月', value: 'month' },
  { label: '不按时间', value: 'none' },
]

const builderAggregationOptions = [
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
const eventUserPropertyOptions = computed(() =>
  builderFieldOptions.value.filter((option) => isEventUserPropertyOption(option, 'event'))
)
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
const builderMetricOptions = computed(() =>
  sqlBuilder.metricItems.map((item, index) => ({
    label: metricOutputAlias(item, index),
    value: item.id,
  }))
)
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
const showXAxis = computed(() => !['table', 'metric', 'pie'].includes(form.chartType))
const showSeries = computed(() => !['table', 'metric', 'funnel', 'scatter'].includes(form.chartType))
const supportsInsightConfig = computed(() => !['table', 'metric'].includes(form.chartType))
const supportsPivotConfig = computed(() => hasSqlSource.value && !hasMcpSource.value && !['table', 'metric'].includes(form.chartType))
const dateExpressionEnabled = computed(
  () => hasSqlSource.value && sqlBuilder.dateExpressionPickerEnabled === true && shouldUseDashboardDateParameters()
)

function shouldUseDashboardDateParameters(chartType: ChartTypes | string = form.chartType) {
  const supportsConfiguredMetric =
    chartType !== 'metric' || sqlBuilder.metricDateExpressionEnabled === true
  return supportsConfiguredMetric && Boolean(sqlBuilder.timeField)
}

function syncDashboardDateParameterUsage(chartType: ChartTypes | string = form.chartType) {
  const enabled = shouldUseDashboardDateParameters(chartType)
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

function metricFilterFieldOptions(item: SqlBuilderMetricItem) {
  const eventOption = fieldOptionByValue(item.field)
  if (
    eventOption?.kind !== 'tracking-event' ||
    !eventOption.eventName ||
    (eventOption.eventTable || eventOption.table) !== 'event'
  ) {
    return []
  }
  const options = [
    ...(trackingEventPropertyOptionsByEvent.value.get(eventOption.eventName) || []),
    ...eventUserPropertyOptions.value,
  ]
  return Array.from(new Map(options.map((option) => [option.value, option])).values())
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
    const candidates = unique([
      item.field,
      metricMeasureField(item),
      ...schemaFieldOptions.value
        .filter((field) => field.table === fieldOptionByValue(item.field)?.table)
        .map((field) => field.value),
    ])
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
  const issues: string[] = [...eventScopeIssues]
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
  return resultAdviceItems(result, 'issues').filter((item) => !isNonBlockingBuilderAdviceItem(item))
}

function resultNonBlockingIssueItems(result: any) {
  return resultAdviceItems(result, 'issues').filter(isNonBlockingBuilderAdviceItem)
}

function builderAgentBlockingIssues(result: any) {
  const localAdvice = collectLocalBuilderConfigIssues()
  return unique([
    ...localAdvice.issues,
    ...resultBlockingIssueItems(result),
  ])
}

function stopBuilderExecutionWithAdvice(result: any, generatedSql = '') {
  const localAdvice = collectLocalBuilderConfigIssues()
  setBuilderAgentAdvice({
    severity: 'warning',
    intent: result?.intent || inferBuilderIntentText(),
    message: result?.message || '配置 Agent 判断当前配置需要调整，未执行 SQL',
    advice: result?.advice || '按下面配置项改完再生成。',
    issues: unique([...localAdvice.issues, ...resultBlockingIssueItems(result)]),
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
  ElMessage.warning('配置 Agent 发现问题，已停止执行，请查看提示建议')
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
  syncDashboardDateParameterUsage(nextChartType || form.chartType)
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
      const [metadata, trackingConfigResult] = await Promise.all([
        dashboardApi.execution_datasource_metadata(datasourceId),
        trackingConfigApi.get().catch(() => null),
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
        trackingEventCatalog: buildTrackingEventCatalogFromConfig(trackingConfigResult),
      }
    })
    if (!isCurrentSchemaLoad()) {
      return
    }
    datasourceInfo.value = metadata.datasource
    trackingConfig.value = metadata.trackingConfig
    trackingEventCatalog.value = metadata.trackingEventCatalog
    schemaTables.value = metadata.schemaTables.length ? metadata.schemaTables : previewSchemaTables()
    if (!sqlBuilder.metricItems.length && !sqlBuilder.calculatedMetrics.length) {
      addMetricItem()
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
  initializedPivotGroupValueField.value = ''
  normalizePivotSelections()
  if (!form.pivotEnabled) {
    form.pivotGroupValues = []
    initializedPivotGroupValueField.value = ''
    return
  }
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
    group_enabled: Boolean(groupField && (form.pivotGroupEnabled || pivotGroupValues.length > 0)),
    dimensions: inferredPivotDimensions(),
    granularity: form.pivotGranularity,
    range: form.pivotRange,
    custom_start: form.pivotCustomStart,
    custom_end: form.pivotCustomEnd,
    aggregation: defaultPivotAggregation(),
  })
  if (options.includeGroupValues !== false) {
    config.group_values = pivotGroupValues
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
  resetSqlBuilderState()
  restoreSqlBuilderState(sourceConfig.sql?.builder || sourceConfig.builder)
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
  form.chartType = chart.sourceType || chart.type || 'table'
  form.columns = axisValues(chart.columns)
  form.x = axisValues(chart.xAxis)[0] || ''
  form.y = axisValues(chart.yAxis)
  pruneAutoSeededMetricItemsForFormulaOnlyBuilder()
  form.series = axisValues(chart.series)[0] || ''
  form.multiQuotaName = t('dashboard.metric_type')
  sourcePreview.fields = fields
  sourcePreview.data = viewInfo.data?.source_data || viewInfo.data?.data || []
  preview.fields = currentFields.length ? currentFields : fields
  preview.data = viewInfo.data?.data || []
  preview.status = 'success'
  preview.message = ''
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
        ElMessage.error('当前图表的日期配置尚未迁移，暂时无法编辑。')
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
    const sourceSnapshot = previewResultSnapshot(sourceResult)
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
  const strictMcpArguments = options.strictMcpArguments !== false
  const mcpArgumentsValue = currentMcpArgumentsForSave(strictMcpArguments)
  if (mcpArgumentsValue === null) {
    return false
  }
  const existingSourceConfig = chartSourceConfig(props.viewInfo)
  const { builder: _legacyBuilder, ...sourceConfigBase } = existingSourceConfig
  void _legacyBuilder
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
          ...(existingSourceConfig.sql || {}),
          datasource: selectedExecutionDatasourceId.value,
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
            <section class="builder-section">
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
              <el-checkbox v-if="sqlBuilder.activeTab === 'builder'" v-model="sqlBuilder.approximate">
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
            :disabled="executionDatasourceOptions.length <= 1"
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
