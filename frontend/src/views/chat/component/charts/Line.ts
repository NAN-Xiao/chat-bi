import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'

export class Line extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'line')
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
      ?.data(data)
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

    if (series.length > 0) {
      this.chart?.encode('color', series[0].value)
    }

    this.chart
      ?.line()
      .label({
        text: y[0].value,
        style: {
          dx: -10,
          dy: -12,
        },
        transform: [{ type: 'overlapDodgeY' }, { type: 'exceedAdjust' }, { type: 'overlapHide' }],
      })
      .tooltip((data) => {
        if (series.length > 0) {
          return { name: data[series[0].value], value: data[y[0].value] }
        } else {
          return { name: y[0].name, value: data[y[0].value] }
        }
      })

    this.chart?.point().style('fill', 'white').tooltip(false)
  }
}
