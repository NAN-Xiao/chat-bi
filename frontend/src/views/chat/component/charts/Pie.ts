import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import { axisLabel, type ChartAxis, type ChartData, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { checkIsPercent, formatNumber, getAxesWithFilter } from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { resolveG2ResponsiveStyle } from '@/views/chat/component/charts/g2Responsive.ts'

export class Pie extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'pie')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)
    const { y, series } = getAxesWithFilter(this.axis)

    if (series.length == 0 || y.length == 0) {
      console.debug({ instance: this })
      return
    }

    const _data = checkIsPercent(y, data)

    console.debug({ 'render-info': { y: y, series: series, data: _data }, instance: this })

    const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'structure')
    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'interval',
      padding: responsive.padding,
      coordinate: { type: 'theta', outerRadius: responsive.outerRadius },
      transform: [{ type: 'stackY' }],
      data: _data.data,
      encode: {
        y: y[0].value,
        color: series[0].value,
      },
      scale: {
        x: {
          nice: true,
        },
        y: {
          type: 'linear',
        },
      },
      legend: {
        color: {
          position: responsive.legendPosition,
          itemLabelFontSize: responsive.legendItemFontSize,
          layout: { justifyContent: 'center' },
        },
      },
      animate: { enter: { type: 'waveIn' } },
      labels: this.showLabel && responsive.showPointLabels
        ? [
            {
              position: 'spider',
              fontSize: responsive.structureLabelFontSize,
              text: (data: any) => {
                return `${data[series[0].value]}: ${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`
              },
            },
          ]
        : [],
      tooltip: {
        title: (data: any) => data[series[0].value],
        items: [
          (data: any) => {
            return {
              name: axisLabel(y[0]),
              value: `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
            }
          },
        ],
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
