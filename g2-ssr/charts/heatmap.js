const { checkIsPercent, formatNumber, getAxesWithFilter } = require('./utils')

function getHeatmapOptions(baseOptions, axis, data) {
  const axes = getAxesWithFilter(axis)
  if (axes.x.length === 0 || axes.y.length === 0 || axes.series.length === 0) return baseOptions

  const x = axes.x
  const y = axes.y
  const series = axes.series
  const _data = checkIsPercent(y, data)

  return {
    ...baseOptions,
    type: 'cell',
    data: _data.data,
    encode: {
      x: x[0].value,
      y: series[0].value,
      color: y[0].value,
    },
    style: {
      inset: 1,
      radius: 2,
    },
    axis: {
      x: {
        title: false,
        labelAutoHide: true,
        labelAutoRotate: false,
      },
      y: {
        title: false,
        labelAutoHide: true,
      },
    },
    scale: {
      color: {
        range: ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
      },
    },
    legend: {
      color: { position: 'right' },
    },
    tooltip: (datum) => ({
      name: `${datum[series[0].value]} / ${datum[x[0].value]}`,
      value: `${formatNumber(datum[y[0].value])}${_data.isPercent ? '%' : ''}`,
    }),
  }
}

module.exports = { getHeatmapOptions }
