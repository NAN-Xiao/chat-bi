import type { ChartTypes } from '@/views/chat/component/BaseChart'
import type { RoiChart, RoiChartCreate, RoiChartUpdate, RoiLayoutSpan } from './types'

export interface RoiPivotConfig {
  enabled: boolean
  time_field?: string
  metric_field?: string
  metric_fields?: string[]
  group_field?: string
  group_enabled?: boolean
  granularity?: 'day' | 'week' | 'month'
  [key: string]: unknown
}

export interface RoiInsightSectionConfig {
  enabled: boolean
  metrics: string[]
}

export interface RoiInsightConfig {
  enabled: boolean
  comparison: RoiInsightSectionConfig
  aggregate: RoiInsightSectionConfig
  [key: string]: unknown
}

export interface RoiChartForm {
  sql: string
  title: string
  chartType: ChartTypes
  columns: string[]
  x: string
  y: string[]
  series: string
  pivotEnabled: boolean
  pivot: RoiPivotConfig
  insightEnabled: boolean
  insight: RoiInsightConfig
  layoutSpan: RoiLayoutSpan
  extraChartConfig: Record<string, unknown>
  version?: number
}

export function canCancelRoiEditor(saving: boolean): boolean {
  return !saving
}

export function getRoiChartMappingError(form: RoiChartForm): string {
  const hasColumns = form.columns.some((field) => field.trim())
  const hasY = form.y.some((field) => field.trim())
  const hasX = Boolean(form.x.trim())
  const hasSeries = Boolean(form.series.trim())

  if (form.chartType === 'table') {
    return hasColumns ? '' : '请选择至少一个表格列'
  }
  if (form.chartType === 'metric') {
    return hasY || hasColumns ? '' : '请选择至少一个指标字段'
  }
  if (form.chartType === 'pie') {
    if (!hasY) return '请选择至少一个 Y 轴字段'
    return hasSeries ? '' : '请选择系列字段'
  }
  if (!hasX) return '请选择 X 轴字段'
  if (!hasY) return '请选择至少一个 Y 轴字段'
  if ((form.chartType === 'heatmap' || form.chartType === 'sankey') && !hasSeries) {
    return '请选择系列字段'
  }
  return ''
}

const defaultPivot = (): RoiPivotConfig => ({
  enabled: false,
  time_field: '',
  metric_fields: [],
  group_field: '',
  group_enabled: false,
  granularity: 'day',
})

const defaultInsight = (): RoiInsightConfig => ({
  enabled: true,
  comparison: { enabled: true, metrics: ['change', 'changeRate'] },
  aggregate: { enabled: true, metrics: ['sum', 'avg'] },
})

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function cloneRecord<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const blockedConfigKeys = new Set([
  ['data', 'source'].join(''),
  ['data', 'source', 'id'].join(''),
  ['data', 'source', 'name'].join(''),
  ['tenant'].join(''),
  ['tenant', 'id'].join(''),
  ['tenant', 'name'].join(''),
])

const protocolKeyPrefix = ['m', 'c', 'p'].join('')
const externalProtocolKeyPrefix = ['external', 'm', 'c', 'p'].join('')

function isBlockedConfigKey(key: string): boolean {
  const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, '')
  return (
    blockedConfigKeys.has(normalized) ||
    normalized.startsWith(protocolKeyPrefix) ||
    normalized.startsWith(externalProtocolKeyPrefix)
  )
}

function sanitizeConfigValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeConfigValue)
  if (!value || typeof value !== 'object') return value
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !isBlockedConfigKey(key))
      .map(([key, item]) => [key, sanitizeConfigValue(item)])
  )
}

export function createEmptyRoiChartForm(): RoiChartForm {
  return {
    sql: '',
    title: '',
    chartType: 'table',
    columns: [],
    x: '',
    y: [],
    series: '',
    pivotEnabled: false,
    pivot: defaultPivot(),
    insightEnabled: true,
    insight: defaultInsight(),
    layoutSpan: 'full',
    extraChartConfig: {},
    version: undefined,
  }
}

