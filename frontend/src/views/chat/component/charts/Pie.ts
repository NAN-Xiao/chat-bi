import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'

export class Pie extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'pie')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)
    const y = this.axis.filter((item) => item.type === 'y')
    const series = this.axis.filter((item) => item.type === 'series')

    if (series.length == 0 || y.length == 0) {
      return
    }

    this.chart.coordinate({ type: 'theta', outerRadius: 0.8 })

    this.chart
      ?.interval()
      .transform({ type: 'stackY' })
      .data(data)
      .encode('y', y[0].value)
      .encode('color', series[0].value)
      .legend('color', { position: 'bottom', layout: { justifyContent: 'center' } })
      .label({
        position: 'outside',
        text: (data: any) => `${data[series[0].value]}: ${data[y[0].value]}`,
      })
      .tooltip((data) => {
        return { name: y[0].name, value: data[y[0].value] }
      })
  }
}
