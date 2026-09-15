import type { ChartAxis, ChartData } from './BaseChart.ts'

export function trendDimensionError(type: string, axes: ChartAxis[], rows: ChartData[]): string | undefined {
  if (!['line', 'area'].includes(type) || rows.length === 0) return undefined
  const dimension = axes.find((axis) => axis.type === 'x' && !axis.hidden)
  const field = dimension?.value || dimension?.name
  if (!field) return 'missing_category_field'
  if (rows.some((row) => {
    const value = row[field]
    return value === null || value === undefined || (typeof value === 'string' && value.trim() === '')
  })) return 'invalid_trend_dimension'
  return undefined
}

export class ChartValidationError extends Error {
  constructor(public readonly code: string) {
    super(code)
    this.name = 'ChartValidationError'
  }
}

export function isChartValidationError(error: unknown): error is ChartValidationError {
  return error instanceof ChartValidationError
}
