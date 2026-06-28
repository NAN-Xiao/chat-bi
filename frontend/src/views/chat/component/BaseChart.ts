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

export type ChartMountTarget = string | HTMLElement

export type ChartTypes =
  | 'table'
  | 'bar'
  | 'column'
  | 'line'
  | 'area'
  | 'pie'
  | 'metric'
  | 'funnel'
  | 'heatmap'
  | 'scatter'
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

  constructor(mountTarget: ChartMountTarget, name: string) {
    this.mountTarget = mountTarget
    this.id = typeof mountTarget === 'string' ? mountTarget : mountTarget.id
    this._name = name
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>): void {
    this.axis = axis
    this.data = data
  }

  abstract render(): void | Promise<unknown>

  abstract destroy(): void
}
