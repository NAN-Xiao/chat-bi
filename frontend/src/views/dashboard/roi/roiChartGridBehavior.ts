import type { RoiChart, RoiChartOrderItem, RoiLayoutSpan } from './types'

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
