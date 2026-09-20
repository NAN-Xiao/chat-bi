import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import { ChartValidationError } from '@/views/chat/component/chartValidation.ts'

export interface BoxplotSummary {
  category: string
  series: string
  low: number
  q1: number
  median: number
  q3: number
  high: number
  count: number
}

export interface BoxplotOutlier {
  category: string
  series: string
  value: number
}

function quantile(sorted: number[], fraction: number): number {
  const position = (sorted.length - 1) * fraction
  const index = Math.floor(position)
  const weight = position - index
  return sorted[index] * (1 - weight) + sorted[Math.min(index + 1, sorted.length - 1)] * weight
}

/** Compute each box from its own samples using linear quartiles and 1.5 IQR whiskers. */
export function prepareBoxplotData(
  axes: ChartAxis[],
  data: ChartData[]
): {
  boxes: BoxplotSummary[]
  outliers: BoxplotOutlier[]
} {
  const x = axes.filter((axis) => axis.type === 'x' && !axis.hidden)
  const y = axes.filter((axis) => axis.type === 'y' && !axis.hidden)
  const series = axes.filter((axis) => axis.type === 'series' && !axis.hidden)
  if (x.length !== 1)
    throw new ChartValidationError(x.length ? 'multiple_category_fields' : 'missing_category_field')
  if (y.length !== 1)
    throw new ChartValidationError(y.length ? 'multiple_value_fields' : 'missing_value_field')
  if (series.length > 1) throw new ChartValidationError('invalid_boxplot_series')
  const groups = new Map<string, { category: string; series: string; values: number[] }>()
  for (const row of data) {
    if (!(x[0].value in row)) throw new ChartValidationError('missing_category_field')
    if (!(y[0].value in row)) throw new ChartValidationError('missing_value_field')
    const category = String(row[x[0].value] ?? '').trim()
    const seriesValue = series.length ? String(row[series[0].value] ?? '').trim() : ''
    if (!category) throw new ChartValidationError('empty_category')
    if (series.length && !seriesValue) throw new ChartValidationError('invalid_boxplot_series')
    const raw = row[y[0].value]
    const isNumericString =
      typeof raw === 'string' && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw.trim())
    if (typeof raw !== 'number' && !isNumericString) throw new ChartValidationError('invalid_value')
    const value = Number(raw)
    if (!Number.isFinite(value)) throw new ChartValidationError('invalid_value')
    const key = JSON.stringify([category, seriesValue])
    let group = groups.get(key)
    if (!group) {
      group = { category, series: seriesValue, values: [] }
      groups.set(key, group)
    }
    group.values.push(value)
  }
  const boxes: BoxplotSummary[] = []
  const outliers: BoxplotOutlier[] = []
  for (const { category, series, values } of groups.values()) {
    values.sort((a, b) => a - b)
    const q1 = quantile(values, 0.25)
    const median = quantile(values, 0.5)
    const q3 = quantile(values, 0.75)
    const iqr = q3 - q1
    const lowerFence = q1 - 1.5 * iqr
    const upperFence = q3 + 1.5 * iqr
    const inside = values.filter((value) => value >= lowerFence && value <= upperFence)
    boxes.push({
      category,
      series,
      low: inside[0],
      q1,
      median,
      q3,
      high: inside[inside.length - 1],
      count: values.length,
    })
    for (const value of values) {
      if (value < lowerFence || value > upperFence) outliers.push({ category, series, value })
    }
  }
  return { boxes, outliers }
}
