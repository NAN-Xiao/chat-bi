const { checkIsPercent, formatNumber, getAxesWithFilter } = require('./utils')

function getFunnelOptions(baseOptions, axis, data) {
  const axes = getAxesWithFilter(axis)
  if (axes.x.length === 0 || axes.y.length === 0) return baseOptions

  const x = axes.x
  const y = axes.y
  const _data = checkIsPercent(y, data)

  return {
    ...baseOptions,
    type: 'interval',
    data: _data.data,
    encode: {
      x: x[0].value,
      y: y[0].value,
      color: x[0].value,
      shape: 'funnel',
    },
    transform: [{ type: 'symmetryY' }],
    axis: false,
    legend: false,
    tooltip: (datum) => ({
      name: datum[x[0].value],
      value: `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
    }),
  }
}

module.exports = { getFunnelOptions }
