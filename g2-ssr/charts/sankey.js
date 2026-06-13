const { formatNumber, getAxesWithFilter, toNumber } = require('./utils')

function getSankeyOptions(baseOptions, axis, data) {
  const axes = getAxesWithFilter(axis)
  if (axes.x.length === 0 || axes.y.length === 0 || axes.series.length === 0) return baseOptions

  const source = axes.x[0]
  const target = axes.series[0]
  const value = axes.y[0]
  const normalizedData = data
    .map((datum) => ({
      ...datum,
      [value.value]: toNumber(datum[value.value]),
    }))
    .filter((datum) => datum[source.value] && datum[target.value] && datum[value.value] > 0)

  return {
    ...baseOptions,
    type: 'sankey',
    data: normalizedData,
    encode: {
      source: source.value,
      target: target.value,
      value: value.value,
      nodeKey: (datum) => datum.key,
      nodeColor: (datum) => datum.key,
      linkColor: (datum) => datum.source?.key,
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
    },
    tooltip: {
      link: {
        title: '',
        items: [
          (datum) => ({
            name: `${datum.source.key} -> ${datum.target.key}`,
            value: formatNumber(datum.value),
          }),
        ],
      },
      node: {
        title: (datum) => datum.key,
        items: [
          (datum) => ({
            name: value.name,
            value: formatNumber(datum.value),
          }),
        ],
      },
    },
  }
}

module.exports = { getSankeyOptions }
