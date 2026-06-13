import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
} from '@/views/chat/component/charts/utils.ts'

export class Scatter extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'scatter')
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
    const series = axes.series
    const _data = checkIsPercent(y, data)

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'point',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: series.length > 0 ? series[0].value : undefined,
        size: 4,
      },
      style: {
        fillOpacity: 0.72,
        lineWidth: 1,
      },
      axis: {
        x: {
          title: false,
          labelFontSize: 12,
          labelAutoHide: true,
          labelAutoRotate: false,
        },
        y: {
          title: false,
          labelFormatter: (value: any) => String(formatNumber(value)),
        },
      },
      scale: {
        x: { nice: true },
        y: { nice: true, type: 'linear' },
      },
      interaction: {
        tooltip: { shared: false },
      },
      labels: this.showLabel
        ? [
            {
              text: (datum: any) =>
                `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
              transform: [{ type: 'overlapHide' }],
            },
          ]
        : [],
      tooltip: (datum: any) => ({
        name: series.length > 0 ? datum[series[0].value] : y[0].name,
        value: `${x[0].name}: ${formatNumber(datum[x[0].value])}, ${y[0].name}: ${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
      }),
    } as G2Spec

    this.chart.options(options)
  }
}
