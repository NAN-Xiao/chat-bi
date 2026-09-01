import { dashboardApi } from '@/api/dashboard.ts'
import { externalMcpApi } from '@/api/externalMcp.ts'
import {
  buildDashboardDateFilterRequestForView,
  canShowDashboardDateFilter,
  getOrCreateDashboardDateFilterState,
} from '@/views/dashboard/utils/dashboardDateFilter.ts'
import { shapeDistributionTableResult } from '@/views/dashboard/utils/distributionTable.ts'

type ChartDataSourceType = 'sql' | 'external_mcp'

type PreviewResultSnapshot = {
  fields: string[]
  data: Array<Record<string, any>>
  status: string
  message: string
  raw?: any
  [key: string]: any
}

type MixedRefreshOptions = {
  forceRefresh?: boolean
  cacheOnly?: boolean
  requestConfig?: any
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const DAY_MS = 24 * 60 * 60 * 1000

function unique(values: Array<string | undefined | null>) {
  return Array.from(new Set(values.filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '').map((value) => `${value}`)))
}

export function getPreviewResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

function previewResultSnapshot(result: any): PreviewResultSnapshot {
  return {
    ...result,
    fields: getPreviewResultFields(result),
    data: Array.isArray(result?.data) ? result.data : [],
    status: result?.status || 'success',
    message: result?.message || '',
    raw: result?.raw,
  }
}

function hasUsablePreviewResult(result: any) {
  if (!result || result?.status === 'failed') {
    return false
  }
  return (
    (Array.isArray(result?.data) && result.data.length > 0) ||
    getPreviewResultFields(result).length > 0
  )
}

function dashboardCacheMissResult(message = '看板缓存未命中') {
  return {
    status: 'failed',
    fields: [],
    data: [],
    message,
    reason: message,
    error_type: 'dashboard_cache_miss',
  }
}

function failedPreviewResult(message: string, errorType = 'external_mcp_refresh_failed') {
  return {
    status: 'failed',
    fields: [],
    data: [],
    message,
    reason: message,
    error_type: errorType,
  }
}

export function isMixedChart(viewInfo: any) {
  const sources = viewInfo?.sourceConfig?.sources || viewInfo?.sources
  return (
    viewInfo?.dataSourceType === 'mixed' ||
    viewInfo?.sourceConfig?.mode === 'mixed' ||
    (Array.isArray(sources) && sources.includes('sql') && sources.includes('external_mcp'))
  )
}

export function isExternalMcpSnapshotChart(viewInfo: any) {
  return viewInfo?.dataSourceType === 'external_mcp' || (
    viewInfo?.externalSnapshot === true && !isMixedChart(viewInfo)
  )
}

function parseIsoDate(value: any) {
  const text = `${value || ''}`
  if (!ISO_DATE_RE.test(text)) {
    return null
  }
  const [year, month, day] = text.split('-').map((item) => Number(item))
  return new Date(Date.UTC(year, month - 1, day))
}

