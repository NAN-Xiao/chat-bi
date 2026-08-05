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
const TINY_MIN_HEIGHT = 200
const TOP_BASIC_MAX_WIDTH = 440
const TOP_BASIC_MAX_HEIGHT = 360
const TOP_MINI_MAX_WIDTH = 560
const TOP_MINI_MAX_HEIGHT = 430
const SIDE_MINI_MAX_WIDTH = 760
const SIDE_MINI_MAX_HEIGHT = 330
const SIDE_COMPACT_MAX_WIDTH = 900
const SIDE_COMPACT_MAX_HEIGHT = 390
// 真实外部 resize 会在阈值附近带来相邻帧的轻微尺寸回摆。布局与密度历史在此保留迟滞，
// 其窗口必须大于最大 header 高差（compact↔basic 约 10px），避免一次外部 resize 的回摆
// 立即反向切换档位，导致摘要布局频繁改变。
const DENSITY_HYSTERESIS = 20
const WIDE_TREND_SIDE_MIN_WIDTH = 1100
const WIDE_TREND_SIDE_MIN_HEIGHT = 260
const WIDE_TREND_SIDE_MIN_ASPECT_RATIO = 2.2
const SIDE_MAX_STATS = 8
const SIDE_COMPACT_RESERVED_HEIGHT = 130
const SIDE_COMPACT_STAT_HEIGHT = 76
const TOP_RANKED_REGULAR_MIN_WIDTH = 640
const TOP_RANKED_COMPACT_MIN_WIDTH = 500
const TOP_RANKED_MAX_STATS = 4
const DAY_MS = 24 * 60 * 60 * 1000
const TOP_RICH_SUMMARY_TYPES = new Set<ChartTypes>(['bar', 'column', 'heatmap', 'scatter', 'funnel'])
const INSIGHT_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

function isValidInsightDate(value: string) {
  const match = INSIGHT_DATE_PATTERN.exec(value)
  if (!match) {
    return false
  }
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day
}

export function formatInsightDateRange(range?: [string, string] | null) {
  const start = String(range?.[0] || '').trim()
  const end = String(range?.[1] || '').trim()
  if (!isValidInsightDate(start) || !isValidInsightDate(end) || start > end) {
    return ''
  }
  return start === end ? start : `${start} - ${end}`
}

function axisValues(axes?: Array<ChartAxis>) {
  return (axes || []).map((axis) => axis.value).filter(Boolean)
}

function hasManySeriesGroups(
  data: Array<ChartData> | undefined,
  seriesAxis: ChartAxis | undefined
) {
  if (!seriesAxis) return false
  const groups = new Set(
    (Array.isArray(data) ? data : [])
      .map((row) => row?.[seriesAxis.value])
      .filter((value) => !isBlankValue(value))
      .map(String)
  )
  return groups.size >= 6
}

export function buildInsightLayoutStateKey(params: {
  viewId?: string | number | null
  chartType: ChartTypes
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  dashboard?: boolean
}) {
  return JSON.stringify([
    params.viewId ?? null,
    params.chartType,
    Boolean(params.dashboard),
    axisValues(params.x),
    axisValues(params.y),
    axisValues(params.series),
  ])
}

export function buildInsightDataStructureKey(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  dashboard?: boolean
}) {
  const rows = Array.isArray(params.data) ? params.data : []
  const seriesAxis = params.series?.[0]
  const trendGranularityRelevant =
    params.dashboard === true &&
    ['line', 'area'].includes(params.chartType) &&
    axisValues(params.y).length === 1 &&
    axisValues(params.series).length === 0
  return JSON.stringify([
    rows.length > 0,
    seriesAxis ? hasManySeriesGroups(rows, seriesAxis) : null,
    trendGranularityRelevant ? detectTrendAxisGranularity(rows, params.x?.[0]) : null,
  ])
}

