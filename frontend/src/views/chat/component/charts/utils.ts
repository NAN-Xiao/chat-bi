import type { ChartAxis, ChartData } from '@/views/chat/component/BaseChart.ts'
import { axisLabel } from '@/views/chat/component/BaseChart.ts'
import type { G2Spec } from '@antv/g2'
import { endsWith, replace } from 'lodash-es'

const AUTO_VALUE_FIELD = 'zhishu_auto_quota'
const AUTO_COUNT_VALUE_FIELD = 'zhishu_auto_count_quota'
const AUTO_PERCENT_VALUE_FIELD = 'zhishu_auto_percent_quota'
const AUTO_SERIES_FIELD = 'zhishu_auto_series'
const AUTO_PERCENT_FIELD = 'zhishu_auto_is_percent'

const PERCENT_KEYWORDS = [
  'rate',
  'ratio',
  'percent',
  'pct',
  'share',
  'proportion',
  'percentage',
  '比率',
  '率',
  '占比',
  '比例',
  '百分',
  '%',
]

const AVERAGE_KEYWORDS = [
  'avg',
  'average',
  'mean',
  'per ',
  'per_',
  '平均',
  '人均',
  '每',
  '单均',
  '客单',
]

const CJK_IDENTIFIER_PATTERN =
  /(账号|账户|用户|玩家|角色|区服|服务器|订单|商品|产品|渠道|设备|会话|事件|项目|记录|租户|工作空间)\s*id/i

const CJK_IDENTIFIER_KEYWORDS = [
  '编号',
  '编码',
  '代码',
  '号码',
  '单号',
  '序列号',
  '标识',
]

const EN_IDENTIFIER_TOKEN_PATTERN =
  /(^|[\s_.:/-])(id|uid|uuid|guid|code|key|no)([\s_.:/-]|$)/i

const EN_IDENTIFIER_SUFFIX_PATTERN = /(Id|ID|Uid|UID|UUID|Guid|GUID|Code|Key|No)$/

/**
 * 为数值添加千分符，保持原有小数位数不变
 * 纯字符串处理，避免精度丢失
 * 支持：正负整数、小数、字符串格式的数值
 */
