import dayjs, { type Dayjs } from 'dayjs'
import customParseFormat from 'dayjs/plugin/customParseFormat'
import timezonePlugin from 'dayjs/plugin/timezone'
import utc from 'dayjs/plugin/utc'

dayjs.extend(customParseFormat)
dayjs.extend(utc)
dayjs.extend(timezonePlugin)

export const ALL_TIME_START = '1000-01-01'
export const ALL_TIME_END = '9999-12-31'
export const DASHBOARD_DATE_PRESETS = [
  'yesterday',
  'today',
  'previous_week',
  'current_week',
  'previous_month',
  'current_month',
  'past_7_days',
  'recent_7_days',
  'past_30_days',
  'recent_30_days',
  'past_90_days',
  'all_time',
] as const

export type DashboardDatePreset = (typeof DASHBOARD_DATE_PRESETS)[number]
export type DashboardDateEndpoint =
  | { mode: 'dynamic'; unit: 'day'; offset: number }
  | { mode: 'static'; date: string }
export type DashboardDateExpression =
  | { version: 1; mode: 'preset'; preset: DashboardDatePreset }
  | {
      version: 1
      mode: 'range'
      start: DashboardDateEndpoint
      end: DashboardDateEndpoint
    }
export type DashboardResolvedDateRange = { start: string; end: string }
export type DashboardDateExpressionCalendarRange = [string, string] | []
export type DashboardDateExpressionValidation = { valid: boolean; message: string }

export function defaultDashboardDateExpression(): DashboardDateExpression {
  return {
    version: 1,
    mode: 'preset',
    preset: 'past_7_days',
  }
}

export const DASHBOARD_DATE_PRESET_LABELS: Record<DashboardDatePreset, string> = {
  yesterday: '昨日',
  today: '今日',
  previous_week: '上周',
  current_week: '本周',
  previous_month: '上月',
  current_month: '本月',
  past_7_days: '过去7天',
  recent_7_days: '最近7天',
  past_30_days: '过去30天',
  recent_30_days: '最近30天',
  past_90_days: '过去90天',
  all_time: '全部时间',
}

const isoDatePattern = /^\d{4}-\d{2}-\d{2}$/

function isIsoDate(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    isoDatePattern.test(value) &&
    dayjs(value, 'YYYY-MM-DD', true).format('YYYY-MM-DD') === value
  )
}

function monday(value: Dayjs) {
  return value.subtract((value.day() + 6) % 7, 'day').startOf('day')
}

function textDate(value: Dayjs) {
  return value.format('YYYY-MM-DD')
}

function normalizeEndpoint(value: unknown): DashboardDateEndpoint | null {
  if (!value || typeof value !== 'object') return null
  const endpoint = value as Record<string, unknown>
  if (endpoint.mode === 'static' && isIsoDate(endpoint.date)) {
    return { mode: 'static', date: endpoint.date }
  }
  if (
    endpoint.mode === 'dynamic' &&
    endpoint.unit === 'day' &&
    typeof endpoint.offset === 'number' &&
    Number.isInteger(endpoint.offset) &&
    endpoint.offset <= 0
  ) {
    return { mode: 'dynamic', unit: 'day', offset: endpoint.offset }
  }
  return null
}

export function cloneDashboardDateExpression(
  value: DashboardDateExpression
): DashboardDateExpression {
  return JSON.parse(JSON.stringify(value)) as DashboardDateExpression
}

export function normalizeDashboardDateExpression(
  value: unknown
): DashboardDateExpression | null {
  if (!value || typeof value !== 'object') return null
  const expression = value as Record<string, unknown>
  if (expression.version !== 1) return null
  if (
    expression.mode === 'preset' &&
    DASHBOARD_DATE_PRESETS.includes(expression.preset as DashboardDatePreset)
  ) {
    return {
      version: 1,
      mode: 'preset',
      preset: expression.preset as DashboardDatePreset,
    }
  }
  if (expression.mode !== 'range') return null
  const start = normalizeEndpoint(expression.start)
  const end = normalizeEndpoint(expression.end)
  return start && end ? { version: 1, mode: 'range', start, end } : null
}

