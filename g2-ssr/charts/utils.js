const { endsWith, replace } = require('lodash')

const AUTO_VALUE_FIELD = 'zhishu_auto_quota'
const AUTO_SERIES_FIELD = 'zhishu_auto_series'
const AUTO_PERCENT_FIELD = 'zhishu_auto_is_percent'

const PERCENT_KEYWORDS = [
  'rate',
  'ratio',
  'percent',
  'pct',
  'retention',
  'conversion',
  '留存',
  '转化率',
  '付费率',
  '流失率',
  '占比',
  '比例',
  '百分',
  '%',
]

const AVERAGE_KEYWORDS = [
  'avg',
  'average',
  'mean',
  'arpu',
  'arppu',
  'per user',
  'per payer',
  'per pay',
  '平均',
  '人均',
  '每用户',
  '每付费',
  '单均',
  '客单',
]

/**
 * 为数值添加千分符，保持原有小数位数不变
 * 纯字符串处理，避免精度丢失
 * 支持：正负整数、小数、字符串格式的数值
 */
function formatNumber(value) {
  if (value === null || value === undefined || value === '') {
    return value
  }

  let str
  if (typeof value === 'string') {
    str = value.trim()
  } else if (typeof value === 'number') {
    str = String(value)
  } else {
    return value
  }

  const match = str.match(/^([+-])?(\d+)(\.(\d+))?$/)
  if (!match) {
    return value
  }

  const sign = match[1] || ''
  const intPart = match[2]
  const decPart = match[3] || ''

  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')

  return sign + formattedInt + decPart
}

function toNumber(value) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0
  }
  if (typeof value !== 'string') {
    return 0
  }
  const normalized = value.trim().replace(/,/g, '').replace(/%$/, '')
  if (!normalized) {
    return 0
  }
  const numValue = Number(normalized)
  return Number.isFinite(numValue) ? numValue : 0
}

function isBlankValue(value) {
  return value === null || value === undefined || value === ''
}

function toNullableNumber(value, multiplier = 1) {
  if (isBlankValue(value)) {
    return null
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value * multiplier : null
  }
  if (typeof value !== 'string') {
    return null
  }

  const normalized = value.trim().replace(/,/g, '').replace(/%$/, '')
  if (!normalized) {
    return null
  }

  const numValue = Number(normalized)
  return Number.isFinite(numValue) ? numValue * multiplier : null
}

function axisText(axis) {
  return `${axis.name || ''} ${axis.value || ''}`.toLowerCase()
}

function isAverageAxis(axis) {
  const text = axisText(axis)
  return AVERAGE_KEYWORDS.some((keyword) => text.includes(keyword))
}

function isPercentAxis(axis, data) {
  const text = axisText(axis)
  if (PERCENT_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return true
  }

  return data.some((datum) => {
    const value = datum && datum[axis.value]
    return typeof value === 'string' && endsWith(value.trim(), '%')
  })
}

function getPercentMultiplier(axis, data) {
  const values = data.map((datum) => datum && datum[axis.value]).filter((value) => !isBlankValue(value))

  if (values.some((value) => typeof value === 'string' && endsWith(value.trim(), '%'))) {
    return 1
  }

  const numbers = values.map((value) => toNullableNumber(value)).filter((value) => value !== null)

  if (numbers.length === 0) {
    return 1
  }

  const minValue = Math.min(...numbers)
  const maxAbsValue = Math.max(...numbers.map((value) => Math.abs(value)))
  return minValue >= 0 && maxAbsValue <= 1 ? 100 : 1
}

function buildMetricRows(x, metricAxes, data, percent) {
  const rows = []
  const percentMultipliers = new Map(
    metricAxes.map((axis) => [axis.value, percent ? getPercentMultiplier(axis, data) : 1]),
  )

  for (const datum of data) {
    for (const metricAxis of metricAxes) {
      const value = toNullableNumber(datum[metricAxis.value], percentMultipliers.get(metricAxis.value))
      if (value === null) {
        continue
      }

      const row = {
        [AUTO_VALUE_FIELD]: value,
        [AUTO_SERIES_FIELD]: metricAxis.name,
        [AUTO_PERCENT_FIELD]: percent,
      }
      for (const xAxis of x) {
        row[xAxis.value] = datum[xAxis.value]
      }
      rows.push(row)
    }
  }

  return rows
}

