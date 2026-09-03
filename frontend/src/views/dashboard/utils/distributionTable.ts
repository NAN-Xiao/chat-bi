type TabularResult = Record<string, any>
type TabularRow = Record<string, any>

export const DISTRIBUTION_DATE_COLUMN = '事件发生时间'
export const DISTRIBUTION_TOTAL_COLUMN = '全部用户'

const DISTRIBUTION_SOURCE_FIELDS = [
  'distribution_date',
  'total_entities',
  'interval_order',
  'interval_label',
  'entity_count',
  'entity_rate',
  'simultaneous_value',
] as const

const REQUIRED_DISTRIBUTION_SOURCE_FIELDS = [
  'distribution_date',
  'total_entities',
  'interval_order',
  'interval_label',
  'entity_count',
] as const

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)))
}

function resultFields(result: TabularResult) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields.map(String) : []),
    ...(Array.isArray(result?.data)
      ? result.data.flatMap((row: TabularRow) => Object.keys(row || {}))
      : []),
  ])
}

function distributionBuilder(context: any) {
  if (!context || typeof context !== 'object') return null
  if (context.analysisModel || context.analysis_model) return context
  const sourceConfig = context.sourceConfig || context.source_config || {}
  return sourceConfig?.sql?.builder || sourceConfig?.builder || null
}

export function isDistributionTableContext(context: any) {
  const builder = distributionBuilder(context)
  return String(builder?.analysisModel || builder?.analysis_model || '') === 'distribution'
}

function distributionMetricKind(context: any) {
  const builder = distributionBuilder(context)
  return String(builder?.distribution?.metric?.kind || 'count')
}

function normalizedComparableValue(value: any) {
  if (value === null || value === undefined) return ''
  if (value instanceof Date) return value.toISOString()
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function isValidDateParts(year: string, month: string, day: string) {
  const timestamp = Date.UTC(Number(year), Number(month) - 1, Number(day))
  const parsed = new Date(timestamp)
  return (
    parsed.getUTCFullYear() === Number(year)
    && parsed.getUTCMonth() + 1 === Number(month)
    && parsed.getUTCDate() === Number(day)
  )
}

function distributionDateValue(value: any) {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? value : value.toISOString().slice(0, 10)
  }
  const text = String(value ?? '').trim()
  const compactDate = text.match(/^(\d{4})(\d{2})(\d{2})$/)
  if (compactDate) {
    const [, year, month, day] = compactDate
    if (isValidDateParts(year, month, day)) {
      return `${year}-${month}-${day}`
    }
  }
  const dateTime = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/)
  return dateTime && isValidDateParts(dateTime[1], dateTime[2], dateTime[3])
    ? `${dateTime[1]}-${dateTime[2]}-${dateTime[3]}`
    : value
}

function normalizedGroupKeyValue(value: any) {
  if (value === null) return ['null']
  if (value === undefined) return ['undefined']
  if (value instanceof Date) return ['date', normalizedComparableValue(value)]
  if (typeof value === 'object') return ['object', normalizedComparableValue(value)]
  return [typeof value, value]
}

function groupKey(row: TabularRow, groupFields: string[]) {
  return JSON.stringify([
    ['date', distributionDateValue(row.distribution_date)],
    ...groupFields.map((field) => normalizedGroupKeyValue(row?.[field])),
  ])
}

function compactNumber(value: string) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? String(numberValue) : value
}

function countIntervalLabel(label: any, order: any) {
  let text = String(label ?? '').trim() || String(order ?? '').trim()
  if (!text) return ''
  if (text.endsWith('次')) return text
  const range = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$/)
  if (range && Number(range[1]) === Number(range[2])) {
    text = compactNumber(range[1])
  } else if (/^-?\d+(?:\.\d+)?$/.test(text)) {
    text = compactNumber(text)
  }
  return `${text}次`
}

function intervalColumnLabel(row: TabularRow, metricKind: string) {
  if (metricKind === 'count') {
    return countIntervalLabel(row.interval_label, row.interval_order)
  }
  return String(row.interval_label ?? '').trim() || String(row.interval_order ?? '').trim()
}

function failedResult(result: TabularResult, message: string) {
  return {
    ...result,
    status: 'failed',
    message,
  }
}

