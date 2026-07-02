export const normalizeEmbeddedOrigin = (value?: unknown): string => {
  const rawValue = String(value || '').trim()
  if (!rawValue) {
    return ''
  }
  try {
    return new URL(rawValue).origin
  } catch {
    return rawValue.replace(/\/+$/, '')
  }
}

export const trustedMessageHostOrigin = (
  event: MessageEvent,
  currentHostOrigin?: string
): string => {
  const eventOrigin = normalizeEmbeddedOrigin(event.origin)
  const expectedOrigin = normalizeEmbeddedOrigin(currentHostOrigin)
  if (expectedOrigin) {
    return eventOrigin === expectedOrigin ? expectedOrigin : ''
  }

  const declaredOrigin = normalizeEmbeddedOrigin((event.data as any)?.hostOrigin)
  if (declaredOrigin && declaredOrigin === eventOrigin) {
    return declaredOrigin
  }
  return ''
}
