import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'

export class Bar extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'bar')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const x = this.axis.filter((item) => item.type === 'x')
    const y = this.axis.filter((item) => item.type === 'y')
    const series = this.axis.filter((item) => item.type === 'series')

    if (x.length == 0 || y.length == 0) {
      return
    }

    this.chart
      ?.interval()
      .coordinate({ transform: [{ type: 'transpose' }] })
      .data(data)
      .encode('x', x[0].value)
      .encode('y', y[0].value)
      .axis({
        x: { title: x[0].name },
        y: { title: y[0].name },
      })
      .scale('x', {
        nice: true,
      })
      .scale('y', {
        nice: true,
      })
      .interaction('elementHighlight', { background: true })

    if (series.length > 0) {
      this.chart?.encode('color', series[0].value).transform({ type: 'stackY' })
    }
  }
}
