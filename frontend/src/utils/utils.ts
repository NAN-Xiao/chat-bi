import dayjs from 'dayjs'
import { useCache } from '@/utils/useCache'
const { wsCache } = useCache()
const getCheckDate = (timestamp: any) => {
  if (!timestamp) return false
  const dt = new Date(timestamp)
  if (isNaN(dt.getTime())) return false
  return dt
}

export const datetimeFormat = (timestamp: any) => {
  const dt = getCheckDate(timestamp)
  if (!dt) return timestamp

  const y = dt.getFullYear()
  const m = (dt.getMonth() + 1 + '').padStart(2, '0')
  const d = (dt.getDate() + '').padStart(2, '0')
  const hh = (dt.getHours() + '').padStart(2, '0')
  const mm = (dt.getMinutes() + '').padStart(2, '0')
  const ss = (dt.getSeconds() + '').padStart(2, '0')

  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`
}

/**
 *
 * string: only accept ISO 8601, example: '2018-04-04T16:00:00.000Z'
 * number: timestamp
 * @param time
 */
export function getDate(time?: Date | string | number) {
  if (!time) return undefined
  if (time instanceof Date) return time
  if (typeof time === 'string') {
    return dayjs(time).toDate()
  }
  return new Date(time)
}

export const getBrowserLocale = () => {
  const language = navigator.language
  if (!language) {
    return 'zh-CN'
  }
  if (language.startsWith('en')) {
    return 'en'
  }
  if (language.toLowerCase().startsWith('zh')) {
    const temp = language.toLowerCase().replace('_', '-')
    return temp === 'zh' ? 'zh-CN' : temp === 'zh-cn' ? 'zh-CN' : 'tw'
  }
  return language
}
export const getLocale = () => {
  return wsCache.get('user.language') || getBrowserLocale() || 'zh-CN'
}
