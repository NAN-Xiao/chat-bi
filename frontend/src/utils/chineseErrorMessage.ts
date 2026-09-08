/** Only message fields are user-facing; traceback/context remain diagnostic data. */
export function chineseErrorMessage(error: unknown, fallback: string): string {
  const seen = new Set<object>()
  function message(value: unknown, depth = 0): string | undefined {
    if (depth > 6) return undefined
    if (typeof value === 'string') {
      const text = value.trim()
      if (!text || /<\s*(?:!doctype|html|head|body)[\s>]/i.test(text)) return undefined
      try {
        const parsed = JSON.parse(text)
        if (parsed !== value) return message(parsed, depth + 1)
      } catch { /* Plain text is also a supported error payload. */ }
      return /[\u3400-\u9fff\uf900-\ufaff]/.test(text) ? text : undefined
    }
    if (!value || typeof value !== 'object' || seen.has(value)) return undefined
    seen.add(value)
    const record = value as Record<string, unknown>
    const values = Array.isArray(value)
      ? value
      : ['response', 'data', 'detail', 'message', 'msg', 'error', 'reason'].map(key => record[key])
    for (const item of values) {
      const found = message(item, depth + 1)
      if (found) return found
    }
    return undefined
  }
  return message(error) || fallback
}
