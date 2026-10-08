/** Serializes asynchronous visual updates, keeping only the newest pending revision. */
export function createChartThemeLifecycle(options: {
  apply: (revision: number) => Promise<void>
  onError: (error: unknown) => void
}) {
  let revision = 0
  let completed = 0
  let disposed = false
  let pending: Promise<void> | undefined
  async function drain() {
    while (!disposed && completed !== revision) {
      const next = revision
      try {
        await options.apply(next)
      } catch (error) {
        if (!disposed) options.onError(error)
      }
      completed = next
    }
  }
  return {
    request() {
      if (disposed) return
      revision++
      if (!pending)
        pending = drain().finally(() => {
          pending = undefined
        })
    },
    whenIdle: () => pending ?? Promise.resolve(),
    dispose() {
      disposed = true
    },
  }
}
