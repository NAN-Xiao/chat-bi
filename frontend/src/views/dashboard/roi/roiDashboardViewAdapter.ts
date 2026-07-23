import type {
  RoiCanvasViewInfo,
  RoiChart,
  RoiChartCreate,
  RoiChartUpdate,
  RoiConfig,
  RoiDashboardComponentItem,
  RoiLayoutSpan,
} from './types'

type UnknownRecord = Record<string, any>

export interface RoiDashboardViewInfo extends Record<string, any> {
  id: string
  datasource: number
  sql: string
  chart: UnknownRecord
  data: { fields: string[]; data: Array<Record<string, unknown>> }
  sourceConfig: UnknownRecord
}

const blockedConfigKeys = new Set([
  'datasource',
  'datasourceid',
  'datasourcename',
  'tenant',
  'tenantid',
  'tenantname',
  'mcp',
  'externalmcp',
  'externalmcpserverid',
])

function cloneValue<T>(value: T): T {
  if (Array.isArray(value)) return value.map(cloneValue) as T
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as UnknownRecord).map(([key, item]) => [key, cloneValue(item)])
    ) as T
  }
  return value
}

function normalizedKey(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function isBlockedConfigKey(key: string): boolean {
  const normalized = normalizedKey(key)
  return blockedConfigKeys.has(normalized) || normalized.startsWith('mcp') || normalized.startsWith('externalmcp')
}

function sanitizeRoiConfig(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeRoiConfig)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value as UnknownRecord)
      .filter(([key]) => !isBlockedConfigKey(key))
      .map(([key, item]) => [key, sanitizeRoiConfig(item)])
  )
}

function axisArray(value: unknown): Array<UnknownRecord> {
  if (Array.isArray(value)) {
    return value.flatMap((item) => axisArray(item))
  }
  if (value && typeof value === 'object') return [cloneValue(value) as UnknownRecord]
  if (typeof value === 'string' && value) return [{ value }]
  return []
}

function chartAxes(chartConfig: UnknownRecord) {
  return {
    xAxis: axisArray(chartConfig.xAxis ?? chartConfig.x),
    yAxis: axisArray(chartConfig.yAxis ?? chartConfig.y),
    series: axisArray(chartConfig.series),
  }
}

function roiSourceConfig(config: RoiConfig, sourceConfig?: UnknownRecord): UnknownRecord {
  const source = (sanitizeRoiConfig(sourceConfig || {}) || {}) as UnknownRecord
  const sql = (source.sql && typeof source.sql === 'object' ? source.sql : {}) as UnknownRecord
  return {
    ...source,
    sources: ['sql'],
    primarySource: 'sql',
    sql: { ...sql, datasource: config.datasource_id },
    mcp: null,
  }
}

function payloadSourceConfig(sourceConfig: UnknownRecord): UnknownRecord {
  const {
    mcp: _mcp,
    sources: _sources,
    primarySource: _primarySource,
    mode: _mode,
    sourceTypes: _sourceTypes,
    dataSourceType: _dataSourceType,
    ...rest
  } = sanitizeRoiConfig(sourceConfig) as UnknownRecord
  void _mcp
  void _sources
  void _primarySource
  void _mode
  void _sourceTypes
  void _dataSourceType
  return { ...rest, sources: ['sql'], primarySource: 'sql' }
}

export function roiChartToDashboardViewInfo(chart: RoiChart, config: RoiConfig): RoiDashboardViewInfo {
  const chartConfig = cloneValue(chart.chart_config || {}) as UnknownRecord
  const { sourceConfig: storedSourceConfig, ...storedChart } = chartConfig
  const axes = chartAxes(storedChart)
  const queryResult = chart.query_result
  return {
    id: String(chart.id),
    datasource: config.datasource_id,
    sql: String(chart.sql || ''),
    sourceConfig: roiSourceConfig(config, storedSourceConfig),
    sources: ['sql'],
    primarySource: 'sql',
    data: {
      fields: Array.isArray(queryResult?.fields) ? [...queryResult.fields] : [],
      data: Array.isArray(queryResult?.data) ? cloneValue(queryResult.data) : [],
    },
    fields: Array.isArray(queryResult?.fields) ? [...queryResult.fields] : [],
    status: queryResult?.status || 'success',
    dataState: 'ready',
    loadingProgress: 100,
    message: queryResult?.message || '',
    chart: {
      ...(sanitizeRoiConfig(storedChart) as UnknownRecord),
      id: String(chart.id),
      type: chart.chart_type || 'table',
      sourceType: chart.chart_type || 'table',
      title: chart.title || '',
      columns: Array.isArray(storedChart.columns) ? cloneValue(storedChart.columns) : [],
      ...axes,
    },
  }
}

export function createRoiDashboardViewInfo(config: RoiConfig): RoiDashboardViewInfo {
  return {
    id: '',
    datasource: config.datasource_id,
    sql: '',
    sourceConfig: roiSourceConfig(config),
    sources: ['sql'],
    primarySource: 'sql',
    data: { fields: [], data: [] },
    fields: [],
    status: 'success',
    dataState: 'ready',
    loadingProgress: 100,
    message: '',
    chart: {
      id: '',
      type: 'table',
      sourceType: 'table',
      title: '',
      columns: [],
      xAxis: [],
      yAxis: [],
      series: [],
    },
  }
}

export function dashboardViewInfoToRoiPayload(
  viewInfo: RoiDashboardViewInfo,
  options: { version?: number; layoutSpan: RoiLayoutSpan }
): RoiChartCreate | RoiChartUpdate {
  const chart = cloneValue(viewInfo.chart || {}) as UnknownRecord
  const { id: _id, type, sourceType: _sourceType, title, ...chartConfig } = chart
  void _id
  void _sourceType
  const payload: RoiChartCreate = {
    title: String(title || ''),
    sql: String(viewInfo.sql || ''),
    chart_type: String(type || 'table'),
    chart_config: {
      ...(sanitizeRoiConfig(chartConfig) as UnknownRecord),
      sourceConfig: payloadSourceConfig(viewInfo.sourceConfig || {}),
    },
    layout_span: options.layoutSpan,
  }
  return options.version === undefined ? payload : { ...payload, version: options.version }
}

export function roiChartToComponentItem(chart: RoiChart): RoiDashboardComponentItem {
  return {
    id: String(chart.id),
    component: 'SQView',
    label: chart.title || '',
    propValue: '',
    x: 1,
    y: 1,
    sizeX: 12,
    sizeY: 6,
  }
}

export function roiChartsToCanvasViewInfo(charts: RoiChart[], config: RoiConfig): RoiCanvasViewInfo {
  return Object.fromEntries(
    charts.map((chart) => [String(chart.id), roiChartToDashboardViewInfo(chart, config)])
  )
}