export function resolveDashboardDateExpression(
  value: DashboardDateExpression,
  now: string | Date,
  timezone: string
): DashboardResolvedDateRange {
  const today = dayjs(now).tz(timezone).startOf('day')
  if (value.mode === 'range') {
    const resolveEndpoint = (endpoint: DashboardDateEndpoint) =>
      endpoint.mode === 'static' ? endpoint.date : textDate(today.add(endpoint.offset, 'day'))
    return {
      start: resolveEndpoint(value.start),
      end: resolveEndpoint(value.end),
    }
  }

  const weekStart = monday(today)
  const previousMonth = today.subtract(1, 'month')
  const ranges: Record<DashboardDatePreset, DashboardResolvedDateRange> = {
    yesterday: {
      start: textDate(today.subtract(1, 'day')),
      end: textDate(today.subtract(1, 'day')),
    },
    today: { start: textDate(today), end: textDate(today) },
    previous_week: {
      start: textDate(weekStart.subtract(7, 'day')),
      end: textDate(weekStart.subtract(1, 'day')),
    },
    current_week: { start: textDate(weekStart), end: textDate(today) },
    previous_month: {
      start: textDate(previousMonth.startOf('month')),
      end: textDate(previousMonth.endOf('month')),
    },
    current_month: { start: textDate(today.startOf('month')), end: textDate(today) },
    past_7_days: {
      start: textDate(today.subtract(7, 'day')),
      end: textDate(today.subtract(1, 'day')),
    },
    recent_7_days: { start: textDate(today.subtract(6, 'day')), end: textDate(today) },
    past_30_days: {
      start: textDate(today.subtract(30, 'day')),
      end: textDate(today.subtract(1, 'day')),
    },
    recent_30_days: { start: textDate(today.subtract(29, 'day')), end: textDate(today) },
    past_90_days: {
      start: textDate(today.subtract(90, 'day')),
      end: textDate(today.subtract(1, 'day')),
    },
    all_time: { start: ALL_TIME_START, end: ALL_TIME_END },
  }
  return ranges[value.preset]
}

export function dashboardDateExpressionCalendarRange(
  value: DashboardDateExpression,
  now: string | Date,
  timezone: string
): DashboardDateExpressionCalendarRange {
  if (value.mode === 'preset' && value.preset === 'all_time') return []
  const range = resolveDashboardDateExpression(value, now, timezone)
  return [range.start, range.end]
}

export function buildDashboardDateExpressionFromCalendarRange(
  value: unknown
): DashboardDateExpression | null {
  if (!Array.isArray(value) || value.length !== 2) return null
  const [start, end] = value
  if (!isIsoDate(start) || !isIsoDate(end) || start > end) return null
  return {
    version: 1,
    mode: 'range',
    start: { mode: 'static', date: start },
    end: { mode: 'static', date: end },
  }
}

export function validateDashboardDateExpression(
  value: unknown,
  now: string | Date,
  timezone: string
): DashboardDateExpressionValidation {
  const normalized = normalizeDashboardDateExpression(value)
  if (!normalized) return { valid: false, message: '日期表达式配置无效' }
  const range = resolveDashboardDateExpression(normalized, now, timezone)
  return range.start <= range.end
    ? { valid: true, message: '' }
    : { valid: false, message: '开始日期不能晚于结束日期' }
}

export function formatDashboardDateExpression(value: DashboardDateExpression) {
  if (value.mode === 'preset') return DASHBOARD_DATE_PRESET_LABELS[value.preset]
  const formatEndpoint = (endpoint: DashboardDateEndpoint) => {
    if (endpoint.mode === 'static') return endpoint.date
    if (endpoint.offset === 0) return '今日'
    return endpoint.offset < 0 ? `${Math.abs(endpoint.offset)}天前` : `${endpoint.offset}天后`
  }
  return `${formatEndpoint(value.start)} 至 ${formatEndpoint(value.end)}`
}
