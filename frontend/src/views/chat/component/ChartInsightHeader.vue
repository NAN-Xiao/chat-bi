<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  formatNumber,
  isAverageAxis,
  isPercentAxis,
  toNullableNumber,
} from '@/views/chat/component/charts/utils.ts'
import { chartPalette } from '@/views/chat/component/charts/theme.ts'
import {
  availableTrendComparisonMetrics,
  defaultTrendComparisonMetrics,
  detectTrendAxisGranularity,
  parseTrendDateValue,
  type InsightDensity,
  type ParsedTrendDateValue,
  type TrendAggregateMetric,
  type TrendComparisonMetric,
  type TrendTimeGranularity,
} from '@/views/chat/component/chartInsight.ts'

type InsightLayout = 'top' | 'side'
type StatTone = 'positive' | 'negative' | 'neutral'

interface TrendInsightConfig {
  enabled?: boolean
  comparison?: {
    enabled?: boolean
    metrics?: TrendComparisonMetric[]
  }
  aggregate?: {
    enabled?: boolean
    metrics?: TrendAggregateMetric[]
  }
}

const props = withDefaults(
  defineProps<{
    chartType: ChartTypes
    data?: Array<ChartData>
    x?: Array<ChartAxis>
    y?: Array<ChartAxis>
    series?: Array<ChartAxis>
    columns?: Array<ChartAxis>
    sql?: string
    compact?: boolean
    maxStats?: number
    layout?: InsightLayout
    density?: InsightDensity
    insight?: TrendInsightConfig
    featuredSide?: boolean
  }>(),
  {
    data: () => [],
    x: () => [],
    y: () => [],
    series: () => [],
    columns: () => [],
    sql: '',
    compact: false,
    maxStats: 4,
    layout: 'top',
    density: 'regular',
    featuredSide: false,
  }
)

const { t, locale } = useI18n()

interface StatItem {
  label: string
  value: string
  subLabel?: string
  meta?: string
  color: string
  tone?: StatTone
  group?: 'comparison' | 'aggregate'
}

interface ConfiguredTrendSummary {
  anchorLabel: string
  latestValue: string
  comparisonStats: StatItem[]
  aggregateStats: StatItem[]
}

const structureChartTypes = new Set<ChartTypes>(['pie', 'funnel', 'treemap'])
const rankedChartTypes = new Set<ChartTypes>(['bar', 'column', 'heatmap', 'scatter', 'sankey'])
const trendChartTypes = new Set<ChartTypes>(['line', 'area'])

const isBlank = (value: any) => value === null || value === undefined || value === ''
const genericAxisLabels = new Set([
  'x',
  'y',
  'series',
  'category',
  'value',
  'name',
  'type',
  'metric',
])

const stringifyValue = (value: any) => {
  if (isBlank(value)) {
    return ''
  }
  return String(value)
}

const normalizeAxes = (axes?: Array<ChartAxis>) => (axes || []).filter((axis) => !axis.hidden)

function cleanAxisLabel(value?: string) {
  const rawLabel = String(value || '').trim()
  if (/^[a-z][a-z0-9_]*$/.test(rawLabel)) {
    return ''
  }

  const label = rawLabel
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^(x|y|series)\s+/i, '')
    .trim()
  return label && !genericAxisLabels.has(label.toLowerCase()) ? label : ''
}

function displayAxisName(axis?: ChartAxis) {
  return cleanAxisLabel(axis?.name) || cleanAxisLabel(axis?.value)
}

const valueAxes = computed(() => normalizeAxes(props.y))
const xAxis = computed(() => normalizeAxes(props.x)[0])
const seriesAxis = computed(() => normalizeAxes(props.series)[0])
const rows = computed(() => (Array.isArray(props.data) ? props.data : []))

const shouldShow = computed(() => {
  return (
    props.insight?.enabled !== false &&
    props.chartType !== 'table' &&
    props.chartType !== 'metric' &&
    rows.value.length > 0 &&
    valueAxes.value.length > 0
  )
})

function numericValue(row: ChartData, axis: ChartAxis): number | null {
  return toNullableNumber(row?.[axis.value])
}

function formatChartValue(value: any, axis: ChartAxis) {
  if (isBlank(value)) {
    return '-'
  }

  if (typeof value === 'string' && value.trim().endsWith('%')) {
    return value.trim()
  }

  const currentValue = toNullableNumber(value)
  if (currentValue === null) {
    return String(value)
  }

  const isPercent = isPercentAxis(axis, rows.value)
  const displayValue = isPercent && Math.abs(currentValue) <= 1 ? currentValue * 100 : currentValue
  return `${formatNumberForInsight(displayValue)}${isPercent ? '%' : ''}`
}

function formatNumberForInsight(value: number) {
  const precision = Math.abs(value) >= 100 ? 0 : 2
  const rounded = Number(value.toFixed(precision))
  return formatNumber(rounded)
}

function formatPercent(value: number) {
  return `${formatNumber(Number(value.toFixed(2)))}%`
}

function formatSignedPercent(value: number) {
  const normalized = Math.abs(value) < 0.005 ? 0 : Number(value.toFixed(2))
  const prefix = normalized > 0 ? '+' : ''
  return `${prefix}${formatNumber(normalized)}%`
}

function changeMeta(current: number | null, previous: number | null) {
  return relativeChangeMeta(current, previous, 'chat.insight_change')
}

function relativeChangeMeta(current: number | null, previous: number | null, key: string) {
  if (current === null || previous === null || previous === 0) {
    return undefined
  }

  const change = ((current - previous) / Math.abs(previous)) * 100
  const tone: StatTone = change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral'
  return {
    text: t(key, [formatSignedPercent(change)]),
    tone,
  }
}

function isDateLikeValue(value: any) {
  if (isBlank(value)) {
    return false
  }
  const text = String(value).trim()
  return (
    /^\d{4}[-/]\d{1,2}[-/]\d{1,2}/.test(text) ||
    /^\d{4}[-/]\d{1,2}$/.test(text) ||
    /^\d{1,2}[-/]\d{1,2}$/.test(text)
  )
}

function parseDateForRange(value: any) {
  if (isBlank(value)) {
    return null
  }

  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return {
      label: `${year}-${month}-${day}`,
      time: Date.UTC(year, value.getMonth(), value.getDate()),
    }
  }

  const text = String(value).trim()
  const dateMatch =
    text.match(/^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})/) ||
    text.match(/^(\d{4})(\d{2})(\d{2})$/)

  if (!dateMatch) {
    return null
  }

  const year = Number(dateMatch[1])
  const month = Number(dateMatch[2])
  const day = Number(dateMatch[3])
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31
  ) {
    return null
  }

  const date = new Date(Date.UTC(year, month - 1, day))
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null
  }

  return {
    label: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    time: date.getTime(),
  }
}

