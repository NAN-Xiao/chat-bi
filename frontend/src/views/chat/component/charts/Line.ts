import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  buildMixedUnitComboOptions,
  buildMixedUnitData,
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
  getTrendSummary,
  isBaselinePercentTrend,
  processMultiQuotaData,
  sortDataByXAxis,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { createTrendInsight } from '@/views/chat/component/charts/insight.ts'

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
      data: sortDataByXAxis(data, axes.x[0]),
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

    const multiQuota =
      axes.multiQuota.length > 0 ? axes.multiQuota : axes.y.map((item) => item.value)
    if (axes.series.length === 0 && multiQuota.length > 1) {
      config = processMultiQuotaData(axes.x, config.y, multiQuota, axes.multiQuotaName, config.data)
    }

    const x = axes.x
    const y = config.y
    const series = config.series

    const _data = checkIsPercent(y, config.data)
    const baselinePercentTrend = _data.isPercent && isBaselinePercentTrend(_data.data, y[0])
    const insightEnabled =
      this.insightsEnabled && !baselinePercentTrend && series.length === 0 && _data.data.length > 1
    const trendSummary = insightEnabled ? getTrendSummary(_data.data, y[0]) : undefined
    const latestDatum = trendSummary?.latest
    const maxDatum = trendSummary?.max

    if (insightEnabled && trendSummary) {
      this.setInsight(
        createTrendInsight({
          valueLabel: y[0].name || y[0].value,
          latestValue: trendSummary.latestValue,
          changePercent: trendSummary.changePercent,
          maxLabel: maxDatum ? String(maxDatum[x[0].value] ?? '') : undefined,
          maxValue: trendSummary.maxValue,
          isPercent: _data.isPercent,
        })
      )
    } else {
      this.clearInsight()
    }

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
          labelFontSize: 12,
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
            : insightEnabled
              ? [
                  {
                    text: (data: any) => {
                      if (data === latestDatum) {
                        return `最新 ${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`
                      }
                      if (data === maxDatum && maxDatum !== latestDatum) {
                        return `最高 ${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`
                      }
                      return ''
                    },
                    style: {
                      dx: -10,
                      dy: -12,
                      fontSize: 12,
                      fontWeight: 600,
                      fill: '#1b2a41',
                    },
                    transform: [{ type: 'exceedAdjust' }, { type: 'overlapHide' }],
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
