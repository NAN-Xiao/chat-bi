import { BaseG2Chart } from '@/views/chat/component/BaseG2Chart.ts'
import { axisLabel, type ChartAxis, type ChartData, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { formatNumber, getAxesWithFilter, toNumber } from '@/views/chat/component/charts/utils.ts'
import { withChartThemeOptions } from '@/views/chat/component/charts/theme.ts'

interface TreeNode {
  name: string
  value?: number
  children?: TreeNode[]
}

function buildTreemapData(
  data: Array<ChartData>,
  category: ChartAxis,
  value: ChartAxis,
  group?: ChartAxis
): TreeNode {
  if (!group) {
    return {
      name: 'root',
      children: data.map((datum) => ({
        name: String(datum[category.value] ?? '-'),
        value: toNumber(datum[value.value]),
      })),
    }
  }

  const groupMap = new Map<string, TreeNode[]>()
  data.forEach((datum) => {
    const groupName = String(datum[group.value] ?? '-')
    const children = groupMap.get(groupName) || []
    children.push({
      name: String(datum[category.value] ?? '-'),
      value: toNumber(datum[value.value]),
    })
    groupMap.set(groupName, children)
  })

  return {
    name: 'root',
    children: Array.from(groupMap.entries()).map(([name, children]) => ({
      name,
      children,
    })),
  }
}

export class Treemap extends BaseG2Chart {
  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'treemap')
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    super.init(axis, data)

    const axes = getAxesWithFilter(this.axis)
    if (axes.x.length === 0 || axes.y.length === 0) {
      console.debug({ instance: this })
      return
    }

    const category = axes.x[0]
    const value = axes.y[0]
    const group = axes.series[0]
    const treeData = buildTreemapData(data, category, value, group)

    const options: G2Spec = withChartThemeOptions({
      ...this.chart.options(),
      type: 'treemap',
      data: treeData,
      encode: {
        value: 'value',
      },
      layout: {
        paddingInner: 2,
        paddingOuter: 1,
      },
      style: {
        labelFill: '#15233b',
        labelFontSize: 11,
      },
      labels: this.showLabel
        ? [
            {
              text: (datum: any) => `${datum.data.name}\n${formatNumber(datum.value)}`,
              position: 'inside',
              wordWrap: true,
              maxLines: 2,
            },
          ]
        : [],
      tooltip: {
        title: (datum: any) => datum.path?.slice(1).join(' / ') || datum.data?.name,
        items: [
          (datum: any) => ({
            name: axisLabel(value),
            value: formatNumber(datum.value),
          }),
        ],
      },
    } as G2Spec)

    this.chart.options(options)
  }
}
