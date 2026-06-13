const { formatNumber } = require('./utils')

function getMetricOptions(baseOptions, axis, data) {
  const valueAxes = axis.filter((item) => item.type === 'y')
  const fallbackAxes = axis.filter((item) => !item.hidden)
  const axes = (valueAxes.length > 0 ? valueAxes : fallbackAxes).slice(0, 1)
  const firstAxis = axes[0]
  const firstRow = data[0] || {}
  const rawValue = firstAxis ? firstRow[firstAxis.value] : undefined
  const value = rawValue === null || rawValue === undefined || rawValue === '' ? '-' : formatNumber(rawValue)
  const label = firstAxis ? firstAxis.name || firstAxis.value : ''

  return {
    ...baseOptions,
    type: 'view',
    children: [
      {
        type: 'text',
        style: {
          x: '50%',
          y: '43%',
          text: String(value),
          textAlign: 'center',
          textBaseline: 'middle',
          fontSize: 38,
          fontWeight: 700,
          fill: '#1f2329',
        },
        tooltip: false,
      },
      {
        type: 'text',
        style: {
          x: '50%',
          y: '58%',
          text: String(label),
          textAlign: 'center',
          textBaseline: 'middle',
          fontSize: 16,
          fill: '#646a73',
        },
        tooltip: false,
      },
    ],
  }
}

module.exports = { getMetricOptions }
