import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'

export const analysisModelChartTypes: Record<string, readonly ChartTypes[]> = {
  event: ['table', 'metric', 'line', 'area', 'column', 'grouped_column', 'bar', 'pie', 'donut'],
  property: ['table', 'column', 'pie'],
  retention: ['table', 'line'],
  funnel: ['table', 'funnel', 'column', 'line'],
  distribution: ['table', 'column', 'area', 'pie'],
  interval: ['table', 'column', 'boxplot'],
  path: ['sankey'],
  revenue: ['table'],
  attribution: ['table'],
  ranking: ['table', 'bar'],
  heatmap: ['heatmap'],
}

export function supportsAnalysisChartType(model: string, chartType: ChartTypes): boolean {
  const types = analysisModelChartTypes[model]
  return Array.isArray(types) && types.includes(chartType)
}
