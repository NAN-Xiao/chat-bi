import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { formatNumber, getAxesWithFilter, toNumber } from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'

export class Sankey extends BaseG2Chart {
  constructor(id: string) {
    super(id, 'sankey')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)
    if (axes.x.length === 0 || axes.y.length === 0 || axes.series.length === 0) {
      console.debug({ instance: this })
      return
    }

    const source = axes.x[0]
    const target = axes.series[0]
    const value = axes.y[0]
    const normalizedData = data
      .map((datum) => ({
        ...datum,
        [value.value]: toNumber(datum[value.value]),
      }))
      .filter((datum) => datum[source.value] && datum[target.value] && datum[value.value] > 0)

    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'sankey',
      data: normalizedData,
      encode: {
        source: source.value,
        target: target.value,
        value: value.value,
        nodeKey: (datum: any) => datum.key,
        nodeColor: (datum: any) => datum.key,
        linkColor: (datum: any) => datum.source?.key,
      },
      layout: {
        nodeAlign: 'justify',
        nodePadding: 0.03,
      },
      style: {
        nodeStroke: '#fff',
        nodeLineWidth: 1,
        linkFillOpacity: 0.36,
        labelFontSize: 11,
        labelFill: '#5b6f95',
      },
      tooltip: {
        link: {
          title: '',
          items: [
            (datum: any) => ({
              name: `${datum.source.key} -> ${datum.target.key}`,
              value: formatNumber(datum.value),
            }),
          ],
        },
        node: {
          title: (datum: any) => datum.key,
          items: [
            (datum: any) => ({
              name: value.name,
              value: formatNumber(datum.value),
            }),
          ],
        },
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
