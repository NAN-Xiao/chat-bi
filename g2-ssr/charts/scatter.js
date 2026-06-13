const { checkIsPercent, formatNumber, getAxesWithFilter } = require('./utils')

function getScatterOptions(baseOptions, axis, data) {
  const axes = getAxesWithFilter(axis)
  if (axes.x.length === 0 || axes.y.length === 0) return baseOptions

  const x = axes.x
  const y = axes.y
  const series = axes.series
  const _data = checkIsPercent(y, data)

  return {
    ...baseOptions,
    type: 'point',
    data: _data.data,
    encode: {
      x: x[0].value,
      y: y[0].value,
      color: series.length > 0 ? series[0].value : undefined,
      size: 4,
    },
    style: {
      fillOpacity: 0.72,
      lineWidth: 1,
    },
    axis: {
      x: {
        title: false,
        labelFontSize: 12,
        labelAutoHide: true,
        labelAutoRotate: false,
      },
      y: {
        title: false,
        labelFormatter: (value) => String(formatNumber(value)),
      },
    },
    scale: {
      x: { nice: true },
      y: { nice: true, type: 'linear' },
    },
    tooltip: (datum) => ({
      name: series.length > 0 ? datum[series[0].value] : y[0].name,
      value: `${x[0].name}: ${formatNumber(datum[x[0].value])}, ${y[0].name}: ${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
    }),
  }
}

module.exports = { getScatterOptions }
