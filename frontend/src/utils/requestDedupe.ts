interface RequestCacheEntry<T> {
  promise?: Promise<T>
  value?: T
  expiresAt: number
}

const requestCache = new Map<string, RequestCacheEntry<unknown>>()

export function cachedRequest<T>(
  key: string,
  factory: () => Promise<T>,
  ttlMs = 1500
): Promise<T> {
  const now = Date.now()
  const existing = requestCache.get(key) as RequestCacheEntry<T> | undefined
  if (existing?.promise) {
    return existing.promise
  }
  if (existing && existing.expiresAt > now && 'value' in existing) {
    return Promise.resolve(existing.value as T)
  }

  const promise = factory()
    .then((value) => {
      requestCache.set(key, {
        value,
        expiresAt: Date.now() + ttlMs,
      })
      return value
    })
    .catch((error) => {
      if ((requestCache.get(key) as RequestCacheEntry<T> | undefined)?.promise === promise) {
        requestCache.delete(key)
      }
      throw error
    })

  requestCache.set(key, {
    promise,
    expiresAt: now + ttlMs,
  })
  return promise
}

export function clearRequestCache(prefix = '') {
  if (!prefix) {
    requestCache.clear()
    return
  }
  for (const key of requestCache.keys()) {
    if (key.startsWith(prefix)) {
      requestCache.delete(key)
    }
  }
}