function formatIsoDate(value: Date) {
  const year = value.getUTCFullYear()
  const month = `${value.getUTCMonth() + 1}`.padStart(2, '0')
  const day = `${value.getUTCDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function shiftIsoDate(value: string, offsetDays: number) {
  const date = parseIsoDate(value)
  if (!date) {
    return value
  }
  date.setUTCDate(date.getUTCDate() + offsetDays)
  return formatIsoDate(date)
}

function inclusiveDateWindowDays(startDate: any, endDate: any) {
  const start = parseIsoDate(startDate)
  const end = parseIsoDate(endDate)
  if (!start || !end) {
    return 0
  }
  return Math.max(1, Math.round((end.getTime() - start.getTime()) / DAY_MS) + 1)
}

function todayInTimezone(timezone?: string) {
  if (!timezone) {
    return formatIsoDate(new Date(Date.UTC(
      new Date().getFullYear(),
      new Date().getMonth(),
      new Date().getDate()
    )))
  }
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date())
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
    if (values.year && values.month && values.day) {
      return `${values.year}-${values.month}-${values.day}`
    }
  } catch (_error) {
    // Fall back to the browser date if the MCP server advertises an unknown timezone.
  }
  return formatIsoDate(new Date(Date.UTC(
    new Date().getFullYear(),
    new Date().getMonth(),
    new Date().getDate()
  )))
}

function chartTitle(viewInfo: any) {
  return `${viewInfo?.chart?.title || viewInfo?.title || ''}`
}

function titleLooksRelativeDateWindow(title: string) {
  return /(?:近|最近|过去)\s*\d+\s*(?:日|天)/.test(title) || /\b(?:last|recent|past)\s*\d+\s*days?\b/i.test(title)
}

function configuredRelativeDateWindow(sourceMcp: any, viewInfo: any) {
  return sourceMcp?.dateWindow || sourceMcp?.relativeDateWindow || viewInfo?.dateWindow || viewInfo?.relativeDateWindow || null
}

function relativeDateWindowDays(config: any) {
  if (!config || typeof config !== 'object') {
    return 0
  }
  const days = Number(config.days || config.value || config.windowDays || config.recentDays)
  return Number.isFinite(days) && days > 0 ? Math.round(days) : 0
}

function shouldRefreshDateWindow(sourceMcp: any, viewInfo: any) {
  if (sourceMcp?.autoRefreshDateWindow === false) {
    return false
  }
  if (sourceMcp?.autoRefreshDateWindow === true || configuredRelativeDateWindow(sourceMcp, viewInfo)) {
    return true
  }
  return titleLooksRelativeDateWindow(chartTitle(viewInfo))
}

function withResolvedMcpDateWindow(argumentsValue: Record<string, any>, sourceMcp: any, viewInfo: any) {
  if (!argumentsValue?.start_date || !argumentsValue?.end_date) {
    return argumentsValue
  }
  if (!ISO_DATE_RE.test(`${argumentsValue.start_date}`) || !ISO_DATE_RE.test(`${argumentsValue.end_date}`)) {
    return argumentsValue
  }
  if (!shouldRefreshDateWindow(sourceMcp, viewInfo)) {
    return argumentsValue
  }
  const explicitDays = relativeDateWindowDays(configuredRelativeDateWindow(sourceMcp, viewInfo))
  const days = explicitDays || inclusiveDateWindowDays(argumentsValue.start_date, argumentsValue.end_date)
  if (!days) {
    return argumentsValue
  }
  const endDate = todayInTimezone(sourceMcp?.timezone || argumentsValue.timezone)
  return {
    ...argumentsValue,
    start_date: shiftIsoDate(endDate, -(days - 1)),
    end_date: endDate,
  }
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

function isDateLikeField(field: string) {
  return /(^|[_\s-])(date|day|dt|time|month|week)($|[_\s-])/i.test(field)
}

function preferredJoinFields(sqlResult: PreviewResultSnapshot, mcpResult: PreviewResultSnapshot) {
  const commonFields = sqlResult.fields.filter((field) => mcpResult.fields.includes(field))
  const preferred = commonFields.filter((field) =>
    isDateLikeField(field) ||
    (!hasNumericValues(sqlResult.data, field) && !hasNumericValues(mcpResult.data, field))
  )
  return preferred.length ? preferred : commonFields.slice(0, 1)
}

function prefixedSourceField(type: ChartDataSourceType, field: string) {
  return `${type === 'sql' ? 'SQL' : 'MCP'}.${field}`
}

export function mergeMixedChartResults(
  sqlResultInput: any,
  mcpResultInput: any,
  mergeConfig: any = {}
): PreviewResultSnapshot {
  const sqlResult = previewResultSnapshot(sqlResultInput)
  const mcpResult = previewResultSnapshot(mcpResultInput)
  if (sqlResult.status === 'failed') {
    return sqlResult
  }
  if (mcpResult.status === 'failed') {
    return mcpResult
  }

  const configuredJoinFields = Array.isArray(mergeConfig?.joinFields) ? mergeConfig.joinFields : []
  const joinFields = configuredJoinFields.length
    ? configuredJoinFields.filter((field: string) => sqlResult.fields.includes(field) && mcpResult.fields.includes(field))
    : preferredJoinFields(sqlResult, mcpResult)
  if (!joinFields.length) {
    return {
      fields: [],
      data: [],
      status: 'failed',
      message: 'SQL and MCP results do not have a common dimension field to merge.',
    }
  }

  const allMetricFields = [
    ...sqlResult.fields.filter((field) => !joinFields.includes(field)),
    ...mcpResult.fields.filter((field) => !joinFields.includes(field)),
  ]
  const duplicatedMetricFields = new Set(
    allMetricFields.filter((field, index) => allMetricFields.indexOf(field) !== index)
  )
  const configuredFieldMap = mergeConfig?.fieldMap || {}
  const fieldMap: Record<ChartDataSourceType, Record<string, string>> = {
    sql: { ...(configuredFieldMap.sql || {}) },
    external_mcp: { ...(configuredFieldMap.external_mcp || {}) },
  }
  const makeOutputField = (type: ChartDataSourceType, field: string) =>
    joinFields.includes(field)
      ? field
      : fieldMap[type][field] || (duplicatedMetricFields.has(field) ? prefixedSourceField(type, field) : field)
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
        joinFields.forEach((field: string) => {
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
    status: 'success',
    message: '',
    fields: outputFields,
    data: rowOrder.map((key) => rowMap.get(key)!).filter(Boolean),
    merge: {
      strategy: 'join_by_common_dimensions',
      joinFields,
      fieldMap,
    },
    sourceResults: {
      sql: sqlResult,
      external_mcp: mcpResult,
    },
  }
}

function chartSqlPayload(viewInfo: any) {
  const sourceSql = viewInfo?.sourceConfig?.sql || {}
  const dateFilterState = canShowDashboardDateFilter(viewInfo?.dateFilterCapability)
    ? getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability)
    : null
  return {
    datasource: viewInfo.datasource,
    sql: (sourceSql.sql || viewInfo.sql || '').trim(),
    pivot: viewInfo.pivot?.enabled === true ? viewInfo.pivot : undefined,
    date_filter: buildDashboardDateFilterRequestForView(
      viewInfo,
      dateFilterState?.appliedRange
    ),
  }
}

function normalizeDatasourceId(value: any) {
  const datasourceId = Number(value)
  return Number.isInteger(datasourceId) && datasourceId > 0 ? datasourceId : null
}

function mixedChartDatasourceFailure(viewInfo: any) {
  const outer = normalizeDatasourceId(viewInfo?.datasource)
  const inner = normalizeDatasourceId(viewInfo?.sourceConfig?.sql?.datasource)
  if (outer && inner && outer !== inner) {
    return failedPreviewResult(
      `图表执行数据源配置冲突：viewInfo.datasource=${outer}，sourceConfig.sql.datasource=${inner}。请重新选择数据源并预览后保存。`,
      'dashboard_chart_datasource_conflict'
    )
  }
  if (!outer && inner) {
    return failedPreviewResult(
      '图表只有旧版 sourceConfig.sql.datasource，必须完成数据源与 Schema 校验后迁移。',
      'dashboard_chart_datasource_legacy_only'
    )
  }
  if (!outer) {
    return failedPreviewResult(
      '图表未配置执行数据源，请重新选择数据源并预览后保存。',
      'dashboard_chart_datasource_missing'
    )
  }
  return null
}

function mcpPayload(viewInfo: any) {
  const sourceMcp = viewInfo?.sourceConfig?.mcp || viewInfo?.mcp || {}
  const argumentsValue = withResolvedMcpDateWindow({ ...(sourceMcp.arguments || {}) }, sourceMcp, viewInfo)
  return {
    external_mcp_server_id: sourceMcp.externalMcpServerId || sourceMcp.external_mcp_server_id || viewInfo.external_mcp_server_id,
    tenant_id: sourceMcp.tenantId || sourceMcp.tenant_id || viewInfo.tenant_id || null,
    dashboard_id: sourceMcp.dashboardId || sourceMcp.dashboard_id || viewInfo.dashboard_id || null,
    tool: sourceMcp.tool,
    arguments: argumentsValue,
    result_path: sourceMcp.resultPath || sourceMcp.result_path || null,
    key_field: sourceMcp.keyField || sourceMcp.key_field || null,
    value_field: sourceMcp.valueField || sourceMcp.value_field || null,
  }
}

function cachedMcpResult(viewInfo: any) {
  return (
    viewInfo?.sourceConfig?.mcp?.lastResult ||
    viewInfo?.mcp?.lastResult ||
    viewInfo?.sourceConfig?.external_mcp?.lastResult ||
    null
  )
}

export function canRefreshMixedChart(viewInfo: any) {
  if (mixedChartDatasourceFailure(viewInfo)) {
    return false
  }
  const sqlPayload = chartSqlPayload(viewInfo)
  const mcp = mcpPayload(viewInfo)
  return Boolean(isMixedChart(viewInfo) && sqlPayload.datasource && sqlPayload.sql && mcp.external_mcp_server_id && mcp.tool)
}

function chartBoundFields(viewInfo: any) {
  const chart = viewInfo?.chart || {}
  return unique([
    ...(Array.isArray(chart?.xAxis) ? chart.xAxis.map((item: any) => item?.value || item?.name) : []),
    ...(Array.isArray(chart?.yAxis) ? chart.yAxis.map((item: any) => item?.value || item?.name) : []),
    ...(Array.isArray(chart?.series) ? chart.series.map((item: any) => item?.value || item?.name) : []),
  ])
}

function missingBoundFields(viewInfo: any, fields: string[]) {
  const available = new Set(fields)
  return chartBoundFields(viewInfo).filter((field) => !available.has(field))
}

export function canRefreshExternalMcpSnapshotChart(viewInfo: any) {
  const mcp = mcpPayload(viewInfo)
  return Boolean(isExternalMcpSnapshotChart(viewInfo) && mcp.external_mcp_server_id && mcp.tool)
}

export async function refreshExternalMcpSnapshotData(viewInfo: any, options: MixedRefreshOptions = {}) {
  const payload = mcpPayload(viewInfo)
  if (!payload.external_mcp_server_id || !payload.tool) {
    return failedPreviewResult('当前图表缺少第三方 MCP 数据源配置', 'external_mcp_missing_config')
  }
  const result = await externalMcpApi.preview(payload, options.requestConfig)
  const normalized = previewResultSnapshot(result)
  if (normalized.status === 'failed') {
    return normalized
  }
  const missing = missingBoundFields(viewInfo, normalized.fields)
  if (missing.length) {
    return {
      ...normalized,
      status: 'failed',
      message: `MCP 返回字段缺少当前图表绑定字段：${missing.join('、')}。请调整 MCP 结果路径或使用能返回同结构数据的 MCP 函数。`,
      error_type: 'external_mcp_shape_mismatch',
    }
  }
  return {
    ...normalized,
    refreshed_at: Date.now(),
  }
}

export async function refreshMixedChartData(viewInfo: any, options: MixedRefreshOptions = {}) {
  const datasourceFailure = mixedChartDatasourceFailure(viewInfo)
  if (datasourceFailure) {
    return datasourceFailure
  }
  const sqlPayload = chartSqlPayload(viewInfo)
  const mcp = mcpPayload(viewInfo)
  const sqlRequest = {
    ...sqlPayload,
    ...(options.cacheOnly ? { cache_only: true } : {}),
    ...(options.forceRefresh ? { force_refresh: true } : {}),
  }
  const sqlResult = await dashboardApi.preview_sql(sqlRequest, options.requestConfig)
  const shapedSqlResult = shapeDistributionTableResult(sqlResult, viewInfo)
  if (shapedSqlResult?.status === 'failed') {
    return shapedSqlResult
  }
  let mcpResult: any = null
  if (options.cacheOnly) {
    mcpResult = cachedMcpResult(viewInfo)
    if (!hasUsablePreviewResult(mcpResult)) {
      return dashboardCacheMissResult('混合图表 MCP 缓存未命中')
    }
  } else {
    mcpResult = await externalMcpApi.preview(mcp, options.requestConfig)
  }
  const merged = mergeMixedChartResults(shapedSqlResult, mcpResult, viewInfo?.sourceConfig?.merge)
  const refreshedAt = Number(sqlResult?.refreshed_at || sqlResult?.cache_refreshed_at || 0)
  return {
    ...merged,
    ...(sqlResult?.cache_hit !== undefined ? { cache_hit: sqlResult.cache_hit } : {}),
    ...(sqlResult?.cache_stale !== undefined ? { cache_stale: sqlResult.cache_stale } : {}),
    ...(sqlResult?.refresh_deferred !== undefined ? { refresh_deferred: sqlResult.refresh_deferred } : {}),
    refreshed_at: Number.isFinite(refreshedAt) && refreshedAt > 0 ? refreshedAt : Date.now(),
  }
}

export function applyExternalMcpSnapshotResult(viewInfo: any, result: any) {
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  const fields = getPreviewResultFields(result)
  const data = Array.isArray(result?.data) ? result.data : []
  viewInfo.data.fields = fields
  viewInfo.data.data = data
  viewInfo.data.source_fields = fields
  viewInfo.data.source_data = data
  viewInfo.data.raw = result?.raw
  viewInfo.fields = fields
  viewInfo.status = result?.status || 'success'
  viewInfo.message = result?.message || ''
  viewInfo.dataState = viewInfo.status === 'failed' ? 'failed' : 'ready'
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
  viewInfo.externalSnapshot = true
  viewInfo.dataSourceType = 'external_mcp'
  if (result?.mcp) {
    const nextMcp = {
      ...((viewInfo.sourceConfig?.mcp || viewInfo.mcp || {}) as Record<string, any>),
      ...result.mcp,
      lastResult: previewResultSnapshot(result),
    }
    viewInfo.mcp = {
      ...(viewInfo.mcp || {}),
      ...nextMcp,
    }
    viewInfo.sourceConfig = {
      ...(viewInfo.sourceConfig || {}),
      mode: viewInfo.sourceConfig?.mode || 'external_mcp',
      mcp: {
        ...(viewInfo.sourceConfig?.mcp || {}),
        ...nextMcp,
      },
    }
  }
}

export function applyMixedChartResult(viewInfo: any, result: any) {
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  const fields = getPreviewResultFields(result)
  const data = Array.isArray(result?.data) ? result.data : []
  viewInfo.data.fields = fields
  viewInfo.data.data = data
  viewInfo.data.source_fields = fields
  viewInfo.data.source_data = data
  viewInfo.fields = fields
  viewInfo.status = result?.status || 'success'
  viewInfo.message = result?.message || ''
  viewInfo.dataState = viewInfo.status === 'failed' ? 'failed' : 'ready'
  viewInfo.loadingProgress = 100
  viewInfo.refreshState = ''
  viewInfo.externalSnapshot = false
  viewInfo.dataSourceType = 'mixed'
  if (result?.merge) {
    viewInfo.sourceConfig = {
      ...(viewInfo.sourceConfig || {}),
      mode: 'mixed',
      merge: result.merge,
      sql: {
        ...(viewInfo.sourceConfig?.sql || {}),
        lastResult: result.sourceResults?.sql,
      },
      mcp: {
        ...(viewInfo.sourceConfig?.mcp || {}),
        lastResult: result.sourceResults?.external_mcp,
      },
    }
  }
}
