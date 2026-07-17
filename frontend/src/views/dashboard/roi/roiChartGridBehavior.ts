import type {
  RoiChart,
  RoiDateRange,
  RoiChartOrderItem,
  RoiChartPreviewRequest,
  RoiChartPreviewResponse,
  RoiLayoutSpan,
} from './types'

const ROI_DATE_PLACEHOLDER_PAIRS = [
  ['{{start_date}}', '{{end_date}}'],
  ['{{start_date_yyyymmdd}}', '{{end_date_yyyymmdd}}'],
] as const

function formatLocalDate(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function defaultRoiDateRange(now = new Date()): RoiDateRange {
  const endDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  const startDate = new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate() - 6)
  return [formatLocalDate(startDate), formatLocalDate(endDate)]
}

export function hasRoiDateRangePlaceholders(sql: string | null | undefined) {
  const source = String(sql || '')
  let hasCompletePair = false
  for (const [startPlaceholder, endPlaceholder] of ROI_DATE_PLACEHOLDER_PAIRS) {
    const hasStart = source.includes(startPlaceholder)
    const hasEnd = source.includes(endPlaceholder)
    if (hasStart !== hasEnd) return false
    if (hasStart) hasCompletePair = true
  }
  return hasCompletePair
}

export const roiLayoutSpanColumns: Record<RoiLayoutSpan, number> = {
  full: 6,
  half: 3,
  third: 2,
}

export const canManageRoiChart = (chart: RoiChart, canEdit: boolean) =>
  canEdit && chart.can_execute !== false && chart.can_edit !== false

export function moveRoiChart(charts: RoiChart[], fromIndex: number, toIndex: number) {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= charts.length ||
    toIndex >= charts.length
  ) {
    return [...charts]
  }
  const reordered = [...charts]
  const [moved] = reordered.splice(fromIndex, 1)
  reordered.splice(toIndex, 0, moved)
  return reordered
}

export const buildRoiChartOrderItems = (charts: RoiChart[]): RoiChartOrderItem[] =>
  charts.map((chart, index) => ({
    id: String(chart.id),
    sort: index + 1,
    layout_span: chart.layout_span,
    version: chart.version,
  }))

export function mergeReorderedRoiCharts(current: RoiChart[], reordered: RoiChart[]) {
  const currentById = new Map(current.map((chart) => [String(chart.id), chart]))
  return reordered.map((chart) => {
    const previous = currentById.get(String(chart.id))
    if (!previous) return chart
    return {
      ...chart,
      query_result: chart.query_result === null ? previous.query_result : chart.query_result,
    }
  })
}

export function buildRoiChartPreviewRequest(
  chart: RoiChart,
  dateRange?: RoiDateRange
): RoiChartPreviewRequest {
  const request: RoiChartPreviewRequest = {
    title: chart.title,
    sql: String(chart.sql || '').trim(),
    chart_type: chart.chart_type,
    chart_config: { ...(chart.chart_config || {}) },
    layout_span: chart.layout_span,
  }
  if (dateRange) {
    request.start_date = dateRange[0]
    request.end_date = dateRange[1]
  }
  return request
}

export function replaceRoiChartPreviewResult(
  charts: RoiChart[],
  chartId: string,
  result: RoiChartPreviewResponse
) {
  return charts.map((chart) =>
    String(chart.id) === String(chartId) ? { ...chart, error: null, query_result: result } : chart
  )
}
