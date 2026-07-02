import { dashboardApi } from '@/api/dashboard.ts'
import { externalMcpApi } from '@/api/externalMcp.ts'

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
  return {
    datasource: sourceSql.datasource || viewInfo.datasource,
    sql: (sourceSql.sql || viewInfo.sql || '').trim(),
    pivot: viewInfo.pivot?.enabled === true ? viewInfo.pivot : undefined,
  }
}

function mcpPayload(viewInfo: any) {
  const sourceMcp = viewInfo?.sourceConfig?.mcp || viewInfo?.mcp || {}
  return {
    external_mcp_server_id: sourceMcp.externalMcpServerId || sourceMcp.external_mcp_server_id || viewInfo.external_mcp_server_id,
    tenant_id: sourceMcp.tenantId || sourceMcp.tenant_id || viewInfo.tenant_id || null,
    dashboard_id: sourceMcp.dashboardId || sourceMcp.dashboard_id || viewInfo.dashboard_id || null,
    tool: sourceMcp.tool,
    arguments: sourceMcp.arguments || {},
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
  const sqlPayload = chartSqlPayload(viewInfo)
  const mcp = mcpPayload(viewInfo)
  return Boolean(isMixedChart(viewInfo) && sqlPayload.datasource && sqlPayload.sql && mcp.external_mcp_server_id && mcp.tool)
}

export async function refreshMixedChartData(viewInfo: any, options: MixedRefreshOptions = {}) {
  const sqlPayload = chartSqlPayload(viewInfo)
  const mcp = mcpPayload(viewInfo)
  const sqlRequest = {
    ...sqlPayload,
    ...(options.cacheOnly ? { cache_only: true } : {}),
    ...(options.forceRefresh ? { force_refresh: true } : {}),
  }
  const sqlResult = await dashboardApi.preview_sql(sqlRequest, options.requestConfig)
  if (sqlResult?.status === 'failed') {
    return sqlResult
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
  const merged = mergeMixedChartResults(sqlResult, mcpResult, viewInfo?.sourceConfig?.merge)
  const refreshedAt = Number(sqlResult?.refreshed_at || sqlResult?.cache_refreshed_at || 0)
  return {
    ...merged,
    ...(sqlResult?.cache_hit !== undefined ? { cache_hit: sqlResult.cache_hit } : {}),
    ...(sqlResult?.cache_stale !== undefined ? { cache_stale: sqlResult.cache_stale } : {}),
    ...(sqlResult?.refresh_deferred !== undefined ? { refresh_deferred: sqlResult.refresh_deferred } : {}),
    refreshed_at: Number.isFinite(refreshedAt) && refreshedAt > 0 ? refreshedAt : Date.now(),
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