function addDays(date: { time: number }, days: number) {
  const next = new Date(date.time + days * 24 * 60 * 60 * 1000)
  return {
    label: `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, '0')}-${String(
      next.getUTCDate()
    ).padStart(2, '0')}`,
    time: next.getTime(),
  }
}

function dateKey(date: { time: number }) {
  const value = new Date(date.time)
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-${String(
    value.getUTCDate()
  ).padStart(2, '0')}`
}

function addMonths(date: { time: number }, months: number) {
  const current = new Date(date.time)
  const next = new Date(Date.UTC(current.getUTCFullYear(), current.getUTCMonth() + months, current.getUTCDate()))
  if (next.getUTCDate() !== current.getUTCDate()) {
    return null
  }
  return {
    label: dateKey({ time: next.getTime() }),
    time: next.getTime(),
  }
}

function addYears(date: { time: number }, years: number) {
  const current = new Date(date.time)
  const next = new Date(Date.UTC(current.getUTCFullYear() + years, current.getUTCMonth(), current.getUTCDate()))
  if (next.getUTCMonth() !== current.getUTCMonth() || next.getUTCDate() !== current.getUTCDate()) {
    return null
  }
  return {
    label: dateKey({ time: next.getTime() }),
    time: next.getTime(),
  }
}

function compareTargetDate(date: { time: number }, metric: TrendComparisonMetric) {
  if (metric === 'day_over_day') {
    return addDays(date, -1)
  }
  if (metric === 'week_over_week') {
    return addDays(date, -7)
  }
  if (metric === 'month_over_month') {
    return addMonths(date, -1)
  }
  return addYears(date, -1)
}

const insightLabelFallbacks = {
  'zh-CN': {
    day_over_day: '日环比',
    week_over_week: '周环比',
    week_same_period: '周同比',
    month_over_month: '月环比',
    year_over_year: '年同比',
    average: '阶段均值',
    sum: '阶段总和',
    max: '最大值',
    min: '最小值',
  },
  'zh-TW': {
    day_over_day: '日環比',
    week_over_week: '週環比',
    week_same_period: '週同比',
    month_over_month: '月環比',
    year_over_year: '年同比',
    average: '階段均值',
    sum: '階段總和',
    max: '最大值',
    min: '最小值',
  },
  en: {
    day_over_day: 'Day-over-day',
    week_over_week: 'Week-over-week',
    week_same_period: 'Same day last week',
    month_over_month: 'Month-over-month',
    year_over_year: 'Year-over-year',
    average: 'Period Average',
    sum: 'Period Sum',
    max: 'Maximum',
    min: 'Minimum',
  },
  'ko-KR': {
    day_over_day: '전일 대비',
    week_over_week: '전주 대비',
    week_same_period: '지난주 동일 요일 대비',
    month_over_month: '전월 대비',
    year_over_year: '전년 대비',
    average: '기간 평균',
    sum: '기간 합계',
    max: '최댓값',
    min: '최솟값',
  },
} as const

function insightText(chatKey: string, dashboardKey?: string, fallbackKey?: keyof (typeof insightLabelFallbacks)['zh-CN']) {
  const value = t(chatKey)
  if (value !== chatKey) {
    return value
  }
  if (dashboardKey) {
    const dashboardValue = t(dashboardKey)
    if (dashboardValue !== dashboardKey) {
      return dashboardValue
    }
  }
  const localeKey = String(locale.value || 'zh-CN')
  const localizedFallback =
    insightLabelFallbacks[localeKey as keyof typeof insightLabelFallbacks] || insightLabelFallbacks['zh-CN']
  return fallbackKey ? localizedFallback[fallbackKey] : value
}

function comparisonLabel(metric: TrendComparisonMetric, granularity: TrendTimeGranularity | null) {
  if (metric === 'week_over_week' && granularity === 'day') {
    return insightText('chat.insight_week_same_period', 'dashboard.insight_week_same_period', 'week_same_period')
  }
  if (metric === 'day_over_day') {
    return insightText('chat.insight_day_over_day', 'dashboard.insight_day_over_day', 'day_over_day')
  }
  if (metric === 'week_over_week') {
    return insightText('chat.insight_week_over_week', 'dashboard.insight_week_over_week', 'week_over_week')
  }
  if (metric === 'month_over_month') {
    return insightText('chat.insight_month_over_month', 'dashboard.insight_month_over_month', 'month_over_month')
  }
  return insightText('chat.insight_year_over_year', 'dashboard.insight_year_over_year', 'year_over_year')
}

function aggregateLabel(metric: TrendAggregateMetric) {
  const labels: Record<TrendAggregateMetric, string> = {
    average: insightText('chat.insight_period_average', 'dashboard.insight_period_average', 'average'),
    sum: insightText('chat.insight_period_sum', 'dashboard.insight_period_sum', 'sum'),
    max: insightText('chat.insight_peak', 'dashboard.insight_peak', 'max'),
    min: insightText('chat.insight_lowest', 'dashboard.insight_lowest', 'min'),
  }
  return labels[metric]
}

function trendPointSubLabel(point: { row: ChartData; index: number; date?: { label: string } }) {
  return point.date?.label || pointLabel(point.row, point.index)
}

function extractSqlDates(sql?: string) {
  const text = String(sql || '')
  if (!text) {
    return []
  }
  const matches = Array.from(
    text.matchAll(/(?:date\s*)?['"](\d{4}[-/.]\d{1,2}[-/.]\d{1,2})['"]/gi)
  )
  const dates = matches
    .map((match) => parseDateForRange(match[1]))
    .filter((item): item is { label: string; time: number } => item !== null)
  const seen = new Set<string>()
  return dates.filter((date) => {
    if (seen.has(date.label)) {
      return false
    }
    seen.add(date.label)
    return true
  })
}

function dateFieldPriority(field: string) {
  const text = field.toLowerCase()
  if (/cohort|首日|注册|註冊|signup|install/.test(text)) {
    return 1
  }
  if (/date|time|day|日期|时间|時間/.test(text)) {
    return 2
  }
  return 0
}

const isTrendLike = computed(() => {
  if (trendChartTypes.has(props.chartType)) {
    return true
  }
  const axis = xAxis.value
  if (!axis) {
    return false
  }
  const values = rows.value.map((row) => row[axis.value]).filter((value) => !isBlank(value))
  if (values.length === 0) {
    return false
  }
  const dateLikeCount = values.filter(isDateLikeValue).length
  return dateLikeCount / values.length >= 0.5
})

const latestAnchorValue = computed(() => {
  const axis = xAxis.value
  if (!axis || rows.value.length === 0) {
    return undefined
  }
  const values = rows.value.map((row) => row[axis.value]).filter((value) => !isBlank(value))
  return values[values.length - 1]
})

const latestRows = computed(() => {
  if (rows.value.length === 0) {
    return []
  }
  const axis = xAxis.value
  const anchorValue = latestAnchorValue.value
  if (!axis || isBlank(anchorValue)) {
    return [rows.value[rows.value.length - 1]]
  }
  const filteredRows = rows.value.filter((row) => row[axis.value] === anchorValue)
  return filteredRows.length > 0 ? filteredRows : [rows.value[rows.value.length - 1]]
})

function previousRowFor(row: ChartData, axis: ChartAxis) {
  const rowIndex = rows.value.indexOf(row)
  if (rowIndex <= 0) {
    return undefined
  }

  const currentSeries = seriesAxis.value ? row[seriesAxis.value.value] : undefined
  for (let index = rowIndex - 1; index >= 0; index -= 1) {
    const candidate = rows.value[index]
    if (seriesAxis.value && candidate[seriesAxis.value.value] !== currentSeries) {
      continue
    }
    if (numericValue(candidate, axis) !== null) {
      return candidate
    }
  }
  return undefined
}

function categoryLabel(row: ChartData, index: number) {
  if (props.chartType === 'sankey' && xAxis.value && seriesAxis.value) {
    const source = stringifyValue(row[xAxis.value.value]) || '-'
    const target = stringifyValue(row[seriesAxis.value.value]) || '-'
    return `${source} -> ${target}`
  }

  if (props.chartType === 'heatmap' && xAxis.value && seriesAxis.value) {
    const xValue = stringifyValue(row[xAxis.value.value]) || '-'
    const yValue = stringifyValue(row[seriesAxis.value.value]) || '-'
    return `${yValue} / ${xValue}`
  }

  const axis = props.chartType === 'pie' ? seriesAxis.value || xAxis.value : xAxis.value || seriesAxis.value
  return axis ? stringifyValue(row[axis.value]) || `${index + 1}` : `${index + 1}`
}

function isDayAxis(axis?: ChartAxis) {
  const axisText = `${axis?.name || ''} ${axis?.value || ''}`.toLowerCase()
  if (/date|日期|dt\b/.test(axisText)) {
    return false
  }
  return /(^|[_\s-])(day|days)([_\s-]|$)|天/.test(axisText)
}

function pointLabel(row: ChartData, index: number) {
  const axis = xAxis.value
  if (!axis) {
    return t('chat.insight_point_label', [index + 1])
  }

  return periodPointLabel(row[axis.value], axis, index)
}

function periodPointLabel(value: any, axis?: ChartAxis, index = 0) {
  const rawValue = stringifyValue(value)
  if (!rawValue) {
    return t('chat.insight_point_label', [index + 1])
  }

  if (isDateLikeValue(rawValue)) {
    return rawValue
  }

  if (/^-?\d+$/.test(rawValue) && isDayAxis(axis)) {
    return t('chat.insight_day_label', [rawValue])
  }

  const axisDisplayName = displayAxisName(axis)
  if (axisDisplayName) {
    return `${axisDisplayName} ${rawValue}`
  }

  return t('chat.insight_point_label', [rawValue])
}

function numericAxisRange(axis?: ChartAxis) {
  if (!axis) {
    return null
  }
  const values = rows.value
    .map((row) => toNullableNumber(row?.[axis.value]))
    .filter((value): value is number => value !== null)
  if (values.length === 0) {
    return null
  }
  return {
    min: Math.min(...values),
    max: Math.max(...values),
  }
}

function buildLatestStats(): Array<StatItem> {
  const axis = valueAxes.value[0]
  if (!axis) {
    return []
  }
  const axisDisplayName = displayAxisName(axis)

  if (seriesAxis.value) {
    const seen = new Set<string>()
    const stats: Array<StatItem> = []
    latestRows.value.forEach((row) => {
      const label = stringifyValue(row[seriesAxis.value!.value]) || displayAxisName(seriesAxis.value)
      if (!label || seen.has(label)) {
        return
      }
      seen.add(label)
      const previous = previousRowFor(row, axis)
      const meta = changeMeta(numericValue(row, axis), previous ? numericValue(previous, axis) : null)
      stats.push({
        label,
        value: formatChartValue(row[axis.value], axis),
        subLabel: axisDisplayName,
        meta: meta?.text,
        tone: meta?.tone,
        color: chartPalette[stats.length % chartPalette.length],
      })
    })
    return stats.slice(0, props.maxStats)
  }

  const latestRow = latestRows.value[0] || {}
  const previousRow = rows.value.length > 1 ? rows.value[rows.value.length - 2] : undefined
  return valueAxes.value.slice(0, props.maxStats).map((item, index) => {
    const label = displayAxisName(item)
    const meta = changeMeta(
      numericValue(latestRow, item),
      previousRow ? numericValue(previousRow, item) : null
    )
    return {
      label: label || '',
      value: formatChartValue(latestRow[item.value], item),
      meta: meta?.text,
      tone: meta?.tone,
      color: chartPalette[index % chartPalette.length],
    }
  })
}

function buildTrendSeriesStats(axis: ChartAxis): Array<StatItem> {
  if (!seriesAxis.value) {
    return []
  }

  const seen = new Set<string>()
  const stats: Array<StatItem & { rawValue: number }> = []
  latestRows.value.forEach((row) => {
    const currentValue = numericValue(row, axis)
    const label = stringifyValue(row[seriesAxis.value!.value]) || displayAxisName(seriesAxis.value)
    if (!label || seen.has(label) || currentValue === null) {
      return
    }
    seen.add(label)
    const previous = previousRowFor(row, axis)
    const meta = changeMeta(currentValue, previous ? numericValue(previous, axis) : null)
    stats.push({
      label,
      value: formatChartValue(row[axis.value], axis),
      subLabel: pointLabel(row, rows.value.indexOf(row)),
      meta: meta?.text,
      tone: meta?.tone,
      color: chartPalette[stats.length % chartPalette.length],
      rawValue: currentValue,
    })
  })

  return stats
    .sort((a, b) => b.rawValue - a.rawValue)
    .slice(0, props.maxStats)
    .map(({ rawValue, ...item }) => item)
}

function buildConfiguredTrendSummary(
  metricAxis: ChartAxis,
  points: Array<{ row: ChartData; index: number; value: number }>
): ConfiguredTrendSummary | null {
  const timeAxis = xAxis.value
  if (!timeAxis) {
    return null
  }

  const granularity = detectTrendAxisGranularity(rows.value, timeAxis)
  if (!granularity) {
    return null
  }

  const datedPoints = points
    .map((point) => ({
      ...point,
      date: parseTrendDateValue(point.row[timeAxis.value]),
    }))
    .filter(
      (
        point
      ): point is { row: ChartData; index: number; value: number; date: ParsedTrendDateValue } =>
        point.date !== null && point.date.granularity === granularity
    )
  if (datedPoints.length === 0) {
    return null
  }

  const sortedDatedPoints = [...datedPoints].sort((a, b) => a.date.time - b.date.time)
  const latestPoint = sortedDatedPoints[sortedDatedPoints.length - 1]
  const aggregatePoints = sortedDatedPoints
  const percentOrAverageMetric = isPercentAxis(metricAxis, rows.value) || isAverageAxis(metricAxis)
  const comparisonStats: Array<StatItem> = []
  const aggregateStats: Array<StatItem> = []
  const availableComparisonMetrics = availableTrendComparisonMetrics(granularity)
  const defaultComparisonSelections = defaultTrendComparisonMetrics(granularity)
  const defaultAggregateMetrics: TrendAggregateMetric[] = percentOrAverageMetric
    ? ['average']
    : ['average', 'sum']
  const configuredComparisonMetrics = Array.isArray(props.insight?.comparison?.metrics)
    ? props.insight!.comparison!.metrics!.filter((metric) => availableComparisonMetrics.includes(metric))
    : []
  const comparisonMetrics =
    configuredComparisonMetrics.length > 0 ? configuredComparisonMetrics : defaultComparisonSelections
  const configuredAggregateMetrics = Array.isArray(props.insight?.aggregate?.metrics)
    ? props.insight!.aggregate!.metrics!.filter((metric) => !(metric === 'sum' && percentOrAverageMetric))
    : []
  const aggregateMetrics =
    configuredAggregateMetrics.length > 0 ? configuredAggregateMetrics : defaultAggregateMetrics

  if (props.insight?.comparison?.enabled !== false && comparisonMetrics.length > 0) {
    const pointByDate = new Map(sortedDatedPoints.map((point) => [point.date.label, point]))
    comparisonMetrics.forEach((metric) => {
      const targetDate = compareTargetDate(latestPoint.date, metric)
      const previousPoint = targetDate ? pointByDate.get(targetDate.label) : undefined
      if (!previousPoint || previousPoint.value === 0) {
        return
      }
      const change = ((latestPoint.value - previousPoint.value) / Math.abs(previousPoint.value)) * 100
      comparisonStats.push({
        label: comparisonLabel(metric, granularity),
        value: formatSignedPercent(change),
        subLabel: previousPoint.date.label,
        color: chartPalette[comparisonStats.length % chartPalette.length],
        tone: change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral',
        group: 'comparison',
      })
    })
  }

  if (props.insight?.aggregate?.enabled !== false) {
    const total = aggregatePoints.reduce((sum, point) => sum + point.value, 0)
    const average = total / aggregatePoints.length
    const peak = aggregatePoints.reduce((max, point) => (point.value > max.value ? point : max), aggregatePoints[0])
    const lowest = aggregatePoints.reduce((min, point) => (point.value < min.value ? point : min), aggregatePoints[0])
    aggregateMetrics.forEach((metric) => {
      if (metric === 'sum' && percentOrAverageMetric) {
        return
      }
      if (metric === 'average') {
        aggregateStats.push({
          label: aggregateLabel(metric),
          value: formatChartValue(average, metricAxis),
          color: chartPalette[(comparisonStats.length + aggregateStats.length) % chartPalette.length],
          group: 'aggregate',
        })
        return
      }
      if (metric === 'sum') {
        aggregateStats.push({
          label: aggregateLabel(metric),
          value: formatChartValue(total, metricAxis),
          color: chartPalette[(comparisonStats.length + aggregateStats.length) % chartPalette.length],
          group: 'aggregate',
        })
        return
      }
      const point = metric === 'max' ? peak : lowest
      aggregateStats.push({
        label: aggregateLabel(metric),
        value: formatChartValue(point.row[metricAxis.value], metricAxis),
        subLabel: trendPointSubLabel(point),
        color: chartPalette[(comparisonStats.length + aggregateStats.length) % chartPalette.length],
        group: 'aggregate',
      })
    })
  }

  if (comparisonStats.length === 0 && aggregateStats.length === 0) {
    return null
  }

  return {
    anchorLabel: trendPointSubLabel(latestPoint),
    latestValue: formatChartValue(latestPoint.row[metricAxis.value], metricAxis),
    comparisonStats,
    aggregateStats,
  }
}

function buildSingleTrendStats(axis: ChartAxis): Array<StatItem> {
  const points = rows.value
    .map((row, index) => ({
      row,
      index,
      value: numericValue(row, axis),
    }))
    .filter((item): item is { row: ChartData; index: number; value: number } => item.value !== null)

  if (points.length === 0) {
    return []
  }

  const configuredSummary = buildConfiguredTrendSummary(axis, points)
  if (configuredSummary !== null) {
    return [...configuredSummary.comparisonStats, ...configuredSummary.aggregateStats]
  }

  const first = points[0]
  const last = points[points.length - 1]
  const peak = points.reduce((max, item) => (item.value > max.value ? item : max), points[0])
  const lowest = points.reduce((min, item) => (item.value < min.value ? item : min), points[0])
  const total = points.reduce((sum, item) => sum + item.value, 0)
  const average = total / points.length
  const firstChange = relativeChangeMeta(last.value, first.value, 'chat.insight_start_change')
  const percentMetric = isPercentAxis(axis, rows.value)

  const stats: Array<StatItem> = [
    {
      label: t('chat.insight_latest_point'),
      value: formatChartValue(last.row[axis.value], axis),
      subLabel: pointLabel(last.row, last.index),
      meta: firstChange?.text,
      tone: firstChange?.tone,
      color: chartPalette[0],
    },
    {
      label: t('chat.insight_peak'),
      value: formatChartValue(peak.row[axis.value], axis),
      subLabel: pointLabel(peak.row, peak.index),
      color: chartPalette[1],
    },
    {
      label: t('chat.insight_average'),
      value: formatChartValue(average, axis),
      color: chartPalette[2],
    },
  ]

  if (percentMetric) {
    stats.push({
      label: t('chat.insight_lowest'),
      value: formatChartValue(lowest.row[axis.value], axis),
      subLabel: pointLabel(lowest.row, lowest.index),
      color: chartPalette[3],
    })
  } else {
    stats.push({
      label: t('chat.insight_total'),
      value: formatChartValue(total, axis),
      color: chartPalette[3],
    })
  }

  return stats.slice(0, props.maxStats)
}

function buildTrendStats(): Array<StatItem> {
  const axis = valueAxes.value[0]
  if (!axis) {
    return []
  }

  if (seriesAxis.value) {
    return buildTrendSeriesStats(axis)
  }

  if (valueAxes.value.length > 1) {
    return buildLatestStats()
  }

  return buildSingleTrendStats(axis)
}

function buildFunnelStats(): Array<StatItem> {
  const axis = valueAxes.value[0]
  if (!axis) {
    return []
  }

  const points = rows.value
    .map((row, index) => ({ row, index, value: numericValue(row, axis) }))
    .filter((item): item is { row: ChartData; index: number; value: number } => item.value !== null)

  if (points.length === 0) {
    return []
  }

  const first = points[0]
  const last = points[points.length - 1]
  const conversion = first.value === 0 ? null : (last.value / first.value) * 100
  const stats: Array<StatItem> = [
    {
      label: categoryLabel(first.row, first.index),
      value: formatChartValue(first.row[axis.value], axis),
      subLabel: displayAxisName(axis),
      color: chartPalette[0],
    },
  ]

  if (points.length > 1) {
    stats.push({
      label: categoryLabel(last.row, last.index),
      value: formatChartValue(last.row[axis.value], axis),
      subLabel: displayAxisName(axis),
      color: chartPalette[1],
    })
  }

  if (conversion !== null) {
    stats.push({
      label: t('chat.insight_conversion'),
      value: formatPercent(conversion),
      subLabel: `${categoryLabel(first.row, first.index)} -> ${categoryLabel(last.row, last.index)}`,
      color: chartPalette[2],
      tone: conversion >= 100 ? 'positive' : 'neutral',
    })
  }

  return stats.slice(0, props.maxStats)
}

function buildRankedStats(includeTotal = true): Array<StatItem> {
  const axis = valueAxes.value[0]
  if (!axis) {
    return []
  }

  const values = rows.value
    .map((row, index) => ({
      row,
      index,
      label: categoryLabel(row, index),
      value: numericValue(row, axis),
    }))
    .filter((item): item is { row: ChartData; index: number; label: string; value: number } => item.value !== null)

  if (values.length === 0) {
    return []
  }

  const total = values.reduce((sum, item) => sum + item.value, 0)
  const ranked = [...values].sort((a, b) => b.value - a.value)
  const stats: Array<StatItem> = []

  if (includeTotal && total > 0) {
    stats.push({
      label: t('chat.insight_total'),
      value: String(formatNumberForInsight(total)),
      subLabel: displayAxisName(axis),
      color: chartPalette[0],
    })
  }

  ranked.slice(0, Math.max(props.maxStats - stats.length, 1)).forEach((item, index) => {
    const share = total > 0 ? (item.value / total) * 100 : null
    stats.push({
      label: item.label,
      value: formatChartValue(item.row[axis.value], axis),
      subLabel: share === null ? displayAxisName(axis) : t('chat.insight_share', [formatPercent(share)]),
      color: chartPalette[(index + stats.length) % chartPalette.length],
    })
  })

  return stats.slice(0, props.maxStats)
}

const stats = computed<Array<StatItem>>(() => {
  if (trendChartTypes.has(props.chartType)) {
    return buildTrendStats()
  }

  if (props.chartType === 'funnel') {
    return buildFunnelStats()
  }

  if (structureChartTypes.has(props.chartType) || props.chartType === 'sankey') {
    return buildRankedStats(true)
  }

  if (rankedChartTypes.has(props.chartType) && !isTrendLike.value) {
    return buildRankedStats(false)
  }

  return buildLatestStats()
})

const configuredTrendSummary = computed<ConfiguredTrendSummary | null>(() => {
  if (!trendChartTypes.has(props.chartType) || seriesAxis.value || valueAxes.value.length !== 1) {
    return null
  }

  const axis = valueAxes.value[0]
  if (!axis) {
    return null
  }

  const points = rows.value
    .map((row, index) => ({
      row,
      index,
      value: numericValue(row, axis),
    }))
    .filter((item): item is { row: ChartData; index: number; value: number } => item.value !== null)

  if (points.length === 0) {
    return null
  }

  return buildConfiguredTrendSummary(axis, points)
})

const dataDateRangeLabel = computed(() => {
  if (rows.value.length === 0) {
    return ''
  }

  const fields = new Set<string>()
  rows.value.slice(0, 50).forEach((row) => {
    Object.keys(row || {}).forEach((field) => fields.add(field))
  })

  const candidates = Array.from(fields)
    .map((field) => {
      const dates = rows.value
        .map((row) => parseDateForRange(row?.[field]))
        .filter((item): item is { label: string; time: number } => item !== null)
      const distinctCount = new Set(dates.map((item) => item.label)).size
      return {
        field,
        dates,
        distinctCount,
        coverage: rows.value.length > 0 ? dates.length / rows.value.length : 0,
        priority: dateFieldPriority(field),
      }
    })
    .filter((item) => item.dates.length > 0 && item.coverage >= 0.5)
    .sort((a, b) => {
      if (b.distinctCount !== a.distinctCount) {
        return b.distinctCount - a.distinctCount
      }
      if (b.priority !== a.priority) {
        return b.priority - a.priority
      }
      return b.coverage - a.coverage
    })

  const best = candidates[0]
  if (!best) {
    return ''
  }

  const sortedDates = [...best.dates].sort((a, b) => a.time - b.time)
  const start = sortedDates[0]?.label
  const end = sortedDates[sortedDates.length - 1]?.label
  if (!start || !end) {
    return ''
  }
  return start === end ? start : `${start} - ${end}`
})

const inferredDataDateRangeLabel = computed(() => {
  const sqlDates = extractSqlDates(props.sql)
  if (sqlDates.length === 0) {
    return ''
  }

  const sortedDates = [...sqlDates].sort((a, b) => a.time - b.time)
  let start = sortedDates[0]
  let end = sortedDates[sortedDates.length - 1]

  const axisRange = numericAxisRange(xAxis.value)
  if (sqlDates.length === 1 && axisRange && isDayAxis(xAxis.value)) {
    start = addDays(sortedDates[0], Math.min(axisRange.min, axisRange.max))
    end = addDays(sortedDates[0], Math.max(axisRange.min, axisRange.max))
  }

  return start.label === end.label ? start.label : `${start.label} - ${end.label}`
})

const metaItems = computed(() => {
  const items: Array<string> = []
  const dataPeriod = dataDateRangeLabel.value || inferredDataDateRangeLabel.value
  if (dataPeriod) {
    items.push(t('chat.insight_data_period', [dataPeriod]))
  }
  return items
})

const anchorLabel = computed(() => {
  if (!stats.value.length) {
    return ''
  }
  if (props.chartType === 'funnel') {
    return t('chat.insight_funnel_summary')
  }
  if (structureChartTypes.has(props.chartType)) {
    return t('chat.insight_composition_summary')
  }
  if (props.chartType === 'sankey') {
    return t('chat.insight_flow_summary')
  }
  if (trendChartTypes.has(props.chartType)) {
    return t('chat.insight_trend_summary')
  }
  if (isTrendLike.value && latestAnchorValue.value) {
    return t('chat.insight_latest', [stringifyValue(latestAnchorValue.value)])
  }
  return t('chat.insight_top', [stats.value.length])
})

const layoutClass = computed(() => props.layout)
const densityClass = computed(() => props.density)
const visibleMetaItems = computed(() => {
  if (configuredTrendSummary.value && props.layout === 'side') {
    return []
  }
  if (props.density === 'basic') {
    return metaItems.value.slice(0, 1)
  }
  return metaItems.value
})
const visibleStats = computed(() => {
  if (configuredTrendSummary.value) {
    return stats.value
  }
  if (props.density === 'basic') {
    return stats.value.slice(0, 1)
  }
  return stats.value
})
const showAnchor = computed(() => props.density !== 'basic')
</script>

<template>
  <div
    v-if="shouldShow && stats.length > 0"
    class="chart-insight-header"
    :class="[
      layoutClass,
      densityClass,
      {
        compact,
        'configured-trend': Boolean(configuredTrendSummary),
        'featured-side': featuredSide,
      },
    ]"
  >
    <div v-if="visibleMetaItems.length" class="insight-meta-row">
      <span v-for="item in visibleMetaItems" :key="item" class="insight-meta-item">{{ item }}</span>
    </div>
    <div class="insight-stat-row" :class="{ 'no-meta': visibleMetaItems.length === 0 }">
      <template v-if="configuredTrendSummary">
        <div class="configured-trend-layout">
          <div class="configured-trend-primary">
            <div class="configured-trend-anchor" :title="configuredTrendSummary.anchorLabel">
              {{ configuredTrendSummary.anchorLabel }}
            </div>
            <div class="configured-trend-value" :title="configuredTrendSummary.latestValue">
              {{ configuredTrendSummary.latestValue }}
            </div>
          </div>
          <div
            v-if="configuredTrendSummary.comparisonStats.length || configuredTrendSummary.aggregateStats.length"
            class="configured-trend-metrics"
          >
            <div
              v-if="configuredTrendSummary.comparisonStats.length"
              class="configured-trend-group configured-trend-comparison"
            >
              <div
                v-for="item in configuredTrendSummary.comparisonStats"
                :key="`${item.label}-${item.value}`"
                class="configured-trend-item configured-trend-comparison-item"
                :title="item.subLabel ? `${item.label} ${item.subLabel}` : item.label"
              >
                <span class="configured-trend-item-label">{{ item.label }}</span>
                <span class="configured-trend-item-value" :class="item.tone">{{ item.value }}</span>
              </div>
            </div>
            <div
              v-if="configuredTrendSummary.aggregateStats.length"
              class="configured-trend-group configured-trend-aggregate"
            >
              <div
                v-for="item in configuredTrendSummary.aggregateStats"
                :key="`${item.label}-${item.value}`"
                class="configured-trend-item configured-trend-aggregate-item"
              >
                <div class="configured-trend-aggregate-row">
                  <span class="configured-trend-item-label">{{ item.label }}</span>
                  <span class="configured-trend-item-value configured-trend-aggregate-value">{{ item.value }}</span>
                </div>
                <div v-if="item.subLabel" class="configured-trend-item-sub-label" :title="item.subLabel">
                  {{ item.subLabel }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-else>
        <div v-if="showAnchor && anchorLabel" class="insight-anchor">{{ anchorLabel }}</div>
        <div class="insight-stat-grid">
          <div v-for="item in visibleStats" :key="`${item.label}-${item.value}`" class="insight-stat">
            <div class="insight-stat-value" :class="item.tone" :title="item.value">{{ item.value }}</div>
            <div v-if="item.label" class="insight-stat-label" :title="item.label">
              <span class="insight-color" :style="{ backgroundColor: item.color }" />
              <span class="insight-label-text">{{ item.label }}</span>
            </div>
            <div v-if="item.subLabel" class="insight-stat-sub-label" :title="item.subLabel">
              {{ item.subLabel }}
            </div>
            <div v-if="item.meta" class="insight-stat-meta" :class="item.tone">
              {{ item.meta }}
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped lang="less">
.chart-insight-header {
  flex: 0 0 auto;
  padding: 2px 2px 12px;
  margin-bottom: 10px;
  border-bottom: 1px solid #eaf0f8;

  .insight-meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 14px;
    min-height: 20px;
    align-items: center;
    color: #4c5f78;
    font-size: 12px;
    line-height: 20px;
  }

  .insight-meta-item {
    max-width: min(100%, 520px);
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    overflow-wrap: anywhere;
  }

  .insight-stat-row {
    margin-top: 8px;

    &.no-meta {
      margin-top: 0;
    }
  }

  .insight-anchor {
    margin-bottom: 4px;
    color: #63748c;
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .insight-stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
    gap: 12px;
  }

  .insight-stat {
    min-width: 0;
  }

  .insight-stat-value {
    color: #14243a;
    font-size: 21px;
    font-weight: 700;
    line-height: 28px;
    letter-spacing: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    &.positive {
      color: #0c9b6d;
    }

    &.negative {
      color: #e05252;
    }
  }

  .insight-stat-label,
  .insight-stat-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    margin-top: 2px;
    color: #44546a;
    font-size: 12px;
    line-height: 18px;
  }

  .insight-label-text {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .insight-color {
    flex: 0 0 auto;
    width: 7px;
    height: 12px;
    border-radius: 2px;
  }

  .insight-stat-sub-label {
    margin-top: 1px;
    padding-left: 13px;
    color: #7a8aa0;
    font-size: 11px;
    line-height: 16px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .insight-stat-meta {
    padding-left: 13px;
    color: #7a8aa0;

    &.positive {
      color: #0c9b6d;
    }

    &.negative {
      color: #e05252;
    }
  }

  .configured-trend-layout {
    width: 100%;
    min-width: 0;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: flex-start;
    gap: 12px 28px;
  }

  .configured-trend-primary {
    min-width: 0;
  }

  .configured-trend-anchor {
    color: #63748c;
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .configured-trend-value {
    margin-top: 4px;
    color: #14243a;
    font-size: 28px;
    font-weight: 700;
    line-height: 34px;
    letter-spacing: 0;
    white-space: nowrap;
  }

  .configured-trend-metrics {
    box-sizing: border-box;
    width: 100%;
    display: grid;
    grid-template-columns: minmax(92px, max-content) minmax(118px, auto);
    align-items: center;
    justify-self: stretch;
    gap: 10px 28px;
    min-width: 0;
    max-width: none;
    padding: 24px 28px 0 0;
  }

  .configured-trend-group {
    min-width: 0;
  }

  .configured-trend-comparison {
    justify-self: start;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .configured-trend-aggregate {
    justify-self: end;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    align-items: flex-end;
  }

  .configured-trend-item {
    min-width: 0;
  }

  .configured-trend-comparison-item,
  .configured-trend-aggregate-row {
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;
  }

  .configured-trend-aggregate-row {
    justify-content: flex-end;
  }

  .configured-trend-item-label {
    flex: 0 0 auto;
    color: #44546a;
    font-size: 12px;
    line-height: 18px;
    white-space: nowrap;
  }

  .configured-trend-item-value {
    min-width: 0;
    color: #14243a;
    font-size: 12px;
    font-weight: 600;
    line-height: 18px;
    white-space: nowrap;

    &.positive {
      color: #0c9b6d;
    }

    &.negative {
      color: #e05252;
    }
  }

  .configured-trend-aggregate-value {
    font-size: 14px;
    line-height: 20px;
  }

  .configured-trend-item-sub-label {
    margin-top: 1px;
    color: #7a8aa0;
    font-size: 11px;
    line-height: 16px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &.side {
    width: 208px;
    height: 100%;
    padding: 2px 14px 2px 0;
    margin: 0 16px 0 0;
    border-right: 1px solid #eaf0f8;
    border-bottom: 0;
    overflow: hidden;

    .insight-meta-row {
      display: block;
      min-height: 0;
    }

    .insight-meta-item {
      display: block;
      max-width: 100%;
      margin-bottom: 4px;
    }

    .insight-stat-row {
      margin-top: 12px;
    }

    .insight-stat-grid {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .insight-stat-value {
      font-size: 27px;
      line-height: 34px;
    }

    .configured-trend-layout {
      height: 100%;
      grid-template-columns: 1fr;
      justify-content: space-between;
      gap: 14px;
    }

    .configured-trend-value {
      font-size: 30px;
      line-height: 36px;
    }

    .configured-trend-metrics {
      grid-template-columns: 1fr;
      justify-self: stretch;
      gap: 8px;
      min-width: 0;
      max-width: none;
      padding: 0;
    }

    .configured-trend-comparison {
      gap: 4px;
    }

    .configured-trend-item-label,
    .configured-trend-item-value {
      font-size: 12px;
      line-height: 18px;
    }

    .configured-trend-aggregate {
      gap: 6px;
    }

    .configured-trend-aggregate-value {
      font-size: 13px;
      line-height: 18px;
    }

    &.configured-trend.featured-side {
      width: 210px;
      padding: 0 18px 0 0;
      margin: 0 28px 0 0;

      .insight-stat-row {
        height: 100%;
        margin-top: 0;
      }

      .configured-trend-layout {
        display: flex;
        height: 100%;
        flex-direction: column;
        justify-content: flex-start;
        gap: 22px;
      }

      .configured-trend-anchor {
        color: #1f3554;
        font-size: 12px;
        line-height: 18px;
      }

      .configured-trend-value {
        margin-top: 2px;
        color: #071a33;
        font-size: 36px;
        font-weight: 700;
        line-height: 44px;
      }

      .configured-trend-metrics {
        display: flex;
        flex: 1 1 auto;
        flex-direction: column;
        justify-content: space-between;
        gap: 20px;
      }

      .configured-trend-comparison {
        gap: 4px;
      }

      .configured-trend-comparison-item {
        gap: 6px;
      }

      .configured-trend-item-label {
        color: #14243a;
        font-size: 13px;
        line-height: 20px;
      }

      .configured-trend-item-value {
        color: #14243a;
        font-size: 13px;
        font-weight: 700;
        line-height: 20px;

        &.positive {
          color: #0c9b6d;
        }

        &.negative {
          color: #e05252;
        }
      }

      .configured-trend-aggregate {
        align-items: flex-start;
        gap: 8px;
      }

      .configured-trend-aggregate-row {
        justify-content: flex-start;
        gap: 6px;
      }

      .configured-trend-aggregate-item {
        min-width: 0;
      }

      .configured-trend-aggregate-item .configured-trend-item-label {
        color: #14243a;
        font-size: 13px;
        line-height: 24px;
      }

      .configured-trend-aggregate-value {
        color: #071a33;
        font-size: 32px;
        font-weight: 500;
        line-height: 38px;
      }
    }
  }

  &.compact {
    padding-bottom: 8px;
    margin-bottom: 8px;

    .insight-meta-row {
      gap: 6px 10px;
    }

    .insight-meta-item {
      max-width: 100%;
    }

    .insight-stat-row {
      margin-top: 6px;
    }

    .insight-stat-grid {
      grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
      gap: 8px;
    }

    .insight-stat-value {
      font-size: 17px;
      line-height: 23px;
    }

    .insight-stat-sub-label,
    .insight-stat-meta {
      display: none;
    }

    .configured-trend-layout {
      grid-template-columns: auto minmax(0, 1fr);
      gap: 8px 18px;
    }

    .configured-trend-value {
      font-size: 24px;
      line-height: 30px;
    }

    .configured-trend-metrics {
      grid-template-columns: minmax(86px, max-content) minmax(112px, auto);
      gap: 6px 18px;
      min-width: 0;
      padding: 22px 42px 0 0;
    }

    .configured-trend-aggregate-value {
      font-size: 13px;
      line-height: 18px;
    }

    &.side {
      width: 188px;
      padding-right: 12px;
      margin-right: 12px;

      .insight-stat-grid {
        display: flex;
        gap: 10px;
      }

      .insight-stat-sub-label,
      .insight-stat-meta {
        display: block;
      }

      .configured-trend-value {
        font-size: 26px;
        line-height: 32px;
      }

      .configured-trend-comparison {
        gap: 3px;
      }

      .configured-trend-metrics {
        grid-template-columns: 1fr;
        gap: 6px;
        min-width: 0;
        max-width: none;
        padding: 0;
      }

      .configured-trend-item-label,
      .configured-trend-item-value {
        font-size: 11px;
        line-height: 16px;
      }

      .configured-trend-aggregate {
        gap: 4px;
      }

      .configured-trend-aggregate-value {
        font-size: 12px;
        line-height: 16px;
      }
    }
  }

  &.mini {
    padding: 0 0 6px;
    margin-bottom: 6px;

    .insight-meta-row {
      flex-wrap: nowrap;
      gap: 6px;
      min-height: 18px;
      overflow: hidden;
      line-height: 18px;
    }

    .insight-meta-item {
      flex: 0 1 auto;
      max-width: min(100%, 220px);
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      &:nth-child(n + 4) {
        display: none;
      }
    }

    .insight-stat-row {
      margin-top: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }

    .insight-anchor {
      flex: 0 1 auto;
      max-width: 120px;
      margin: 0;
      font-size: 11px;
      line-height: 18px;
    }

    .insight-stat-grid {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      gap: 10px;
      overflow: hidden;
    }

    .insight-stat {
      flex: 0 1 auto;
      min-width: 0;

      &:nth-child(n + 3) {
        display: none;
      }
    }

    .insight-stat-value {
      font-size: 13px;
      line-height: 18px;
    }

    .insight-stat-label {
      margin-top: 0;
      font-size: 11px;
      line-height: 16px;
    }

    .configured-trend-layout {
      grid-template-columns: auto minmax(0, 1fr);
      gap: 6px 12px;
    }

    .configured-trend-anchor,
    .configured-trend-item-label,
    .configured-trend-item-value {
      font-size: 11px;
      line-height: 16px;
    }

    .configured-trend-value {
      font-size: 20px;
      line-height: 24px;
    }

    .configured-trend-metrics {
      grid-template-columns: minmax(74px, max-content) minmax(96px, auto);
      gap: 4px 12px;
      min-width: 0;
      padding: 18px 18px 0 0;
    }

    .insight-color {
      width: 6px;
      height: 10px;
    }

    .insight-stat-sub-label,
    .insight-stat-meta {
      display: none;
    }

    &.side {
      width: 176px;
      height: 100%;
      padding: 2px 10px 2px 0;
      margin: 0 10px 0 0;
      border-right: 1px solid #eaf0f8;
      border-bottom: 0;
      overflow: hidden;

      .insight-meta-row {
        display: block;
        min-height: 0;
        overflow: visible;
      }

      .insight-meta-item {
        display: block;
        max-width: 100%;
        margin-bottom: 4px;
        white-space: normal;
        overflow: visible;
        text-overflow: clip;
        overflow-wrap: anywhere;

        &:nth-child(n + 4) {
          display: block;
        }
      }

      .insight-stat-row {
        margin-top: 8px;
        display: block;
      }

      .insight-anchor {
        max-width: 100%;
        margin-bottom: 4px;
      }

      .insight-stat-grid {
        display: flex;
        flex-direction: column;
        gap: 8px;
        overflow: visible;
      }

      .insight-stat {
        flex: 0 0 auto;

        &:nth-child(n + 3) {
          display: block;
        }
      }

      .insight-stat-sub-label,
      .insight-stat-meta {
        display: block;
      }

      .configured-trend-layout {
        height: 100%;
        grid-template-columns: 1fr;
        gap: 10px;
      }

      .configured-trend-metrics {
        grid-template-columns: 1fr;
        gap: 6px;
        padding: 0;
      }
    }
  }

  &.basic {
    padding: 0 0 4px;
    margin-bottom: 4px;

    .insight-meta-row {
      flex-wrap: nowrap;
      min-height: 16px;
      gap: 6px;
      overflow: hidden;
      font-size: 11px;
      line-height: 16px;
    }

    .insight-meta-item {
      max-width: 100%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .insight-stat-row {
      margin-top: 2px;
      display: flex;
      min-width: 0;
    }

    .insight-anchor {
      display: none;
    }

    .insight-stat-grid {
      display: flex;
      min-width: 0;
      gap: 0;
      overflow: hidden;
    }

    .insight-stat {
      display: flex;
      align-items: center;
      min-width: 0;
      gap: 6px;
    }

    .insight-stat-value {
      flex: 0 0 auto;
      font-size: 13px;
      line-height: 18px;
    }

    .insight-stat-label {
      min-width: 0;
      margin-top: 0;
      font-size: 11px;
      line-height: 16px;
    }

    .insight-color {
      width: 6px;
      height: 10px;
    }

    .insight-stat-sub-label,
    .insight-stat-meta {
      display: none;
    }

    .configured-trend-layout {
      flex: 1 1 auto;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 4px 10px;
    }

    .configured-trend-anchor,
    .configured-trend-item-label,
    .configured-trend-item-value {
      font-size: 11px;
      line-height: 16px;
    }

    .configured-trend-value {
      font-size: 18px;
      line-height: 22px;
    }

    .configured-trend-metrics {
      grid-template-columns: minmax(64px, max-content) minmax(82px, auto);
      gap: 2px 8px;
      min-width: 0;
      padding: 16px 14px 0 0;
    }

    &.side {
      width: auto;
      height: auto;
      padding: 0 0 4px;
      margin: 0 0 4px;
      border-right: 0;
      border-bottom: 1px solid #eaf0f8;

      .configured-trend-layout {
        grid-template-columns: 1fr;
        gap: 8px;
      }

      .configured-trend-metrics {
        grid-template-columns: 1fr;
        min-width: 0;
        padding-top: 0;
      }
    }
  }
}
</style>