export function shapeDistributionTableResult(result: TabularResult, context: any): TabularResult {
  if (!isDistributionTableContext(context) || result?.status === 'failed') return result

  const fields = resultFields(result)
  if (fields.includes(DISTRIBUTION_DATE_COLUMN) && fields.includes(DISTRIBUTION_TOTAL_COLUMN)) {
    return result
  }
  const missingFields = REQUIRED_DISTRIBUTION_SOURCE_FIELDS.filter((field) => !fields.includes(field))
  if (missingFields.length) {
    if (!Array.isArray(result?.data) || result.data.length === 0) return result
    return failedResult(result, `分布分析结果缺少字段：${missingFields.join('、')}`)
  }

  const sourceFieldSet = new Set<string>(DISTRIBUTION_SOURCE_FIELDS)
  const groupFields = fields.filter((field) => !sourceFieldSet.has(field))
  if (groupFields.includes(DISTRIBUTION_DATE_COLUMN) || groupFields.includes(DISTRIBUTION_TOTAL_COLUMN)) {
    return failedResult(result, '分布分析分组字段与系统展示列重名。')
  }

  const rows = Array.isArray(result?.data) ? result.data : []
  const metricKind = distributionMetricKind(context)
  const rowMap = new Map<string, TabularRow>()
  const rowOrder: string[] = []
  const intervalMap = new Map<string, { label: string; order: number; sequence: number }>()
  const simultaneousEnabled = fields.includes('simultaneous_value')

  for (const row of rows) {
    const intervalLabel = intervalColumnLabel(row, metricKind)
    if (!intervalLabel) {
      return failedResult(result, '分布分析结果存在空的区间标签。')
    }
    const intervalOrder = Number(row?.interval_order)
    if (!intervalMap.has(intervalLabel)) {
      intervalMap.set(intervalLabel, {
        label: intervalLabel,
        order: Number.isFinite(intervalOrder) ? intervalOrder : Number.MAX_SAFE_INTEGER,
        sequence: intervalMap.size,
      })
    }

    const key = groupKey(row, groupFields)
    if (!rowMap.has(key)) {
      const outputRow: TabularRow = {
        [DISTRIBUTION_DATE_COLUMN]: distributionDateValue(row?.distribution_date),
      }
      groupFields.forEach((field) => {
        outputRow[field] = row?.[field]
      })
      outputRow[DISTRIBUTION_TOTAL_COLUMN] = row?.total_entities
      rowMap.set(key, outputRow)
      rowOrder.push(key)
    }

    const outputRow = rowMap.get(key)!
    if (normalizedComparableValue(outputRow[DISTRIBUTION_TOTAL_COLUMN]) !== normalizedComparableValue(row?.total_entities)) {
      return failedResult(result, '同一日期和分组的全部用户数不一致，无法展开分布结果。')
    }
    if (Object.prototype.hasOwnProperty.call(outputRow, intervalLabel)) {
      return failedResult(result, `同一日期和分组的区间“${intervalLabel}”出现多条记录。`)
    }
    outputRow[intervalLabel] = row?.entity_count ?? 0
    if (simultaneousEnabled) {
      outputRow[`${intervalLabel}（同时展示）`] = row?.simultaneous_value ?? 0
    }
  }

  const intervals = Array.from(intervalMap.values()).sort(
    (left, right) => left.order - right.order || left.sequence - right.sequence
  )
  const intervalFields = intervals.flatMap(({ label }) => (
    simultaneousEnabled ? [label, `${label}（同时展示）`] : [label]
  ))
  const outputFields = [
    DISTRIBUTION_DATE_COLUMN,
    ...groupFields,
    DISTRIBUTION_TOTAL_COLUMN,
    ...intervalFields,
  ]
  const outputRows = rowOrder.map((key) => {
    const row = rowMap.get(key)!
    intervalFields.forEach((field) => {
      if (!Object.prototype.hasOwnProperty.call(row, field)) row[field] = 0
    })
    return row
  })

  return {
    ...result,
    fields: outputFields,
    data: outputRows,
  }
}

export function syncDistributionTableColumns(viewInfo: any, fields: string[]) {
  if (!isDistributionTableContext(viewInfo) || !fields.includes(DISTRIBUTION_DATE_COLUMN)) return
  if (!viewInfo.chart || typeof viewInfo.chart !== 'object') viewInfo.chart = {}
  const currentColumns = Array.isArray(viewInfo.chart.columns) ? viewInfo.chart.columns : []
  viewInfo.chart.columns = fields.map((field) => {
    const current = currentColumns.find((item: any) => (item?.value || item?.name) === field)
    return current ? { ...current, value: field } : { value: field }
  })
}

export function normalizeDistributionTableViewInfo(viewInfo: any) {
  if (isDistributionTableContext(viewInfo) && viewInfo?.pivot?.enabled === true) {
    viewInfo.pivot = {
      ...viewInfo.pivot,
      enabled: false,
    }
  }
  if (!viewInfo || typeof viewInfo !== 'object' || !viewInfo.data || typeof viewInfo.data !== 'object') {
    return viewInfo
  }
  const shaped = shapeDistributionTableResult(viewInfo.data, viewInfo)
  if (shaped === viewInfo.data) return viewInfo
  viewInfo.data = {
    ...viewInfo.data,
    fields: Array.isArray(shaped.fields) ? shaped.fields : [],
    data: Array.isArray(shaped.data) ? shaped.data : [],
  }
  viewInfo.fields = [...viewInfo.data.fields]
  viewInfo.status = shaped.status || viewInfo.status
  viewInfo.message = shaped.message || ''
  syncDistributionTableColumns(viewInfo, viewInfo.data.fields)
  return viewInfo
}
