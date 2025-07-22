import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { checkIsPercent } from '@/views/chat/component/charts/utils.ts'

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

    const _data = checkIsPercent(y[0], data)

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'interval',
      data: _data.data,
      coordinate: { transform: [{ type: 'transpose' }] },
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: series.length > 0 ? series[0].value : undefined,
      },
      axis: {
        x: { title: x[0].name },
        y: { title: y[0].name },
      },
      scale: {
        x: {
          nice: true,
        },
        y: {
          nice: true,
        },
      },
      interaction: {
        elementHighlight: { background: true },
      },
      tooltip: (data) => {
        if (series.length > 0) {
          return {
            name: data[series[0].value],
            value: `${data[y[0].value]}${_data.isPercent ? '%' : ''}`,
          }
        } else {
          return { name: y[0].name, value: `${data[y[0].value]}${_data.isPercent ? '%' : ''}` }
        }
      },
      labels: [
        {
          text: (data: any) => `${data[y[0].value]}${_data.isPercent ? '%' : ''}`,
          transform: [
            { type: 'overlapDodgeY' },
            { type: 'contrastReverse' },
            { type: 'overlapHide' },
          ],
        },
      ],
    } as G2Spec

    if (series.length > 0) {
      options.transform = [{ type: 'stackY' }]
    }

    this.chart.options(options)
  }
}