function clampNumber(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function isBelowDensityThreshold(
  value: number,
  threshold: number,
  previousBelow: boolean | undefined
) {
  if (previousBelow === true) {
    return value < threshold + DENSITY_HYSTERESIS
  }
  if (previousBelow === false) {
    return value < threshold - DENSITY_HYSTERESIS
  }
  return value < threshold
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

  if (hasManySeriesGroups(params.data, params.series?.[0])) {
    return 'side'
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
  previousLayout?: InsightLayout
  previousDensity?: InsightDensity
}): InsightDisplayStrategy {
  const preferredLayout = resolveInsightLayout(params)
  const width = params.width || 0
  const height = params.height || 0
  const visibleMetricCount = axisValues(params.y).length
  const trendGranularity = detectTrendAxisGranularity(params.data, params.x?.[0])
  const isRichTopSummary =
    params.dashboard &&
    preferredLayout === 'top' &&
    TOP_RICH_SUMMARY_TYPES.has(params.chartType) &&
    axisValues(params.series).length === 0
  const wideTrendMinHeight =
    params.previousLayout === 'side' ? WIDE_TREND_SIDE_MIN_HEIGHT : SIDE_MIN_HEIGHT
  const isWideSingleMetricTrend =
    params.dashboard &&
    preferredLayout === 'top' &&
    ['line', 'area'].includes(params.chartType) &&
    axisValues(params.y).length === 1 &&
    axisValues(params.series).length === 0 &&
    trendGranularity !== null &&
    width >= WIDE_TREND_SIDE_MIN_WIDTH &&
    height >= wideTrendMinHeight &&
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
    // TOP 分支的密度历史迟滞与 side 分支一致。真实外部 resize 在 430px mini↔compact
    // 等边界附近反复接近时，必须保持当前档位直到越过退出阈值，避免摘要布局频繁切换。
    const wasBasic = params.previousDensity === 'basic'
    const wasMiniOrDenser =
      params.previousDensity === 'basic' || params.previousDensity === 'mini'
    const belowBasicThreshold =
      isBelowDensityThreshold(
        width,
        TOP_BASIC_MAX_WIDTH,
        params.previousDensity ? wasBasic : undefined
      ) ||
      isBelowDensityThreshold(
        height,
        TOP_BASIC_MAX_HEIGHT,
        params.previousDensity ? wasBasic : undefined
      )

    if (isRichTopSummary && width >= TOP_RANKED_COMPACT_MIN_WIDTH) {
      return {
        show: true,
        layout,
        density: belowBasicThreshold
          ? 'basic'
          : width >= TOP_RANKED_REGULAR_MIN_WIDTH
            ? 'regular'
            : 'compact',
        maxStats: TOP_RANKED_MAX_STATS,
        featuredSide: false,
      }
    }

    if (belowBasicThreshold) {
      return {
        show: true,
        layout,
        density: 'basic',
        maxStats: clampNumber(visibleMetricCount || 1, 1, 3),
        featuredSide: false,
      }
    }

    const belowMiniThreshold =
      isBelowDensityThreshold(
        width,
        TOP_MINI_MAX_WIDTH,
        params.previousDensity ? wasMiniOrDenser : undefined
      ) ||
      isBelowDensityThreshold(
        height,
        TOP_MINI_MAX_HEIGHT,
        params.previousDensity ? wasMiniOrDenser : undefined
      )
    if (belowMiniThreshold) {
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

  const wasMini = params.previousDensity === 'mini'
  const useMiniDensity =
    isBelowDensityThreshold(width, SIDE_MINI_MAX_WIDTH, params.previousDensity ? wasMini : undefined) ||
    isBelowDensityThreshold(height, SIDE_MINI_MAX_HEIGHT, params.previousDensity ? wasMini : undefined)
  if (useMiniDensity) {
    return {
      show: true,
      layout,
      density: 'mini',
      maxStats: resolveSideMaxStats(height, 2),
      featuredSide: false,
    }
  }

  const wasCompact = params.previousDensity === 'mini' || params.previousDensity === 'compact'
  const useCompactDensity =
    isBelowDensityThreshold(
      width,
      SIDE_COMPACT_MAX_WIDTH,
      params.previousDensity ? wasCompact : undefined
    ) ||
    isBelowDensityThreshold(
      height,
      SIDE_COMPACT_MAX_HEIGHT,
      params.previousDensity ? wasCompact : undefined
    )
  return {
    show: true,
    layout,
    density: useCompactDensity ? 'compact' : 'regular',
    maxStats: resolveSideMaxStats(height, useCompactDensity ? 3 : 4),
    featuredSide: isWideSingleMetricTrend,
  }
}
