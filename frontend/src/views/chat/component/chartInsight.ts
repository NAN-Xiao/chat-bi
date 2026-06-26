import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'

export type InsightLayout = 'top' | 'side'
export type InsightDensity = 'regular' | 'compact' | 'mini' | 'basic'
export type TrendTimeGranularity = 'day' | 'week' | 'month' | 'year'
export type TrendComparisonMetric = 'day_over_day' | 'week_over_week' | 'month_over_month' | 'year_over_year'
export type TrendAggregateMetric = 'average' | 'sum' | 'max' | 'min'

export interface ParsedTrendDateValue {
  label: string
  time: number
  granularity: TrendTimeGranularity
}

export interface InsightDisplayStrategy {
  show: boolean
  layout: InsightLayout
  density: InsightDensity
  maxStats: number
  featuredSide?: boolean
}

const SIDE_LAYOUT_TYPES = new Set<ChartTypes>(['sankey', 'treemap'])
const WIDE_SIDE_MIN_WIDTH = 680
const SIDE_MIN_HEIGHT = 280
const TINY_MIN_WIDTH = 300
const TINY_MIN_HEIGHT = 250
const TOP_BASIC_MAX_WIDTH = 440
const TOP_BASIC_MAX_HEIGHT = 360
const TOP_MINI_MAX_WIDTH = 560
const TOP_MINI_MAX_HEIGHT = 430
const SIDE_MINI_MAX_WIDTH = 760
const SIDE_MINI_MAX_HEIGHT = 330
const SIDE_COMPACT_MAX_WIDTH = 900
const SIDE_COMPACT_MAX_HEIGHT = 390
const WIDE_TREND_SIDE_MIN_WIDTH = 1100
const WIDE_TREND_SIDE_MIN_ASPECT_RATIO = 2.2
const SIDE_MAX_STATS = 8
const SIDE_COMPACT_RESERVED_HEIGHT = 130
const SIDE_COMPACT_STAT_HEIGHT = 76
const DAY_MS = 24 * 60 * 60 * 1000

