import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'
import { ChartValidationError, trendDimensionError } from '@/views/chat/component/chartValidation.ts'

export interface ChartAxis {
  name?: string
  value: string
  type?: 'x' | 'y' | 'series' | 'other-info'
  'multi-quota'?: boolean
  metricType?: 'additive' | 'average' | 'ratio' | 'snapshot' | 'derived'
  pivotAggregation?: 'sum' | 'avg' | 'count' | 'min' | 'max'
  hidden?: boolean
}

export function axisLabel(axis?: Pick<ChartAxis, 'name' | 'value'> | null): string {
  return String(axis?.name || axis?.value || '').trim()
}

export function axisValue(axis?: Pick<ChartAxis, 'name' | 'value'> | null): string {
  return String(axis?.value || axis?.name || '').trim()
}

export interface ChartData {
  [key: string]: any
}

export type ChartForecastMethod =
  | 'auto'
  | 'linear'
  | 'polynomial'
  | 'exponential'
  | 'logarithmic'
  | 'power'
  | 'reciprocal'
  | 'logistic'
  | 'gompertz'
  | 'holt_winters'

export interface ChartForecastConfig {
  enabled?: boolean
  method?: ChartForecastMethod
  periods?: number
  historyWindow?: number
}

export type ChartMountTarget = string | HTMLElement

export type ChartTypes =
  | 'table'
  | 'bar'
  | 'column'
  | 'grouped_column'
  | 'line'
  | 'area'
  | 'pie'
  | 'donut'
  | 'metric'
  | 'funnel'
  | 'heatmap'
  | 'scatter'
  | 'boxplot'
  | 'sankey'
  | 'treemap'

export abstract class BaseChart {
  id: string
  mountTarget: ChartMountTarget
  _name: string = 'base-chart'
  axis: Array<ChartAxis> = []
  data: Array<ChartData> = []
  showLabel: boolean = false
  hideZeroLabel: boolean = false
  hideValueAxis: boolean = false
  forecast?: ChartForecastConfig
  layoutContext?: ChartLayoutContext

  constructor(mountTarget: ChartMountTarget, name: string) {
    this.mountTarget = mountTarget
    this.id = typeof mountTarget === 'string' ? mountTarget : mountTarget.id
    this._name = name
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>): void {
    const error = trendDimensionError(this._name, axis, data)
    if (error) throw new ChartValidationError(error)
    this.axis = axis
    this.data = data
  }

  abstract render(): void | Promise<unknown>

  abstract destroy(): void
}
