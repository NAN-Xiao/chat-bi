import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import { axisLabel, type ChartAxis, type ChartData, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import {
  buildMixedUnitComboOptions,
  buildMixedUnitData,
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
  processGroupedMultiQuotaData,
  processMultiQuotaData,
} from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'

export class Column extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'column')
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

    console.debug({ 'render-info': { x: x, y: y, series: series, data: _data }, instance: this })

    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'interval',
      data: _data.data,
      encode: {
        x: x[0].value,
        y: y[0].value,
        color: series.length > 0 ? series[0].value : undefined,
      },
      style: {
        radiusTopLeft: (d: ChartData) => {
          if (d[y[0].value] && d[y[0].value] > 0) {
            return 4
          }
          return 0
        },
        radiusTopRight: (d: ChartData) => {
          if (d[y[0].value] && d[y[0].value] > 0) {
            return 4
          }
          return 0
        },
        radiusBottomLeft: (d: ChartData) => {
          if (d[y[0].value] && d[y[0].value] < 0) {
            return 4
          }
          return 0
        },
        radiusBottomRight: (d: ChartData) => {
          if (d[y[0].value] && d[y[0].value] < 0) {
            return 4
          }
          return 0
        },
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
      interaction: {
        elementHighlight: { background: true, region: true },
        tooltip: { series: series.length > 0, shared: true },
      },
      tooltip: (data: any) => {
        if (series.length > 0) {
          return {
            name: data[series[0].value],
            value: `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
          }
        } else {
          return {
            name: axisLabel(y[0]),
            value: `${formatNumber(data[y[0].value])}${_data.isPercent ? '%' : ''}`,
          }
        }
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
              position: (data: any) => {
                if (data[y[0].value] < 0) {
                  return 'bottom'
                }
                return 'top'
              },
              transform: [
                { type: 'contrastReverse' },
                { type: 'exceedAdjust' },
                { type: 'overlapHide' },
              ],
            },
          ]
        : [],
    } as G2Spec)

    if (series.length > 0) {
      options.transform = [{ type: 'stackY' }]
    }

    this.chart.options(options)
  }
}
