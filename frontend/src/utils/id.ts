export const normalizeIdString = (value: any): string => {
  if (value === undefined || value === null) return ''
  const text = typeof value === 'object' && value?.toString ? value.toString() : String(value)
  return text.trim().replace(/\.0$/, '')
}

export const toIdStringList = (value: any): string[] => {
  if (!value) return []
  if (Array.isArray(value)) {
    return value.map((item: any) => normalizeIdString(item)).filter(Boolean)
  }
  if (typeof value === 'string') {
    try {
      return toIdStringList(JSON.parse(value))
    } catch (e) {
      const text = normalizeIdString(value)
      return text ? [text] : []
    }
  }
  const text = normalizeIdString(value)
  return text ? [text] : []
}

const looksLikeLargeIntegerId = (value: string) => /^-?\d{16,}$/.test(value)

export const idsEqual = (left: any, right: any): boolean => {
  const leftText = normalizeIdString(left)
  const rightText = normalizeIdString(right)
  if (!leftText || !rightText) return false
  if (leftText === rightText) return true
  if (!looksLikeLargeIntegerId(leftText) || !looksLikeLargeIntegerId(rightText)) return false
  return Number(leftText) === Number(rightText)
}

export const uniqueIdStrings = (values: any[]): string[] => {
  const result: string[] = []
  values.forEach((value) => {
    const text = normalizeIdString(value)
    if (!text || result.some((item) => idsEqual(item, text))) return
    result.push(text)
  })
  return result
}
