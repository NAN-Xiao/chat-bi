import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData, ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatCategoryAxisLabel,
  formatNumber,
  getAxesWithFilter,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import {
  resolveCategoryAxisResponsiveOptions,
  resolveG2ResponsiveStyle,
} from '@/views/chat/component/charts/g2Responsive.ts'

export class Heatmap extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'heatmap')
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

    const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'cartesian')
    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'cell',
      padding: responsive.padding,
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
          labelFormatter: formatCategoryAxisLabel,
          ...resolveCategoryAxisResponsiveOptions(responsive),
        },
        y: {
          title: false,
          labelFontSize: responsive.axisLabelFontSize,
          labelAutoHide: true,
        },
      },
      scale: {
        x: {
          type: 'band',
        },
        color: {
          range: ['#f7fbff', '#dbe8ff', '#9bbcff', '#4c84ff', '#1d4ed8'],
        },
      },
      legend: {
        color: {
          position: responsive.legendPosition,
          itemLabelFontSize: responsive.legendItemFontSize,
        },
      },
      labels: this.showLabel && responsive.showPointLabels
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
    } as G2Spec)

    this.chart.options(options)
  }
}
