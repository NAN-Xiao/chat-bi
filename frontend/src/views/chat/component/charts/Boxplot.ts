import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import {
  axisLabel,
  type ChartAxis,
  type ChartData,
  type ChartMountTarget,
} from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { i18n } from '@/i18n'
import { prepareBoxplotData } from './boxplotData.ts'
import { formatCategoryAxisLabel, formatNumber } from './utils.ts'
import { withChartThemeOptions } from './theme.ts'
import { resolveCategoryAxisResponsiveOptions, resolveG2ResponsiveStyle } from './g2Responsive.ts'

export class Boxplot extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'boxplot')
  }

  init(axis: ChartAxis[], data: ChartData[]) {
    super.init(axis, data)
    const { boxes, outliers } = prepareBoxplotData(axis, data)
    const seriesAxis = axis.find((item) => item.type === 'series' && !item.hidden)
    const valueAxis = axis.find((item) => item.type === 'y' && !item.hidden)
    const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'cartesian')
    const seriesDomain = [...new Set(boxes.map((box) => box.series))]
    const encode = { x: 'category', ...(seriesAxis ? { color: 'series', series: 'series' } : {}) }
    const label = (key: string) => i18n.global.t(`chat.boxplot.${key}`)
    this.chart.options(
      withChartThemeOptions({
        type: 'view',
        padding: responsive.padding,
        scale: {
          x: { type: 'band', domain: [...new Set(boxes.map((box) => box.category))], padding: 0.4 },
          y: { type: 'linear', nice: true, zero: false },
          ...(seriesAxis
            ? {
                color: { domain: seriesDomain },
                series: { type: 'band', domain: seriesDomain, paddingInner: 0.2 },
              }
            : {}),
        },
        axis: {
          x: {
            title: false,
            labelFormatter: formatCategoryAxisLabel,
            ...resolveCategoryAxisResponsiveOptions(responsive),
          },
          y: this.hideValueAxis
            ? false
            : {
                title: false,
                labelFontSize: responsive.axisLabelFontSize,
                labelFormatter: (value: unknown) => String(formatNumber(value)),
              },
        },
        legend: {
          color: seriesAxis
            ? {
                title: false,
                position: responsive.legendPosition,
                itemLabelFontSize: responsive.legendItemFontSize,
              }
            : false,
        },
        interaction: { tooltip: { shared: false } },
        children: [
          {
            type: 'box',
            data: boxes,
            encode: { ...encode, y: ['low', 'q1', 'median', 'q3', 'high'] },
            style: { fillOpacity: 0.35, lineWidth: 1.5 },
            labels: this.showLabel
              ? [
                  {
                    text: (datum: any) => String(formatNumber(datum.median)),
                    transform: [{ type: 'overlapHide' }],
                  },
                ]
              : [],
            tooltip: {
              title: (datum: any) =>
                seriesAxis ? `${datum.category} / ${datum.series}` : datum.category,
              items: ['high', 'q3', 'median', 'q1', 'low', 'count'].map((field) => ({
                field,
                name: label(field),
                valueFormatter: (value: unknown) => String(formatNumber(value)),
              })),
            },
          },
          {
            type: 'point',
            data: outliers,
            encode: { ...encode, y: 'value', size: 3 },
            style: { fillOpacity: 0.8 },
            tooltip: {
              title: (datum: any) =>
                seriesAxis ? `${datum.category} / ${datum.series}` : datum.category,
              items: [
                {
                  field: 'value',
                  name: `${label('outlier')} · ${axisLabel(valueAxis)}`,
                  valueFormatter: (value: unknown) => String(formatNumber(value)),
                },
              ],
            },
          },
        ],
      } as G2Spec)
    )
  }
}
