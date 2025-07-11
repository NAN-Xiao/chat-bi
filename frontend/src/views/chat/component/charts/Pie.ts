import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { endsWith, filter, replace } from 'lodash-es'

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

    // %
    const _data = []
    let isPercent = false
    const notEmptyData = filter(
      data,
      (d) =>
        d &&
        d[y[0].value] !== null &&
        d[y[0].value] !== undefined &&
        d[y[0].value] !== 0 &&
        d[y[0].value] !== '0'
    )
    if (notEmptyData.length > 0) {
      const v = notEmptyData[0][y[0].value] + ''
      if (endsWith(v.trim(), '%')) {
        isPercent = true
      }
    }
    for (let i = 0; i < data.length; i++) {
      const v = data[i]
      const _v = { ...v }
      if (isPercent) {
        const formatValue = replace(v[y[0].value], '%', '')
        _v[y[0].value] = Number(formatValue)
      }
      _data.push(_v)
    }

    const options: G2Spec = {
      ...this.chart.options(),
      type: 'interval',
      coordinate: { type: 'theta', outerRadius: 0.8 },
      transform: [{ type: 'stackY' }],
      data: _data,
      encode: {
        y: y[0].value,
        color: series[0].value,
      },
      legend: {
        color: { position: 'bottom', layout: { justifyContent: 'center' } },
      },
      labels: [
        {
          position: 'outside',
          text: (data: any) =>
            `${data[series[0].value]}: ${data[y[0].value]}${isPercent ? '%' : ''}`,
        },
      ],
      tooltip: (data) => {
        return { name: y[0].name, value: `${data[y[0].value]}${isPercent ? '%' : ''}` }
      },
    }

    this.chart.options(options)
  }
}
