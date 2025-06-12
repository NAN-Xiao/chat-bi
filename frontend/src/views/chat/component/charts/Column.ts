import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'

export class Column extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'column')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const x = this.axis.filter((item) => item.type === 'x')
    const y = this.axis.filter((item) => item.type === 'y')

    if (x.length == 0 || y.length == 0) {
      return
    }

    this.chart
      ?.interval()
      .data(data)
      .encode('x', x[0].value)
      .encode('y', y[0].value)
      .scale('x', {
        nice: true,
      })
      .scale('y', {
        nice: true,
      })
      .interaction('elementHighlight', { background: true })
  }
}
