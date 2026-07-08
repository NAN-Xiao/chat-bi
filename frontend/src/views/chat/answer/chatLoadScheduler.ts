export interface ChatLoadTask<T = unknown> {
  key: string
  scope?: string
  priority?: number
  run: () => Promise<T>
  apply?: (value: T) => void
  isStale?: () => boolean
}

type QueueItem<T = unknown> = ChatLoadTask<T> & {
  sequence: number
  resolve: (value: T | undefined) => void
  reject: (reason?: unknown) => void
}

export interface ChatLoadScheduler {
  enqueue<T>(task: ChatLoadTask<T>): Promise<T | undefined>
  cancel(scope?: string): void
  pendingCount(): number
  runningCount(): number
}

export function createChatLoadScheduler(
  options: { maxConcurrency?: number } = {}
): ChatLoadScheduler {
  const maxConcurrency = Math.max(1, options.maxConcurrency ?? 3)
  const queue: QueueItem<any>[] = []
  const activeByKey = new Map<string, Promise<unknown | undefined>>()
  let running = 0
  let sequence = 0
  let pumpScheduled = false

  function sortQueue() {
    queue.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.sequence - b.sequence)
  }

  function schedulePump() {
    if (pumpScheduled) {
      return
    }
    pumpScheduled = true
    Promise.resolve().then(() => {
      pumpScheduled = false
      pump()
    })
  }

  function pump() {
    while (running < maxConcurrency && queue.length > 0) {
      sortQueue()
      const item = queue.shift()
      if (!item) {
        return
      }
      running += 1
      Promise.resolve()
        .then(() => item.run())
        .then((value) => {
          if (!item.isStale?.()) {
            item.apply?.(value)
          }
          item.resolve(value)
        })
        .catch((error) => {
          item.reject(error)
        })
        .finally(() => {
          running -= 1
          activeByKey.delete(item.key)
          schedulePump()
        })
    }
  }

  return {
    enqueue<T>(task: ChatLoadTask<T>) {
      const existing = activeByKey.get(task.key)
      if (existing) {
        return existing as Promise<T | undefined>
      }
      const promise = new Promise<T | undefined>((resolve, reject) => {
        queue.push({
          ...task,
          sequence: sequence++,
          resolve,
          reject,
        })
      })
      activeByKey.set(task.key, promise)
      schedulePump()
      return promise
    },
    cancel(scope?: string) {
      for (let i = queue.length - 1; i >= 0; i -= 1) {
        const item = queue[i]
        if (scope === undefined || item.scope === scope) {
          queue.splice(i, 1)
          activeByKey.delete(item.key)
          item.resolve(undefined)
        }
      }
    },
    pendingCount() {
      return queue.length
    },
    runningCount() {
      return running
    },
  }
}
