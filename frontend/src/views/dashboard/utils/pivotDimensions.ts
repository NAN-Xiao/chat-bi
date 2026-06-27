import {
  axisLabel,
  axisValue,
  type ChartAxis,
  type ChartData,
} from '@/views/chat/component/BaseChart.ts'

export type PivotDimension = {
  field: string
  label: string
  source?: 'configured' | 'series' | 'field' | 'data'
  confidence?: number
  reason?: string
}

type InferPivotDimensionsOptions = {
  fields?: string[]
  data?: ChartData[]
  chart?: {
    xAxis?: ChartAxis[]
    yAxis?: ChartAxis[]
    series?: ChartAxis[]
    columns?: ChartAxis[]
  }
  timeField?: string
  metricFields?: string[]
  configured?: unknown
}

const DIMENSION_KEYWORDS = [
  'country',
  'region',
  'province',
  'city',
  'state',
  'market',
  'geo',
  'location',
  'area',
  'zone',
  'platform',
  'os',
  'device',
  'device_type',
  'browser',
  'app_version',
  'client_version',
  'channel',
  'campaign',
  'source',
  'medium',
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'referrer',
  'product',
  'category',
  'brand',
  'sku',
  'plan',
  'package',
  'subscription',
  'order_type',
  'payment_method',
  'currency',
  'status',
  'stage',
  'step',
  'funnel',
  'server',
  'workspace',
  'tenant',
  'organization',
  'org',
  'company',
  'customer',
  'customer_type',
  'user_type',
  'member_type',
  'department',
  'dept',
  'team',
  'role',
  'cost_center',
  'account',
  'subject',
  'segment',
  'tier',
  'level',
  'cohort',
  'content_type',
  'author_type',
  'language',
  'locale',
  '国家',
  '國家',
  '地区',
  '地區',
  '省',
  '城市',
  '市场',
  '市場',
  '位置',
  '区域',
  '區域',
  '平台',
  '系统',
  '系統',
  '设备',
  '設備',
  '浏览器',
  '瀏覽器',
  '版本',
  '渠道',
  '活动',
  '活動',
  '来源',
  '來源',
  '媒介',
  '投放',
  '商品',
  '产品',
  '產品',
  '品类',
  '品類',
  '品牌',
  '套餐',
  '订阅',
  '訂閱',
  '订单类型',
  '訂單類型',
  '支付方式',
  '币种',
  '幣種',
  '状态',
  '狀態',
  '阶段',
  '階段',
  '步骤',
  '步驟',
  '服务器',
  '伺服器',
  '区服',
  '區服',
  '组织',
  '組織',
  '公司',
  '客户',
  '客戶',
  '用户类型',
  '用戶類型',
  '会员类型',
  '會員類型',
  '部门',
  '部門',
  '团队',
  '團隊',
  '角色',
  '成本中心',
  '科目',
  '分层',
  '分層',
  '等级',
  '等級',
  '类型',
  '類型',
  '语言',
  '語言',
  '地区语言',
]

const ID_KEYWORDS = [
  'id',
  'uuid',
  'guid',
  'order_no',
  'order_number',
  '订单号',
  '訂單號',
  '编号',
  '編號',
]

function unique(values: Array<string | undefined | null>) {
  return Array.from(
    new Set(
      values
        .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
        .map((value) => `${value}`)
    )
  )
}

export function looksLikePivotDateField(field: string) {
  return looksLikeDateField(field)
}

export function isPivotDateLikeValue(value: unknown) {
  return isDateLikeValue(value)
}

export function isLikelyPivotDateField(field: string, data: ChartData[] = []) {
  if (!field) {
    return false
  }
  const values = sampleValues(data, field)
  if (values.length > 0) {
    return values.filter(isDateLikeValue).length / values.length >= 0.5
  }
  return looksLikeDateField(field)
}

function normalizeField(value: unknown) {
  return String(value || '').trim()
}