function buildMixedUnitData(x, y, data) {
  if (x.length === 0 || y.length < 2 || data.length === 0) {
    return undefined
  }

  const percentAxes = y.filter((axis) => isPercentAxis(axis, data))
  const rawCountAxes = y.filter((axis) => !percentAxes.includes(axis))
  const averageAxes = rawCountAxes.filter((axis) => isAverageAxis(axis))
  const nonAverageAxes = rawCountAxes.filter((axis) => !isAverageAxis(axis))
  const countAxes =
    percentAxes.length > 0 && averageAxes.length > 0 && nonAverageAxes.length > 0
      ? nonAverageAxes
      : rawCountAxes

  if (percentAxes.length === 0 || countAxes.length === 0) {
    return undefined
  }

  const countData = buildMetricRows(x, countAxes, data, false)
  const percentData = buildMetricRows(x, percentAxes, data, true)

  if (countData.length === 0 || percentData.length === 0) {
    return undefined
  }

  return {
    countAxes,
    percentAxes,
    countData,
    percentData,
    valueField: AUTO_VALUE_FIELD,
    seriesField: AUTO_SERIES_FIELD,
  }
}

function getAxesWithFilter(axes) {
  const groups = {
    x: [],
    y: [],
    series: [],
    multiQuota: [],
    multiQuotaName: undefined,
  }

  // 分组
  axes.forEach((axis) => {
    if (axis.type === 'x') groups.x.push(axis)
    else if (axis.type === 'y') groups.y.push(axis)
    else if (axis.type === 'series') groups.series.push(axis)
    else if (axis.type === 'other-info') groups.multiQuotaName = axis.value
  })

  // 应用过滤规则
  if (groups.series.length > 0) {
    groups.y = groups.y.slice(0, 1)
  } else {
    const multiQuotaY = groups.y.filter((item) => item['multi-quota'] === true)
    groups.multiQuota = multiQuotaY.map((item) => item.value)
    if (multiQuotaY.length > 0) {
      groups.y = multiQuotaY
    }
  }

  return groups
}

function processMultiQuotaData(
  x,
  y,
  multiQuota,
  multiQuotaName = 'zhishu_auto_series',
  data,
) {
  const _list = []
  const _map = {}
  y.forEach((axis) => {
    _map[axis.value] = axis.name
  })
  for (const datum of data) {
    multiQuota.forEach((quota) => {
      const _data = {}
      for (const xAxis of x) {
        _data[xAxis.value] = datum[xAxis.value]
      }
      const quotaAxis = y.find((axis) => axis.value === quota)
      const isPercent = quotaAxis ? isPercentAxis(quotaAxis, data) : false
      const multiplier = quotaAxis && isPercent ? getPercentMultiplier(quotaAxis, data) : 1
      _data[AUTO_VALUE_FIELD] = isPercent
        ? toNullableNumber(datum[quota], multiplier)
        : datum[quota]
      _data[AUTO_SERIES_FIELD] = _map[quota]
      _data[AUTO_PERCENT_FIELD] = isPercent
      _list.push(_data)
    })
  }

  return {
    data: _list,
    y: [{ name: AUTO_VALUE_FIELD, value: AUTO_VALUE_FIELD, type: 'y' }],
    series: [{ name: multiQuotaName, value: AUTO_SERIES_FIELD, type: 'series' }],
  }
}

function checkIsPercent(valueAxes, data) {
  const result = {
    isPercent: false,
    data: [],
  }

  // 深拷贝原始数据
  for (let i = 0; i < data.length; i++) {
    result.data.push({ ...data[i] })
  }

  const percentAxes = valueAxes.filter((valueAxis) => {
    if (valueAxis.value === AUTO_VALUE_FIELD) {
      return data.some((datum) => datum && datum[AUTO_PERCENT_FIELD] === true)
    }
    return isPercentAxis(valueAxis, data)
  })

  result.isPercent = percentAxes.length > 0

  // 如果发现任何百分比轴，处理所有轴的所有百分比数据
  if (result.isPercent) {
    const multipliers = new Map(
      percentAxes.map((axis) => [
        axis.value,
        axis.value === AUTO_VALUE_FIELD ? 1 : getPercentMultiplier(axis, data),
      ]),
    )
    for (let i = 0; i < data.length; i++) {
      for (const valueAxis of percentAxes) {
        const value = data[i][valueAxis.value]
        if (value !== null && value !== undefined && value !== '') {
          const strValue = String(value).trim()
          if (endsWith(strValue, '%')) {
            const formatValue = replace(strValue, '%', '')
            const numValue = Number(formatValue)
            result.data[i][valueAxis.value] = isNaN(numValue) ? 0 : numValue
          } else if (valueAxis.value !== AUTO_VALUE_FIELD) {
            result.data[i][valueAxis.value] = toNullableNumber(
              value,
              multipliers.get(valueAxis.value),
            )
          }
        }
      }
    }
  }

  return result
}

