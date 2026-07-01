import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import { axisLabel, type ChartAxis, type ChartData, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  buildMixedUnitComboOptions,
  buildMixedUnitData,
  checkIsPercent,
  formatNumber,
  formatTooltipValue,
  getAxesWithFilter,
  processGroupedMultiQuotaData,
  processMultiQuotaData,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { buildForecastRows } from '@/views/chat/component/charts/forecast.ts'

export class Area extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'area')
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
    } else if (axes.series.length > 0 && axes.groupedMultiQuota.length > 1) {
      config = processGroupedMultiQuotaData(
        axes.x,
        axes.groupedMultiQuota,
        axes.series,
        config.data
      )
    }

    const x = axes.x
    const y = config.y
    const series = config.series

    const _data = checkIsPercent(y, config.data)
    const forecastData = buildForecastRows({
      data: _data.data,
      xField: x[0].value,
      yField: y[0].value,
      seriesField: series[0]?.value,
      forecast: this.forecast,
      isPercent: _data.isPercent,
    })
    const shouldStack = series.length > 0

    console.debug({ 'render-info': { x: x, y: y, series: series, data: _data, forecastData }, instance: this })

    const areaLabels = this.showLabel
      ? [
          {
            text: (datum: ChartData) => {
              const value = datum[y[0].value]
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
      : []

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
          title: false,
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
          title: false,
          labelFormatter: (value: any) => {
            return String(formatNumber(value))
          },
        },
      },
      scale: {
        x: {
          nice: forecastData.length ? false : true,
        },
        y: {
          nice: true,
          type: 'linear',
        },
      },
      interaction: {
        tooltip: { series: series.length > 0, shared: true },
      },
      children: [
        {
          type: 'area',
          transform: shouldStack ? [{ type: 'stackY' }] : undefined,
          style: {
            fillOpacity: 0.78,
          },
          labels: areaLabels,
          tooltip: (datum: ChartData) => {
            if (series.length > 0) {
              return {
                name: datum[series[0].value],
                value: formatTooltipValue(datum[y[0].value], _data.isPercent ? '%' : ''),
              }
            }
            return {
              name: axisLabel(y[0]),
              value: formatTooltipValue(datum[y[0].value], _data.isPercent ? '%' : ''),
            }
          },
        },
        ...(forecastData.length
          ? [
              {
                type: 'line',
                data: forecastData,
                encode: {
                  x: x[0].value,
                  y: y[0].value,
                  color: series.length > 0 ? series[0].value : undefined,
                },
                style: {
                  lineDash: [6, 5],
                  lineWidth: 1.8,
                  strokeOpacity: 0.9,
                },
                tooltip: (datum: ChartData) => {
                  if (series.length > 0) {
                    return {
                      name: `${datum[series[0].value]} 预测`,
                      value: formatTooltipValue(datum[y[0].value], _data.isPercent ? '%' : ''),
                    }
                  }
                  return {
                    name: `${axisLabel(y[0])} 预测`,
                    value: formatTooltipValue(datum[y[0].value], _data.isPercent ? '%' : ''),
                  }
                },
              },
            ]
          : []),
      ],
    } as G2Spec)

    this.chart.options(options)
  }
}