function normalizeText(value: unknown) {
  return normalizeField(value).toLowerCase()
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function isAsciiKeyword(value: string) {
  return /^[a-z0-9_\-\s]+$/i.test(value)
}

function axisToDimension(axis?: ChartAxis | null): PivotDimension | null {
  const field = axisValue(axis)
  if (!field) {
    return null
  }
  return {
    field,
    label: axisLabel(axis) || field,
    source: 'series',
    confidence: 100,
    reason: 'chart-series',
  }
}

function configuredDimensions(configured: unknown): PivotDimension[] {
  if (!Array.isArray(configured)) {
    return []
  }
  return configured
    .map((item) => {
      if (typeof item === 'string') {
        const field = normalizeField(item)
        return field
          ? {
              field,
              label: field,
              source: 'configured' as const,
              confidence: 95,
              reason: 'configured',
            }
          : null
      }
      const raw = item as any
      const field = normalizeField(raw.field || raw.value || raw.name)
      const label = normalizeField(raw.label || raw.name || raw.field || raw.value)
      return field
        ? {
            ...raw,
            field,
            label: label || field,
            source: raw.source || 'configured',
            confidence: Number(raw.confidence || 95),
            reason: raw.reason || 'configured',
          }
        : null
    })
    .filter((item): item is PivotDimension => Boolean(item))
}

function looksLikeDateField(field: string) {
  const text = normalizeText(field)
  return (
    /(^|[_\s-])(date|day|dt|time|timestamp|week|month|year)([_\s-]|$)/.test(text) ||
    /日期|时间|時間|年月|月份|年份|星期|周/.test(field)
  )
}

function isDateLikeValue(value: unknown) {
  if (value instanceof Date) {
    return !Number.isNaN(value.getTime())
  }
  if (typeof value !== 'string') {
    return false
  }
  const text = value.trim()
  if (!text || /^-?\d+(\.\d+)?$/.test(text)) {
    return false
  }
  return (
    /^\d{4}[-/]\d{1,2}([-/]\d{1,2})?([ T]\d{1,2}:\d{2}(:\d{2})?)?/.test(text) ||
    /^\d{4}年\d{1,2}月(\d{1,2}日)?/.test(text)
  )
}

function isNumericLikeValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isFinite(value)
  }
  if (typeof value !== 'string') {
    return false
  }
  const text = value.trim().replace(/,/g, '')
  return Boolean(text) && /^-?\d+(\.\d+)?%?$/.test(text)
}

function hasKeyword(field: string, keywords: string[]) {
  const text = normalizeText(field)
  return keywords.some((keyword) => {
    const value = keyword.toLowerCase()
    if (!isAsciiKeyword(value)) {
      return text.includes(value)
    }
    if (/[_\-\s]/.test(value)) {
      return text.includes(value)
    }
    return new RegExp(`(^|[^a-z0-9])${escapeRegExp(value)}([^a-z0-9]|$)`).test(text)
  })
}

function sampleValues(data: ChartData[] = [], field: string) {
  return data
    .slice(0, 100)
    .map((row) => row?.[field])
    .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
}

function dimensionConfidence(field: string, data: ChartData[] = []) {
  if (!field || looksLikeDateField(field) || hasKeyword(field, ID_KEYWORDS)) {
    return 0
  }
  if (hasKeyword(field, DIMENSION_KEYWORDS)) {
    return 88
  }
  const values = sampleValues(data, field)
  if (values.length === 0) {
    return 0
  }
  const dateLikeCount = values.filter(isDateLikeValue).length
  if (dateLikeCount / values.length >= 0.5) {
    return 0
  }
  const numericCount = values.filter(isNumericLikeValue).length
  if (numericCount / values.length >= 0.6) {
    return 0
  }
  const distinctCount = new Set(values.map((value) => `${value}`)).size
  if (distinctCount > 40 && distinctCount / values.length > 0.8) {
    return 0
  }
  if (distinctCount <= 1) {
    return 0
  }
  if (distinctCount <= 12) {
    return 72
  }
  return 58
}

function isLikelyDimensionField(field: string, data: ChartData[] = []) {
  return dimensionConfidence(field, data) > 0
}

function dimensionRank(dimension: PivotDimension) {
  const sourceRank = {
    series: 0,
    configured: 1,
    field: 2,
    data: 3,
  }[dimension.source || 'data']
  return sourceRank * 1000 - Number(dimension.confidence || 0)
}

export function inferPivotDimensions(options: InferPivotDimensionsOptions): PivotDimension[] {
  const chart = options.chart || {}
  const data = options.data || []
  const timeField = normalizeField(options.timeField)
  const metricFields = new Set(unique(options.metricFields || []).map(normalizeField))
  const excluded = new Set([
    timeField,
    ...metricFields,
    ...(chart.yAxis || []).map(axisValue),
  ].filter(Boolean))

  const candidates: PivotDimension[] = [
    ...configuredDimensions(options.configured),
    ...(chart.series || []).map(axisToDimension).filter((item): item is PivotDimension => Boolean(item)),
  ]

  const knownFields = unique([
    ...(options.fields || []),
    ...(chart.columns || []).map(axisValue),
    ...(chart.xAxis || []).map(axisValue),
    ...(chart.series || []).map(axisValue),
    ...data.slice(0, 20).flatMap((row) => Object.keys(row || {})),
  ])
  const knownFieldSet = new Set(knownFields)

  knownFields.forEach((field) => {
    if (!excluded.has(field) && isLikelyDimensionField(field, data)) {
      const confidence = dimensionConfidence(field, data)
      candidates.push({
        field,
        label: field,
        source: options.fields?.includes(field) ? 'field' : 'data',
        confidence,
        reason: hasKeyword(field, DIMENSION_KEYWORDS) ? 'keyword' : 'low-cardinality-text',
      })
    }
  })

  const used = new Set<string>()
  return candidates
    .filter((dimension) => {
      if (
        !dimension.field ||
        excluded.has(dimension.field) ||
        used.has(dimension.field) ||
        (knownFieldSet.size > 0 && !knownFieldSet.has(dimension.field))
      ) {
        return false
      }
      used.add(dimension.field)
      return true
    })
    .sort((a, b) => dimensionRank(a) - dimensionRank(b))
}
