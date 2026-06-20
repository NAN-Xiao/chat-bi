export interface ChartAxis {
  name: string
  value: string
  type?: 'x' | 'y' | 'series' | 'other-info'
  'multi-quota'?: boolean
  hidden?: boolean
}

export interface ChartData {
  [key: string]: any
}

export interface ChartInsightsOptions {
  enabled?: boolean
}

export type ChartInsightsConfig = boolean | ChartInsightsOptions | undefined

export type ChartTypes =
  | 'table'
  | 'bar'
  | 'column'
  | 'line'
  | 'pie'
  | 'metric'
  | 'funnel'
  | 'heatmap'
  | 'scatter'
  | 'sankey'
  | 'treemap'

export abstract class BaseChart {
  id: string
  _name: string = 'base-chart'
  axis: Array<ChartAxis> = []
  data: Array<ChartData> = []
  showLabel: boolean = false
  insights: ChartInsightsConfig = undefined

  constructor(id: string, name: string) {
    this.id = id
    this._name = name
  }

  get insightsEnabled(): boolean {
    if (this.insights === false) {
      return false
    }
    if (typeof this.insights === 'object' && this.insights?.enabled === false) {
      return false
    }
    return true
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>): void {
    this.axis = axis
    this.data = data
  }

  abstract render(): void

  abstract destroy(): void
}
