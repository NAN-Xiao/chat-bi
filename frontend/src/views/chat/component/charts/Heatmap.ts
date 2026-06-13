import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
} from '@/views/chat/component/charts/utils.ts'

export class Heatmap extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'heatmap')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)
    if (axes.x.length === 0 || axes.y.length === 0 || axes.series.length === 0) {
      console.debug({ instance: this })
      return
    }

    const x = axes.x
    const y = axes.y
    const series = axes.series
    const _data = checkIsPercent(y, data)

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'cell',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: series[0].value,
        color: y[0].value,
      },
      style: {
        inset: 1,
        radius: 2,
      },
      axis: {
        x: {
          title: false,
          labelAutoHide: true,
          labelAutoRotate: false,
        },
        y: {
          title: false,
          labelAutoHide: true,
        },
      },
      scale: {
        color: {
          range: ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
        },
      },
      legend: {
        color: { position: 'right' },
      },
      labels: this.showLabel
        ? [
            {
              text: (datum: any) =>
                `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
              transform: [{ type: 'contrastReverse' }, { type: 'overlapHide' }],
            },
          ]
        : [],
      tooltip: (datum: any) => ({
        name: `${datum[series[0].value]} / ${datum[x[0].value]}`,
        value: `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
      }),
    } as G2Spec

    this.chart.options(options)
  }
}
