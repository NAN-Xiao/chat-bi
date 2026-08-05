import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import {
  axisLabel,
  type ChartAxis,
  type ChartData,
  type ChartMountTarget,
} from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { checkIsPercent, formatNumber, getAxesWithFilter } from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { resolveG2ResponsiveStyle } from '@/views/chat/component/charts/g2Responsive.ts'
import {
  RadialPartitionValidationError,
  prepareRadialSlices,
} from '@/views/chat/component/charts/radialPartition.ts'

export interface RadialPartitionChartOptions {
  name: 'pie' | 'donut'
  innerRadius: number
  showPercentage: boolean
}

export class RadialPartitionChart extends BaseG2Chart {
  constructor(
    mountTarget: ChartMountTarget,
    private readonly radialOptions: RadialPartitionChartOptions
  ) {
    super(mountTarget, radialOptions.name)
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)
    const axes = getAxesWithFilter(this.axis)
    const y = axes.y
    const series = axes.series

    if (series.length !== 1 || y.length !== 1 || axes.groupedMultiQuota.length > 1) {
      if (this.radialOptions.name === 'donut') {
        throw new RadialPartitionValidationError(
          series.length !== 1 ? 'missing_category_field' : 'missing_value_field'
        )
      }
      console.debug({ instance: this })
      return
    }

    const prepared = this.radialOptions.showPercentage
      ? prepareRadialSlices(data, series[0].value, y[0].value)
      : undefined
    const checkedData = prepared ? { data: prepared.data, isPercent: false } : checkIsPercent(y, data)
    const percentageField = prepared?.percentageField

    console.debug({
      'render-info': { y, series, data: checkedData, chartType: this.radialOptions.name },
      instance: this,
    })

    const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'structure')
    const coordinate = {
      type: 'theta' as const,
      outerRadius: responsive.outerRadius,
      ...(this.radialOptions.innerRadius > 0
        ? { innerRadius: this.radialOptions.innerRadius }
        : {}),
    }
    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'interval',
      padding: responsive.padding,
      coordinate,
      transform: [{ type: 'stackY' }],
      data: checkedData.data,
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
              text: (datum: ChartData) => {
                const value = `${formatNumber(datum[y[0].value])}${checkedData.isPercent ? '%' : ''}`
                if (!this.radialOptions.showPercentage) {
                  return `${datum[series[0].value]}: ${value}`
                }
                return `${datum[series[0].value]}: ${value} (${formatNumber(datum[percentageField!])}%)`
              },
            },
          ]
        : [],
      tooltip: {
        title: (datum: ChartData) => datum[series[0].value],
        items: [
          (datum: ChartData) => {
            const value = `${formatNumber(datum[y[0].value])}${checkedData.isPercent ? '%' : ''}`
            return {
              name: axisLabel(y[0]),
              value: this.radialOptions.showPercentage
                ? `${value} (${formatNumber(datum[percentageField!])}%)`
                : value,
            }
          },
        ],
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
