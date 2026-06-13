const { formatNumber, getAxesWithFilter, toNumber } = require('./utils')

function buildTreemapData(data, category, value, group) {
  if (!group) {
    return {
      name: 'root',
      children: data.map((datum) => ({
        name: String(datum[category.value] ?? '-'),
        value: toNumber(datum[value.value]),
      })),
    }
  }

  const groupMap = new Map()
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

function getTreemapOptions(baseOptions, axis, data) {
  const axes = getAxesWithFilter(axis)
  if (axes.x.length === 0 || axes.y.length === 0) return baseOptions

  const category = axes.x[0]
  const value = axes.y[0]
  const group = axes.series[0]
  const treeData = buildTreemapData(data, category, value, group)

  return {
    ...baseOptions,
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
      labelFill: '#1f2329',
      labelFontSize: 11,
    },
    tooltip: {
      title: (datum) => datum.path?.slice(1).join(' / ') || datum.data?.name,
      items: [
        (datum) => ({
          name: value.name,
          value: formatNumber(datum.value),
        }),
      ],
    },
  }
}

module.exports = { getTreemapOptions }
