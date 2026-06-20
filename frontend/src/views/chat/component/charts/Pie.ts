import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  checkIsPercent,
  formatMetricValue,
  formatNumber,
  formatPercentValue,
  getAxesWithFilter,
  getSeriesSummary,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { createCenterLabel } from '@/views/chat/component/charts/insight.ts'

export class Pie extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'pie')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)
    const { y, series } = getAxesWithFilter(this.axis)

    if (series.length == 0 || y.length == 0) {
      console.debug({ instance: this })
      return
    }

    const _data = checkIsPercent(y, data)
    const summary = this.insightsEnabled ? getSeriesSummary(_data.data, series[0], y[0]) : undefined
    const summaryMap = new Map(summary?.items.map((item) => [item.name, item]) ?? [])
    const labelFormatter = (value: any) => {
      const item = summaryMap.get(String(value))
      if (!item) {
        return String(value)
      }
      return `${value} ${formatPercentValue(item.percent)} | ${formatMetricValue(item.value, { isPercent: _data.isPercent })}`
    }

    if (summary && summary.items.length > 0) {
      this.setChartOverlay(
        createCenterLabel({
          title: summary.valueLabel,
          value: formatMetricValue(summary.total, { isPercent: _data.isPercent }),
          subTitle: '总计',
        })
      )
    } else {
      this.clearChartOverlay()
    }
    this.clearInsight()

    console.debug({ 'render-info': { y: y, series: series, data: _data }, instance: this })

    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'interval',
      coordinate: {
        type: 'theta',
        innerRadius: this.insightsEnabled ? 0.58 : 0,
        outerRadius: 0.82,
      },
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
          position: this.insightsEnabled ? 'right' : 'bottom',
          layout: this.insightsEnabled
            ? { justifyContent: 'center', alignItems: 'center' }
            : { justifyContent: 'center' },
          labelFormatter: this.insightsEnabled ? labelFormatter : undefined,
        },
      },
      animate: { enter: { type: 'waveIn' } },
      labels: this.showLabel
        ? [
            {
              position: 'spider',
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
            const item = summaryMap.get(String(data[series[0].value]))
            return {
              name: y[0].name,
              value: item
                ? `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''} (${formatPercentValue(item.percent)})`
                : `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
            }
          },
        ],
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