export function hydrateRoiChartForm(chart?: RoiChart | null): RoiChartForm {
  if (!chart) return createEmptyRoiChartForm()
  const config = chart.chart_config || {}
  const {
    x: _x,
    y: _y,
    series: _series,
    columns: _columns,
    pivot: pivotValue,
    insight: insightValue,
    ...extraChartConfig
  } = config
  void _x
  void _y
  void _series
  void _columns
  const pivot =
    pivotValue && typeof pivotValue === 'object'
      ? (cloneRecord(pivotValue) as RoiPivotConfig)
      : defaultPivot()
  const insight =
    insightValue && typeof insightValue === 'object'
      ? (cloneRecord(insightValue) as RoiInsightConfig)
      : defaultInsight()
  return {
    sql: String(chart.sql || '').trim(),
    title: String(chart.title || ''),
    chartType: (chart.chart_type || 'table') as ChartTypes,
    columns: stringArray(config.columns),
    x: String(config.x || ''),
    y: stringArray(config.y),
    series: String(config.series || ''),
    pivotEnabled: pivot.enabled === true,
    pivot,
    insightEnabled: insight.enabled !== false,
    insight,
    layoutSpan: chart.layout_span || 'full',
    extraChartConfig: sanitizeConfigValue(extraChartConfig) as Record<string, unknown>,
    version: chart.version,
  }
}

export function replaceRoiChartForm(target: RoiChartForm, chart?: RoiChart | null): RoiChartForm {
  delete target.version
  Object.assign(target, hydrateRoiChartForm(chart))
  return target
}

export function serializeRoiChartForm(form: RoiChartForm): RoiChartCreate | RoiChartUpdate {
  const chartConfig = {
    ...form.extraChartConfig,
    x: form.x,
    y: [...form.y],
    series: form.series,
    columns: [...form.columns],
    pivot: { ...cloneRecord(form.pivot), enabled: form.pivotEnabled },
    insight: { ...cloneRecord(form.insight), enabled: form.insightEnabled },
  }
  const payload: RoiChartCreate = {
    title: form.title.trim(),
    sql: form.sql.trim(),
    chart_type: form.chartType,
    chart_config: sanitizeConfigValue(chartConfig) as Record<string, unknown>,
    layout_span: form.layoutSpan,
  }
  return form.version === undefined ? payload : { ...payload, version: form.version }
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)])
    )
  }
  return value
}

export function roiChartFormSignature(form: RoiChartForm): string {
  const { version: _version, ...payload } = serializeRoiChartForm(form) as RoiChartUpdate
  void _version
  return JSON.stringify(canonicalize(payload))
}

interface RoiRequestToken {
  session: number
  cycle: number
  request: number
  signature: string
}

export function createRoiEditorRequestGuard() {
  let session = 0
  let cycle = 0
  let request = 0
  let opened = false
  let previewSignature = ''
  let activePreview = 0
  let activeSave = 0

  const isCurrent = (token: RoiRequestToken) =>
    opened && token.session === session && token.request > 0

  return {
    beginSession() {
      session += 1
      cycle += 1
      opened = true
      previewSignature = ''
      activePreview = 0
      activeSave = 0
    },
    closeSession() {
      opened = false
      session += 1
      cycle += 1
      previewSignature = ''
      activePreview = 0
      activeSave = 0
    },
    invalidatePreview() {
      previewSignature = ''
      activePreview = 0
    },
    invalidateRequests() {
      session += 1
      previewSignature = ''
      activePreview = 0
      activeSave = 0
    },
    isCurrentSession(token: RoiRequestToken | null) {
      return Boolean(token && opened && token.session === session && token.cycle === cycle)
    },
    isCurrentOpenCycle(token: RoiRequestToken | null) {
      return Boolean(token && opened && token.cycle === cycle)
    },
    isActivePreview(token: RoiRequestToken) {
      return isCurrent(token) && token.request === activePreview
    },
    beginPreview(signature: string): RoiRequestToken {
      request += 1
      activePreview = request
      previewSignature = ''
      return { session, cycle, request, signature }
    },
    markPreviewSucceeded(token: RoiRequestToken, currentSignature: string) {
      if (
        !isCurrent(token) ||
        token.request !== activePreview ||
        token.signature !== currentSignature
      ) {
        return false
      }
      previewSignature = currentSignature
      return true
    },
    canSave(signature: string) {
      return opened && Boolean(signature) && previewSignature === signature
    },
    beginSave(signature: string): RoiRequestToken | null {
      if (!this.canSave(signature) || activeSave) return null
      request += 1
      activeSave = request
      return { session, cycle, request, signature }
    },
    markSaved(token: RoiRequestToken | null) {
      if (!token || !isCurrent(token) || token.request !== activeSave) return false
      activeSave = 0
      return true
    },
    markSaveFailed(token: RoiRequestToken | null) {
      if (token && isCurrent(token) && token.request === activeSave) activeSave = 0
    },
  }
}

export function getRoiChartSaveErrorMessage(error: unknown): string {
  const status = Number((error as any)?.response?.status)
  return status === 409 ? '数据已被其他人修改，请刷新后重试' : '保存 ROI 图表失败，请稍后重试'
}