export function formatNumber(value: any): string | number {
  if (value === null || value === undefined || value === '') {
    return value
  }

  let str: string
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

export function isIdentifierAxis(axis?: Pick<ChartAxis, 'name' | 'value'> | null): boolean {
  const label = axisLabel(axis)
  const value = String(axis?.value || '').trim()
  const text = `${label} ${value}`

  if (CJK_IDENTIFIER_PATTERN.test(text)) {
    return true
  }

  if (CJK_IDENTIFIER_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return true
  }

  return EN_IDENTIFIER_TOKEN_PATTERN.test(text) || EN_IDENTIFIER_SUFFIX_PATTERN.test(value)
}

export function formatValueByAxis(
  value: any,
  axis?: Pick<ChartAxis, 'name' | 'value'> | null
): string | number {
  if (isIdentifierAxis(axis)) {
    return value
  }
  return formatNumber(value)
}

export function toNumber(value: any): number {
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

function isBlankValue(value: any): boolean {
  return value === null || value === undefined || value === ''
}

export function toNullableNumber(value: any, multiplier = 1): number | null {
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

function axisText(axis: ChartAxis): string {
  return axisLabel(axis).toLowerCase()
}

export function isAverageAxis(axis: ChartAxis): boolean {
  const text = axisText(axis)
  return AVERAGE_KEYWORDS.some((keyword) => text.includes(keyword))
}

export function isPercentAxis(axis: ChartAxis, data: Array<ChartData>): boolean {
  const text = axisText(axis)
  if (PERCENT_KEYWORDS.some((keyword) => text.includes(keyword))) {
    return true
  }

  return data.some((datum) => {
    const value = datum?.[axis.value]
    return typeof value === 'string' && endsWith(value.trim(), '%')
  })
}

function getPercentMultiplier(axis: ChartAxis, data: Array<ChartData>): number {
  const values = data
    .map((datum) => datum?.[axis.value])
    .filter((value) => !isBlankValue(value))

  if (values.some((value) => typeof value === 'string' && endsWith(value.trim(), '%'))) {
    return 1
  }

  const numbers = values
    .map((value) => toNullableNumber(value))
    .filter((value): value is number => value !== null)

  if (numbers.length === 0) {
    return 1
  }

  const minValue = Math.min(...numbers)
  const maxAbsValue = Math.max(...numbers.map((value) => Math.abs(value)))
  return minValue >= 0 && maxAbsValue <= 1 ? 100 : 1
}

export interface MixedUnitChartData {
  countAxes: ChartAxis[]
  percentAxes: ChartAxis[]
  countData: ChartData[]
  percentData: ChartData[]
  countValueField: string
  percentValueField: string
  seriesField: string
}

function buildMetricRows(
  x: Array<ChartAxis>,
  metricAxes: Array<ChartAxis>,
  data: Array<ChartData>,
  percent: boolean,
  valueField: string
): ChartData[] {
  const rows: ChartData[] = []
  const percentMultipliers = new Map(
    metricAxes.map((axis) => [axis.value, percent ? getPercentMultiplier(axis, data) : 1])
  )

  for (const datum of data) {
    for (const metricAxis of metricAxes) {
      const value = toNullableNumber(
        datum[metricAxis.value],
        percentMultipliers.get(metricAxis.value) ?? 1
      )
      if (value === null) {
        continue
      }

      const row: ChartData = {
        [valueField]: value,
        [AUTO_SERIES_FIELD]: axisLabel(metricAxis),
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

export function buildMixedUnitData(
  x: Array<ChartAxis>,
  y: Array<ChartAxis>,
  data: Array<ChartData>
): MixedUnitChartData | undefined {
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

  const countData = buildMetricRows(x, countAxes, data, false, AUTO_COUNT_VALUE_FIELD)
  const percentData = buildMetricRows(x, percentAxes, data, true, AUTO_PERCENT_VALUE_FIELD)

  if (countData.length === 0 || percentData.length === 0) {
    return undefined
  }

  return {
    countAxes,
    percentAxes,
    countData,
    percentData,
    countValueField: AUTO_COUNT_VALUE_FIELD,
    percentValueField: AUTO_PERCENT_VALUE_FIELD,
    seriesField: AUTO_SERIES_FIELD,
  }
}

function buildPercentScale(data: Array<ChartData>, valueField: string): Record<string, any> {
  const values = data
    .map((datum) => toNullableNumber(datum[valueField]))
    .filter((value): value is number => value !== null)

  const scale: Record<string, any> = {
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

interface CheckedData {
  isPercent: boolean
  data: Array<ChartData>
}

export function getAxesWithFilter(axes: ChartAxis[]): {
  x: ChartAxis[]
  y: ChartAxis[] // 过滤后的 y
  series: ChartAxis[]
  multiQuota: string[] // series 为空时返回 multi-quota 为 true 的 y 轴 value 列表
  multiQuotaName?: string
} {
  const groups = {
    x: [] as ChartAxis[],
    y: [] as ChartAxis[],
    series: [] as ChartAxis[],
    multiQuota: [] as string[],
    multiQuotaName: undefined as string | undefined,
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

export function processMultiQuotaData(
  x: Array<ChartAxis>,
  y: Array<ChartAxis>,
  multiQuota: Array<string>,
  multiQuotaName: string = 'zhishu_auto_series',
  data: Array<ChartData>
) {
  const _list: Array<ChartData> = []
  const _map: { [propName: string]: string } = {}
  y.forEach((axis) => {
    _map[axis.value] = axisLabel(axis)
  })
  for (const datum of data) {
    multiQuota.forEach((quota) => {
      const _data: { [propName: string]: any } = {}
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
    y: [{ value: AUTO_VALUE_FIELD, type: 'y' } as ChartAxis],
    series: [{ name: multiQuotaName, value: AUTO_SERIES_FIELD, type: 'series' } as ChartAxis],
  }
}

export function checkIsPercent(valueAxes: Array<ChartAxis>, data: Array<ChartData>): CheckedData {
  const result: CheckedData = {
    isPercent: false,
    data: [],
  }

  // 深拷贝原始数据
  for (let i = 0; i < data.length; i++) {
    result.data.push({ ...data[i] })
  }

  const percentAxes = valueAxes.filter((valueAxis) => {
    if (valueAxis.value === AUTO_VALUE_FIELD) {
      return data.some((datum) => datum?.[AUTO_PERCENT_FIELD] === true)
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
      ])
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
              multipliers.get(valueAxis.value) ?? 1
            )
          }
        }
      }
    }
  }

  return result
}

export function buildMixedUnitComboOptions(
  baseOptions: G2Spec,
  xAxis: ChartAxis,
  mixedData: MixedUnitChartData,
  showLabel: boolean
): G2Spec {
  const countValueField = mixedData.countValueField
  const percentValueField = mixedData.percentValueField
  const seriesField = mixedData.seriesField
  const percentScale = buildPercentScale(mixedData.percentData, percentValueField)

  const xAxisOptions = {
    title: false,
    labelFontSize: 11,
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
          text: (datum: ChartData) => {
            const value = datum[countValueField]
            return value === undefined || value === null ? '' : String(formatNumber(value))
          },
          position: (datum: ChartData) => (datum[countValueField] < 0 ? 'bottom' : 'top'),
          transform: [{ type: 'contrastReverse' }, { type: 'exceedAdjust' }, { type: 'overlapHide' }],
        },
      ]
    : []

  const percentLabels = showLabel
    ? [
        {
          text: (datum: ChartData) => {
            const value = datum[percentValueField]
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
    paddingRight: 56,
    paddingBottom: 34,
    axis: {
      x: xAxisOptions,
    },
    scale: {
      x: {
        nice: true,
      },
    },
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
          y: countValueField,
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
          y: {
            position: 'left',
            title: false,
            labelFormatter: (value: any) => String(formatNumber(value)),
          },
        },
        style: {
          radiusTopLeft: (datum: ChartData) => (datum[countValueField] > 0 ? 4 : 0),
          radiusTopRight: (datum: ChartData) => (datum[countValueField] > 0 ? 4 : 0),
          radiusBottomLeft: (datum: ChartData) => (datum[countValueField] < 0 ? 4 : 0),
          radiusBottomRight: (datum: ChartData) => (datum[countValueField] < 0 ? 4 : 0),
        },
        labels: countLabels,
        tooltip: (datum: ChartData) => ({
          name: datum[seriesField],
          value: String(formatNumber(datum[countValueField])),
        }),
      },
      {
        type: 'line',
        data: mixedData.percentData,
        encode: {
          x: xAxis.value,
          y: percentValueField,
          color: seriesField,
        },
        scale: {
          y: {
            ...percentScale,
            independent: true,
          },
        },
        axis: {
          y: {
            position: 'right',
            title: false,
            labelFormatter: (value: any) => `${formatNumber(value)}%`,
          },
        },
        labels: percentLabels,
        tooltip: (datum: ChartData) => ({
          name: datum[seriesField],
          value: `${formatNumber(datum[percentValueField])}%`,
        }),
      },
    ],
  } as G2Spec
}
