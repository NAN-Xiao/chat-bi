import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  buildMixedUnitComboOptions,
  buildMixedUnitData,
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
  processMultiQuotaData,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'

export class Line extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'line')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)

    if (axes.x.length == 0 || axes.y.length == 0) {
      console.debug({ instance: this })
      return
    }

    let config = {
      data: data,
      y: axes.y,
      series: axes.series,
    }

    const mixedUnitData = buildMixedUnitData(axes.x, axes.y, config.data)
    if (mixedUnitData) {
      const options = buildMixedUnitComboOptions(
        this.chart.options(),
        axes.x[0],
        mixedUnitData,
        this.showLabel
      )
      this.chart.options(options)
      return
    }

    const multiQuota = axes.multiQuota.length > 0 ? axes.multiQuota : axes.y.map((item) => item.value)
    if (axes.series.length === 0 && multiQuota.length > 1) {
      config = processMultiQuotaData(
        axes.x,
        config.y,
        multiQuota,
        axes.multiQuotaName,
        config.data
      )
    }

    const x = axes.x
    const y = config.y
    const series = config.series

    const _data = checkIsPercent(y, config.data)

    console.debug({ 'render-info': { x: x, y: y, series: series, data: _data }, instance: this })

    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'view',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: series.length > 0 ? series[0].value : undefined,
      },
      axis: {
        x: {
          title: false, // x[0].name,
          labelFontSize: 11,
          labelAutoHide: {
            type: 'hide',
            keepHeader: true,
            keepTail: true,
          },
          labelAutoRotate: false,
          labelAutoWrap: true,
          labelAutoEllipsis: true,
        },
        y: {
          title: false, // y[0].name,
          labelFormatter: (value: any) => {
            return String(formatNumber(value))
          },
        },
      },
      scale: {
        x: {
          nice: true,
        },
        y: {
          nice: true,
          type: 'linear',
        },
      },
      children: [
        {
          type: 'area',
          encode: {
            shape: 'smooth',
          },
          style: {
            fillOpacity: 0.09,
          },
          tooltip: false,
        },
        {
          type: 'line',
          encode: {
            shape: 'smooth',
          },
          labels: this.showLabel
            ? [
                {
                  text: (data: any) => {
                    const value = data[y[0].value]
                    if (value === undefined || value === null) {
                      return ''
                    }
                    return `${formatNumber(value)}${_data.isPercent ? '%' : ''}`
                  },
                  style: {
                    dx: -10,
                    dy: -12,
                  },
                  transform: [
                    { type: 'contrastReverse' },
                    { type: 'exceedAdjust' },
                    { type: 'overlapHide' },
                  ],
                },
              ]
            : [],
          tooltip: (data: any) => {
            if (series.length > 0) {
              return {
                name: data[series[0].value],
                value: `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
              }
            } else {
              return {
                name: y[0].name,
                value: `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
              }
            }
          },
        },
        {
          type: 'point',
          style: {
            fill: 'white',
            lineWidth: 1.8,
          },
          encode: {
            size: 2.2,
          },
          tooltip: false,
        },
      ],
    } as G2Spec)

    this.chart.options(options)
  }
}