function buildPercentScale(data, valueField) {
  const values = data.map((datum) => toNullableNumber(datum[valueField])).filter((value) => value !== null)

  const scale = {
    nice: true,
    type: 'linear',
    key: 'zhishu_percent_axis',
    domainMin: 0,
  }

  if (values.length === 0) {
    scale.domainMax = 1
    return scale
  }

  const maxValue = Math.max(...values)
  if (maxValue <= 0) {
    scale.domainMax = 1
  } else if (maxValue >= 80) {
    scale.domainMax = 100
  }

  return scale
}

function buildMixedUnitComboOptions(baseOptions, xAxis, mixedData, showLabel) {
  const valueField = mixedData.valueField
  const seriesField = mixedData.seriesField
  const percentScale = buildPercentScale(mixedData.percentData, valueField)

  const xAxisOptions = {
    title: false,
    labelFontSize: 12,
    labelAutoHide: {
      type: 'hide',
      keepHeader: true,
      keepTail: true,
    },
    labelAutoRotate: false,
    labelAutoWrap: true,
    labelAutoEllipsis: true,
  }

  const countLabels = showLabel
    ? [
        {
          text: (datum) => {
            const value = datum[valueField]
            return value === undefined || value === null ? '' : String(formatNumber(value))
          },
          position: (datum) => (datum[valueField] < 0 ? 'bottom' : 'top'),
          transform: [{ type: 'contrastReverse' }, { type: 'exceedAdjust' }, { type: 'overlapHide' }],
        },
      ]
    : []

  const percentLabels = showLabel
    ? [
        {
          text: (datum) => {
            const value = datum[valueField]
            return value === undefined || value === null ? '' : `${formatNumber(value)}%`
          },
          style: {
            dx: -10,
            dy: -12,
          },
          transform: [{ type: 'contrastReverse' }, { type: 'exceedAdjust' }, { type: 'overlapHide' }],
        },
      ]
    : []

  return {
    ...baseOptions,
    type: 'view',
    interaction: {
      elementHighlight: { background: true, region: true },
      tooltip: { series: true, shared: true },
    },
    children: [
      {
        type: 'interval',
        data: mixedData.countData,
        encode: {
          x: xAxis.value,
          y: valueField,
          color: seriesField,
        },
        scale: {
          y: {
            nice: true,
            type: 'linear',
            key: 'zhishu_count_axis',
            zero: true,
          },
        },
        axis: {
          x: xAxisOptions,
          y: {
            position: 'left',
            title: false,
            labelFormatter: (value) => String(formatNumber(value)),
          },
        },
        style: {
          radiusTopLeft: (datum) => (datum[valueField] > 0 ? 4 : 0),
          radiusTopRight: (datum) => (datum[valueField] > 0 ? 4 : 0),
          radiusBottomLeft: (datum) => (datum[valueField] < 0 ? 4 : 0),
          radiusBottomRight: (datum) => (datum[valueField] < 0 ? 4 : 0),
        },
        labels: countLabels,
        tooltip: (datum) => ({
          name: datum[seriesField],
          value: String(formatNumber(datum[valueField])),
        }),
      },
      {
        type: 'line',
        data: mixedData.percentData,
        encode: {
          x: xAxis.value,
          y: valueField,
          color: seriesField,
          shape: 'smooth',
        },
        scale: {
          y: percentScale,
        },
        axis: {
          x: false,
          y: {
            position: 'right',
            title: false,
            labelFormatter: (value) => `${formatNumber(value)}%`,
          },
        },
        labels: percentLabels,
        tooltip: (datum) => ({
          name: datum[seriesField],
          value: `${formatNumber(datum[valueField])}%`,
        }),
      },
      {
        type: 'point',
        data: mixedData.percentData,
        encode: {
          x: xAxis.value,
          y: valueField,
          color: seriesField,
          size: 1.5,
        },
        scale: {
          y: percentScale,
        },
        style: {
          fill: 'white',
        },
        axis: false,
        tooltip: false,
      },
    ],
  }
}

module.exports = {
  buildMixedUnitComboOptions,
  buildMixedUnitData,
  checkIsPercent,
  formatNumber,
  getAxesWithFilter,
  processMultiQuotaData,
  toNumber,
}
