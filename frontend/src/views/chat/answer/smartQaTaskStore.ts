type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'paused'

export interface SmartQaRecordLike {
  id?: number | string
  chat_id?: number | string
  task_id?: string
  finish?: boolean
  finish_time?: unknown
  error?: unknown
  stopped?: boolean
  local_answer?: unknown
  chart?: unknown
}

export interface SmartQaTaskKeyInput {
  tenantId?: number | string | null
  chatId?: number | string | null
  recordId?: number | string | null
}

export interface SmartQaTaskEventPage {
  task_id?: string
  status?: string
  events?: string[]
  next_offset?: number
  total?: number
  error?: unknown
}

export interface SmartQaTaskRegisterInput {
  tenantId?: number | string | null
  chatId?: number | string | null
  recordId?: number | string | null
  record?: SmartQaRecordLike
  taskId?: string
  offset?: number
  callbacks?: SmartQaTaskRuntimeOptions
}

export interface SmartQaTaskRuntimeOptions {
  pollIntervalMs?: number
  getTaskEvents?: (taskId: string, offset: number, limit: number) => Promise<SmartQaTaskEventPage>
  refreshRecord?: (input: SmartQaTaskRuntimeCallbackInput) => Promise<boolean | void>
  loadRecordData?: (input: SmartQaTaskRuntimeCallbackInput) => Promise<void>
  onFinish?: (input: SmartQaTaskRuntimeCallbackInput) => void | Promise<void>
  onError?: (input: SmartQaTaskRuntimeCallbackInput & { error?: unknown }) => void | Promise<void>
  onEvents?: (input: SmartQaTaskRuntimeCallbackInput & { events: string[] }) => void | Promise<void>
  sleep?: (ms: number) => Promise<void>
}

export interface SmartQaTaskRuntimeCallbackInput {
  key: string
  taskId: string
  record: SmartQaRecordLike
  eventPage?: SmartQaTaskEventPage
}

export interface SmartQaTaskEntry {
  key: string
  taskId: string
  record: SmartQaRecordLike
  offset: number
  status: TaskStatus
  promise: Promise<void>
  error?: unknown
  updatedAt: number
  paused: boolean
  callbacks?: SmartQaTaskRuntimeOptions
  events: string[]
  deliveredEventCount: number
  eventDelivery: Promise<void>
}

const TERMINAL_STATUSES = new Set(['succeeded', 'failed'])

function defaultSleep(ms: number) {
  return new Promise<void>((resolve) => {
    const timer = typeof window !== 'undefined' ? window.setTimeout : setTimeout
    timer(resolve, ms)
  })
}

function hasStoredFinalAnswer(record?: SmartQaRecordLike) {
  return !!(
    record?.finish ||
    record?.finish_time ||
    record?.error ||
    record?.stopped ||
    record?.local_answer
  )
}

export function buildSmartQaTaskKey(input: SmartQaTaskKeyInput) {
  return `${input.tenantId || 'default'}:${input.chatId || 'unknown'}:${input.recordId || 'unknown'}`
}