function axisValues(axes?: Array<ChartAxis>) {
  return (axes || []).map((axis) => axis.value).filter(Boolean)
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function resolveSideMaxStats(height: number, fallback: number) {
  if (height <= 0) {
    return fallback
  }

  const fitCount = Math.floor(
    (height - SIDE_COMPACT_RESERVED_HEIGHT) / SIDE_COMPACT_STAT_HEIGHT
  )
  return clampNumber(Math.max(fallback, fitCount), 1, SIDE_MAX_STATS)
}

function isBlankValue(value: any) {
  return value === null || value === undefined || value === ''
}

function normalizeTrendDateLabel(date: Date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(
    date.getUTCDate()
  ).padStart(2, '0')}`
}

function parseUtcDate(year: number, month: number, day: number) {
  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null
  }
  return date
}

export function parseTrendDateValue(value: any): ParsedTrendDateValue | null {
  if (isBlankValue(value)) {
    return null
  }

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return {
      label: normalizeTrendDateLabel(value),
      time: Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()),
      granularity: 'day',
    }
  }

  const text = String(value).trim()
  if (!text) {
    return null
  }

  const dateMatch =
    text.match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})/) ||
    text.match(/^(\d{4})(\d{2})(\d{2})$/)
  if (dateMatch) {
    const year = Number(dateMatch[1])
    const month = Number(dateMatch[2])
    const day = Number(dateMatch[3])
    const date = parseUtcDate(year, month, day)
    if (!date) {
      return null
    }
    return {
      label: normalizeTrendDateLabel(date),
      time: date.getTime(),
      granularity: /周|week/i.test(text) ? 'week' : 'day',
    }
  }

  const monthMatch = text.match(/^(\d{4})[-/.年](\d{1,2})(?:月)?$/) || text.match(/^(\d{4})(\d{2})$/)
  if (monthMatch) {
    const year = Number(monthMatch[1])
    const month = Number(monthMatch[2])
    if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
      return null
    }
    return {
      label: `${year}-${String(month).padStart(2, '0')}`,
      time: Date.UTC(year, month - 1, 1),
      granularity: 'month',
    }
  }

  const yearMatch = text.match(/^(\d{4})(?:年)?$/)
  if (yearMatch) {
    const year = Number(yearMatch[1])
    if (!Number.isInteger(year)) {
      return null
    }
    return {
      label: `${year}`,
      time: Date.UTC(year, 0, 1),
      granularity: 'year',
    }
  }

  return null
}

function isConsecutiveTrendDates(dates: ParsedTrendDateValue[], granularity: TrendTimeGranularity) {
  if (dates.length < 2) {
    return false
  }

  for (let index = 1; index < dates.length; index += 1) {
    const current = dates[index]
    const previous = dates[index - 1]
    if (granularity === 'day' && (current.time - previous.time) / DAY_MS !== 1) {
      return false
    }
    if (granularity === 'week' && (current.time - previous.time) / DAY_MS !== 7) {
      return false
    }
    if (granularity === 'month') {
      const currentDate = new Date(current.time)
      const previousDate = new Date(previous.time)
      const monthGap =
        (currentDate.getUTCFullYear() - previousDate.getUTCFullYear()) * 12 +
        (currentDate.getUTCMonth() - previousDate.getUTCMonth())
      if (monthGap !== 1) {
        return false
      }
    }
    if (granularity === 'year') {
      const currentDate = new Date(current.time)
      const previousDate = new Date(previous.time)
      if (currentDate.getUTCFullYear() - previousDate.getUTCFullYear() !== 1) {
        return false
      }
    }
  }

  return true
}

export function detectTrendAxisGranularity(
  data?: Array<ChartData>,
  axis?: ChartAxis | string | null
): TrendTimeGranularity | null {
  const rows = Array.isArray(data) ? data : []
  const axisValue = typeof axis === 'string' ? axis : axis?.value
  if (!axisValue || rows.length === 0) {
    return null
  }

  const rawValues = rows
    .map((row) => row?.[axisValue])
    .filter((value) => !isBlankValue(value))
  if (rawValues.length === 0) {
    return null
  }

  const parsedValues = rawValues.map(parseTrendDateValue).filter((value): value is ParsedTrendDateValue => value !== null)
  if (parsedValues.length / rawValues.length < 0.5) {
    return null
  }

  const granularities: TrendTimeGranularity[] = ['day', 'week', 'month', 'year']
  for (const granularity of granularities) {
    const dates = Array.from(
      new Map(
        parsedValues
          .filter((value) => value.granularity === granularity)
          .map((value) => [value.label, value])
      ).values()
    ).sort((a, b) => a.time - b.time)
    if (dates.length >= 2 && isConsecutiveTrendDates(dates, granularity)) {
      return granularity
    }
  }

  return null
}

export function availableTrendComparisonMetrics(granularity: TrendTimeGranularity | null): TrendComparisonMetric[] {
  if (granularity === 'day') {
    return ['day_over_day', 'week_over_week']
  }
  if (granularity === 'week') {
    return ['week_over_week']
  }
  if (granularity === 'month') {
    return ['month_over_month', 'year_over_year']
  }
  if (granularity === 'year') {
    return ['year_over_year']
  }
  return []
}

export function defaultTrendComparisonMetrics(granularity: TrendTimeGranularity | null): TrendComparisonMetric[] {
  return availableTrendComparisonMetrics(granularity)
}

export function buildInsightColumns(
  data?: Array<ChartData>,
  knownAxes: Array<ChartAxis | undefined> = []
): Array<ChartAxis> {
  const rows = Array.isArray(data) ? data : []
  const knownValues = new Set(
    knownAxes.flatMap((axis) => (axis?.value ? [axis.value] : []))
  )
  const fields = new Set<string>()

  rows.slice(0, 20).forEach((row) => {
    Object.keys(row || {}).forEach((field) => {
      if (!knownValues.has(field)) {
        fields.add(field)
      }
    })
  })

  return Array.from(fields).map((field) => ({ name: field, value: field }))
}

export function resolveInsightLayout(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
}): InsightLayout {
  if (SIDE_LAYOUT_TYPES.has(params.chartType)) {
    return 'side'
  }

  const seriesAxis = params.series?.[0]
  const data = Array.isArray(params.data) ? params.data : []
  if (seriesAxis) {
    const groups = new Set(
      data
        .map((row) => row?.[seriesAxis.value])
        .filter((value) => value !== undefined && value !== null && value !== '')
        .map(String)
    )
    if (groups.size >= 6) {
      return 'side'
    }
  }

  const yValues = axisValues(params.y)
  if (yValues.length >= 4 && ['line', 'area', 'column', 'bar'].includes(params.chartType)) {
    return 'side'
  }

  return 'top'
}

export function resolveInsightDisplay(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  width?: number
  height?: number
  dashboard?: boolean
}): InsightDisplayStrategy {
  const preferredLayout = resolveInsightLayout(params)
  const width = params.width || 0
  const height = params.height || 0
  const visibleMetricCount = axisValues(params.y).length
  const trendGranularity = detectTrendAxisGranularity(params.data, params.x?.[0])
  const isWideSingleMetricTrend =
    params.dashboard &&
    preferredLayout === 'top' &&
    ['line', 'area'].includes(params.chartType) &&
    axisValues(params.y).length === 1 &&
    axisValues(params.series).length === 0 &&
    trendGranularity !== null &&
    width >= WIDE_TREND_SIDE_MIN_WIDTH &&
    height >= SIDE_MIN_HEIGHT &&
    width / Math.max(height, 1) >= WIDE_TREND_SIDE_MIN_ASPECT_RATIO

  if (!params.dashboard || width <= 0 || height <= 0) {
    return {
      show: true,
      layout: preferredLayout,
      density: params.dashboard ? 'compact' : 'regular',
      maxStats: preferredLayout === 'side' ? 4 : 3,
      featuredSide: false,
    }
  }

  const sideAllowed =
    (preferredLayout === 'side' && width >= WIDE_SIDE_MIN_WIDTH && height >= SIDE_MIN_HEIGHT) ||
    isWideSingleMetricTrend
  const layout: InsightLayout = sideAllowed ? 'side' : 'top'

  if (width < TINY_MIN_WIDTH || height < TINY_MIN_HEIGHT) {
    return {
      show: false,
      layout,
      density: 'basic',
      maxStats: 0,
      featuredSide: false,
    }
  }

  if (layout === 'top') {
    if (width < TOP_BASIC_MAX_WIDTH || height < TOP_BASIC_MAX_HEIGHT) {
      return {
        show: true,
        layout,
        density: 'basic',
        maxStats: clampNumber(visibleMetricCount || 1, 1, 3),
        featuredSide: false,
      }
    }

    if (width < TOP_MINI_MAX_WIDTH || height < TOP_MINI_MAX_HEIGHT) {
      return {
        show: true,
        layout,
        density: 'mini',
        maxStats: clampNumber(Math.max(2, visibleMetricCount), 2, 3),
        featuredSide: false,
      }
    }

    return {
      show: true,
      layout,
      density: 'compact',
      maxStats: 3,
      featuredSide: false,
    }
  }

  if (width < SIDE_MINI_MAX_WIDTH || height < SIDE_MINI_MAX_HEIGHT) {
    return {
      show: true,
      layout,
      density: 'mini',
      maxStats: resolveSideMaxStats(height, 2),
      featuredSide: false,
    }
  }

  return {
    show: true,
    layout,
    density: width < SIDE_COMPACT_MAX_WIDTH || height < SIDE_COMPACT_MAX_HEIGHT ? 'compact' : 'regular',
    maxStats: resolveSideMaxStats(
      height,
      width < SIDE_COMPACT_MAX_WIDTH || height < SIDE_COMPACT_MAX_HEIGHT ? 3 : 4
    ),
    featuredSide: isWideSingleMetricTrend,
  }
}
