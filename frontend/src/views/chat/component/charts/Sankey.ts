import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import {
  axisLabel,
  type ChartAxis,
  type ChartData,
  type ChartMountTarget,
} from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { formatNumber, getAxesWithFilter, toNumber } from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'
import { resolveG2ResponsiveStyle } from '@/views/chat/component/charts/g2Responsive.ts'
import { ChartValidationError } from '@/views/chat/component/chartValidation.ts'

const SANKEY_NODE_SEPARATOR = '::'

function findStepField(axis: ChartAxis[], reservedFields: Set<string>): string | undefined {
  return axis.find((item) => {
    if (reservedFields.has(item.value)) {
      return false
    }
    const text = `${item.value} ${item.name || ''}`.toLowerCase()
    return (
      text.includes('path_step') || /(^|[_\s-])step($|[_\s-])/.test(text) || text.includes('步骤')
    )
  })?.value
}

function layeredNodeKey(step: number, label: unknown): string {
  return `${step}${SANKEY_NODE_SEPARATOR}${String(label)}`
}

function nodeLabel(key: unknown): string {
  const text = String(key ?? '')
  const separatorIndex = text.indexOf(SANKEY_NODE_SEPARATOR)
  return separatorIndex >= 0 ? text.slice(separatorIndex + SANKEY_NODE_SEPARATOR.length) : text
}

export class Sankey extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'sankey')
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

    const stepField = findStepField(this.axis, new Set([source.value, target.value, value.value]))
    const sankeyData = stepField
      ? normalizedData.map((datum) => {
          const step = Number(datum[stepField])
          if (!Number.isInteger(step) || step < 0) {
            throw new ChartValidationError('invalid_data')
          }
          return {
            ...datum,
            [source.value]: layeredNodeKey(step, datum[source.value]),
            [target.value]: layeredNodeKey(step + 1, datum[target.value]),
          }
        })
      : normalizedData

    const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'structure')
    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'sankey',
      padding: responsive.padding,
      data: sankeyData,
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
        labelText: this.showLabel ? (datum: any) => nodeLabel(datum.key) : () => '',
        labelFontSize: responsive.structureLabelFontSize,
        labelFill: '#5b6f95',
      },
      tooltip: {
        link: {
          title: '',
          items: [
            (datum: any) => ({
              name: `${nodeLabel(datum.source.key)} -> ${nodeLabel(datum.target.key)}`,
              value: formatNumber(datum.value),
            }),
          ],
        },
        node: {
          title: (datum: any) => nodeLabel(datum.key),
          items: [
            (datum: any) => ({
              name: axisLabel(value),
              value: formatNumber(datum.value),
            }),
          ],
        },
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
