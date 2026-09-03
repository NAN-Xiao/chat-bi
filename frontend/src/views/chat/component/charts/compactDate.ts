import type { ChartAxis } from '@/views/chat/component/BaseChart.ts'

const COMPACT_DATE_VALUE_PATTERN = /^(\d{4})(\d{2})(\d{2})$/
const DATE_AXIS_PATTERN = /(^|[\s_.:/-])(date|dt)([\s_.:/-]|$)|日期|时间|時間/i
const IDENTIFIER_AXIS_PATTERN =
  /(^|[\s_.:/-])(id|uid|uuid|guid|code|key|no)([\s_.:/-]|$)|编号|編號|编码|編碼|代码|代碼/

export function formatCompactDateByAxis(
  value: unknown,
  axis?: Pick<ChartAxis, 'name' | 'value'> | null
): string | null {
  const axisText = `${axis?.name || ''} ${axis?.value || ''}`.trim()
  if (!DATE_AXIS_PATTERN.test(axisText) || IDENTIFIER_AXIS_PATTERN.test(axisText)) {
    return null
  }

  const match = String(value ?? '')
    .trim()
    .match(COMPACT_DATE_VALUE_PATTERN)
  if (!match) {
    return null
  }

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return null
  }

  return `${match[1]}-${match[2]}-${match[3]}`
}
