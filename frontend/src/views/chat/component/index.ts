import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { Bar } from '@/views/chat/component/charts/Bar.ts'
import { Column } from '@/views/chat/component/charts/Column.ts'
import { Line } from '@/views/chat/component/charts/Line.ts'
import { Table } from '@/views/chat/component/charts/Table.ts'
import { Pie } from '@/views/chat/component/charts/Pie.ts'
import { Metric } from '@/views/chat/component/charts/Metric.ts'
import { Funnel } from '@/views/chat/component/charts/Funnel.ts'
import { Heatmap } from '@/views/chat/component/charts/Heatmap.ts'
import { Scatter } from '@/views/chat/component/charts/Scatter.ts'
import { Sankey } from '@/views/chat/component/charts/Sankey.ts'
import { Treemap } from '@/views/chat/component/charts/Treemap.ts'

const CHART_TYPE_MAP: { [key: string]: any } = {
  table: Table,
  column: Column,
  bar: Bar,
  line: Line,
  pie: Pie,
  metric: Metric,
  funnel: Funnel,
  heatmap: Heatmap,
  scatter: Scatter,
  sankey: Sankey,
  treemap: Treemap,
}

const isParent = (type: any, parentType: any) => {
  let _type = type
  while (_type) {
    if (_type === parentType) {
      return true
    }
    _type = _type.__proto__
  }
  return false
}

export function getChartInstance(type: string, id: string): BaseChart | undefined {
  if (isParent(CHART_TYPE_MAP[type], BaseChart)) {
    return new CHART_TYPE_MAP[type](id) as BaseChart
  }
  return undefined
}