export function createSmartQaTaskStore(initialOptions: SmartQaTaskRuntimeOptions = {}) {
  const entries = new Map<string, SmartQaTaskEntry>()
  let options: SmartQaTaskRuntimeOptions = { pollIntervalMs: 1000, ...initialOptions }

  function configure(nextOptions: SmartQaTaskRuntimeOptions) {
    options = { ...options, ...nextOptions }
  }

  function resolveKey(input: SmartQaTaskRegisterInput) {
    return buildSmartQaTaskKey({
      tenantId: input.tenantId,
      chatId: input.chatId || input.record?.chat_id,
      recordId: input.recordId || input.record?.id,
    })
  }

  function currentCallbacks(entry: SmartQaTaskEntry) {
    return { ...options, ...entry.callbacks }
  }

  function deliverBufferedEvents(entry: SmartQaTaskEntry, eventPage?: SmartQaTaskEventPage) {
    const delivery = entry.eventDelivery.then(async () => {
      const callbacks = currentCallbacks(entry)
      if (!callbacks.onEvents) {
        return
      }
      const pendingEvents = entry.events.slice(entry.deliveredEventCount)
      if (pendingEvents.length === 0) {
        return
      }
      await callbacks.onEvents({
        key: entry.key,
        taskId: entry.taskId,
        record: entry.record,
        eventPage,
        events: pendingEvents,
      })
      entry.deliveredEventCount += pendingEvents.length
    })
    entry.eventDelivery = delivery.catch(() => {})
    return delivery
  }

  async function poll(entry: SmartQaTaskEntry) {
    const sleep = options.sleep || defaultSleep
    const limit = 100
    while (!entry.paused) {
      const runtime = currentCallbacks(entry)
      if (!runtime.getTaskEvents) {
        entry.status = 'failed'
        entry.error = new Error('Smart Q&A task event API is not configured')
        await runtime.onError?.({ key: entry.key, taskId: entry.taskId, record: entry.record, error: entry.error })
        return
      }

      let eventPage: SmartQaTaskEventPage
      try {
        eventPage = await runtime.getTaskEvents(entry.taskId, entry.offset, limit)
      } catch (error) {
        entry.status = 'failed'
        entry.error = error
        entry.updatedAt = Date.now()
        await runtime.onError?.({ key: entry.key, taskId: entry.taskId, record: entry.record, error })
        return
      }

      const callbacks = currentCallbacks(entry)
      entry.offset = eventPage.next_offset ?? entry.offset
      entry.updatedAt = Date.now()
      const events = eventPage.events || []
      if (events.length > 0) {
        entry.events.push(...events)
        await deliverBufferedEvents(entry, eventPage)
      }

      const status = eventPage.status || entry.status
      const total = Number(eventPage.total ?? entry.offset)
      if (TERMINAL_STATUSES.has(status) && entry.offset < total) {
        entry.status = 'running'
        continue
      }
      if (TERMINAL_STATUSES.has(status)) {
        entry.status = status as TaskStatus
        entry.error = eventPage.error
        if (status === 'succeeded') {
          await callbacks.refreshRecord?.({ key: entry.key, taskId: entry.taskId, record: entry.record, eventPage })
          await callbacks.loadRecordData?.({ key: entry.key, taskId: entry.taskId, record: entry.record, eventPage })
          await callbacks.onFinish?.({ key: entry.key, taskId: entry.taskId, record: entry.record, eventPage })
        } else {
          await callbacks.onError?.({
            key: entry.key,
            taskId: entry.taskId,
            record: entry.record,
            eventPage,
            error: eventPage.error,
          })
        }
        // Clean up completed task from map to prevent memory leak
        entries.delete(entry.key)
        return
      }

      entry.status = 'running'
      await sleep(callbacks.pollIntervalMs || options.pollIntervalMs || 1000)
    }
    entry.status = 'paused'
    entry.updatedAt = Date.now()
  }

  function ensureTask(input: SmartQaTaskRegisterInput) {
    const record = input.record
    const taskId = input.taskId || record?.task_id
    if (!record || !taskId || hasStoredFinalAnswer(record)) {
      return undefined
    }

    const key = resolveKey(input)
    const existing = entries.get(key)
    if (existing && existing.taskId === taskId && existing.status === 'running') {
      existing.callbacks = { ...existing.callbacks, ...input.callbacks }
      existing.record = record
      void deliverBufferedEvents(existing)
      return existing
    }

    const entry = {
      key,
      taskId,
      record,
      offset: input.offset || 0,
      status: 'running' as TaskStatus,
      promise: Promise.resolve(),
      updatedAt: Date.now(),
      paused: false,
      callbacks: input.callbacks,
      events: [],
      deliveredEventCount: 0,
      eventDelivery: Promise.resolve(),
    }
    entry.promise = poll(entry)
    entries.set(key, entry)
    return entry
  }

  function registerTask(input: SmartQaTaskRegisterInput) {
    return ensureTask(input)
  }

  function pauseTask(key: string) {
    const entry = entries.get(key)
    if (!entry) return
    entry.paused = true
    entry.status = 'paused'
    entry.updatedAt = Date.now()
  }

  function getTask(key: string) {
    return entries.get(key)
  }

  function isTaskRunning(key: string) {
    return entries.get(key)?.status === 'running'
  }

  function clearTask(key: string) {
    entries.delete(key)
  }

  function detachTaskCallbacks(key: string) {
    const entry = entries.get(key)
    if (entry) {
      entry.callbacks = undefined
    }
  }

  function clearAll() {
    entries.clear()
  }

  return {
    configure,
    ensureTask,
    registerTask,
    pauseTask,
    getTask,
    isTaskRunning,
    clearTask,
    detachTaskCallbacks,
    clearAll,
  }
}

export const smartQaTaskStore = createSmartQaTaskStore()

export function configureSmartQaTaskStore(options: SmartQaTaskRuntimeOptions) {
  smartQaTaskStore.configure(options)
}
