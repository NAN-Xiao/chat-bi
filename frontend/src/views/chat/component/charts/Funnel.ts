import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
} from '@/views/chat/component/charts/utils.ts'

export class Funnel extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'funnel')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)
    if (axes.x.length === 0 || axes.y.length === 0) {
      console.debug({ instance: this })
      return
    }

    const x = axes.x
    const y = axes.y
    const _data = checkIsPercent(y, data)

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'interval',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: x[0].value,
        shape: 'funnel',
      },
      transform: [{ type: 'symmetryY' }],
      axis: false,
      legend: false,
      labels: this.showLabel
        ? [
            {
              text: (datum: any) =>
                `${datum[x[0].value]} ${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
              position: 'inside',
              transform: [{ type: 'contrastReverse' }, { type: 'overlapHide' }],
            },
          ]
        : [],
      tooltip: (datum: any) => ({
        name: datum[x[0].value],
        value: `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
      }),
    } as G2Spec

    this.chart.options(options)
  }
}
