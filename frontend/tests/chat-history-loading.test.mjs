import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { createRequire } from 'node:module'
import ts from 'typescript'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(import.meta.url)

function loadTsModule(relativePath) {
  const filePath = path.join(root, relativePath)
  const source = fs.readFileSync(filePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  }).outputText
  const module = { exports: {} }
  vm.runInNewContext(
    output,
    {
      exports: module.exports,
      module,
      require,
      URLSearchParams,
      setTimeout,
      clearTimeout,
    },
    { filename: filePath }
  )
  return module.exports
}

async function flushMicrotasks(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await Promise.resolve()
  }
}

function testFinalAnswerVisibilityRequiresTerminalRefresh() {
  const { partitionTerminalRecordUpdate, shouldShowFinalAnswer, shouldShowTerminalResult } =
    loadTsModule('src/views/chat/answer/answerVisibility.ts')

  assert.equal(typeof partitionTerminalRecordUpdate, 'function')
  assert.equal(typeof shouldShowTerminalResult, 'function')

  assert.equal(
    shouldShowFinalAnswer({
      record: { task_id: 'running', chart: '{"type":"column"}' },
      isTyping: false,
      finalAnswerReady: false,
    }),
    false
  )
  assert.equal(
    shouldShowFinalAnswer({
      record: { finish: true, chart: '{"type":"column"}' },
      isTyping: false,
      finalAnswerReady: false,
    }),
    false
  )
  assert.equal(
    shouldShowFinalAnswer({
      record: { finish: true, chart: '{"type":"column"}' },
      isTyping: false,
      finalAnswerReady: true,
    }),
    true
  )
  assert.equal(
    shouldShowFinalAnswer({
      record: { error: 'failed' },
      isTyping: true,
      finalAnswerReady: false,
    }),
    true
  )
  assert.equal(
    shouldShowFinalAnswer({
      record: { stopped: true },
      isTyping: false,
      finalAnswerReady: false,
    }),
    true
  )
  assert.equal(
    shouldShowFinalAnswer({
      record: {
        analysis: '当前数据源缺少所需埋点数据。',
        analysis_notice: { reason: 'missing_event' },
      },
      isTyping: true,
      finalAnswerReady: false,
    }),
    true
  )
  assert.equal(
    shouldShowTerminalResult({
      record: {
        analysis_notice: { reason: 'missing_event' },
        chart: '{"type":"column"}',
      },
      isTyping: true,
      finalAnswerReady: false,
    }),
    false
  )
  assert.equal(
    shouldShowTerminalResult({
      record: {
        finish: true,
        analysis_notice: { reason: 'missing_event' },
        chart: '{"type":"column"}',
      },
      isTyping: false,
      finalAnswerReady: true,
    }),
    true
  )

  const partitioned = partitionTerminalRecordUpdate(
    {
      id: 94,
      task_id: undefined,
      finish: true,
      finish_time: '2026-07-31T12:00:00Z',
      chart: '{"type":"column"}',
      analysis: '已生成其余可支持的结果。',
      analysis_notice: { reason: 'missing_event' },
      total_tokens: 100,
    },
    'task-still-active'
  )
  assert.equal(Object.hasOwn(partitioned.content, 'finish'), false)
  assert.equal(Object.hasOwn(partitioned.content, 'finish_time'), false)
  assert.equal(partitioned.content.task_id, 'task-still-active')
  assert.equal(partitioned.content.chart, '{"type":"column"}')
  assert.deepEqual(
    { ...partitioned.afterData },
    {
      analysis: '已生成其余可支持的结果。',
      analysis_notice: { reason: 'missing_event' },
    }
  )
  assert.equal(partitioned.terminal.finish, true)
  assert.equal(partitioned.terminal.finish_time, '2026-07-31T12:00:00Z')

  const { applyChartDataResponseToRecord } = loadTsModule(
    'src/views/chat/answer/chartDataResponse.ts'
  )
  const partialResultRecord = { ...partitioned.content }
  applyChartDataResponseToRecord(partialResultRecord, {
    status: 'success',
    fields: ['日期', 'DAU'],
    data: [{ 日期: '2026-07-30', DAU: 100 }],
  })
  assert.equal(partialResultRecord.analysis_notice, undefined)
  Object.assign(partialResultRecord, partitioned.afterData)
  assert.deepEqual(partialResultRecord.analysis_notice, { reason: 'missing_event' })
}

async function testTerminalRecordsDoNotRestoreTasks() {
  const {
    hasStoredFinalAnswer,
    isRestorableAnswerRecord,
    shouldMarkChatTypingOnRestore,
    shouldRestoreWhenAnswerRecordChanges,
    shouldLookupRecordTask,
    shouldRefreshRecordAfterNoActiveTask,
    shouldUseRememberedTask,
  } = loadTsModule('src/views/chat/answer/taskRestore.ts')

  const terminalRecords = [
    { id: 1, finish: true, task_id: 'stale-task' },
    { id: 2, finish_time: '2026-07-08 11:00:00', task_id: 'stale-task' },
    { id: 3, error: 'failed', task_id: 'stale-task' },
    { id: 4, stopped: true, task_id: 'stale-task' },
  ]

  for (const record of terminalRecords) {
    assert.equal(hasStoredFinalAnswer(record), true)
    assert.equal(shouldUseRememberedTask(record), false)
    assert.equal(shouldLookupRecordTask(record), false)
    assert.equal(shouldRefreshRecordAfterNoActiveTask(record), false)
  }

  const pendingRecord = { id: 5, task_id: 'running-task' }
  assert.equal(hasStoredFinalAnswer(pendingRecord), false)
  assert.equal(shouldUseRememberedTask(pendingRecord), true)
  assert.equal(shouldLookupRecordTask(pendingRecord), true)
  assert.equal(shouldRefreshRecordAfterNoActiveTask(pendingRecord), true)

  const streamingRecordWithPartialAnswer = {
    id: 6,
    task_id: 'running-task',
    analysis: '已生成的部分回答',
    analysis_thinking: '仍在思考',
  }
  assert.equal(hasStoredFinalAnswer(streamingRecordWithPartialAnswer), false)
  assert.equal(isRestorableAnswerRecord(streamingRecordWithPartialAnswer, true), true)
  assert.equal(isRestorableAnswerRecord(streamingRecordWithPartialAnswer, false), true)
  assert.equal(shouldUseRememberedTask(streamingRecordWithPartialAnswer), true)
  assert.equal(shouldLookupRecordTask(streamingRecordWithPartialAnswer), true)
  assert.equal(shouldRefreshRecordAfterNoActiveTask(streamingRecordWithPartialAnswer), true)

  const partiallyStoredRecordWithoutTaskId = {
    id: 7,
    analysis: '切页前已经落库的部分回答',
  }
  assert.equal(hasStoredFinalAnswer(partiallyStoredRecordWithoutTaskId), false)
  assert.equal(isRestorableAnswerRecord(partiallyStoredRecordWithoutTaskId, true), true)
  assert.equal(isRestorableAnswerRecord(partiallyStoredRecordWithoutTaskId, false), false)
  assert.equal(shouldUseRememberedTask(partiallyStoredRecordWithoutTaskId), true)
  assert.equal(shouldLookupRecordTask(partiallyStoredRecordWithoutTaskId), true)
  assert.equal(shouldRefreshRecordAfterNoActiveTask(partiallyStoredRecordWithoutTaskId), true)

  const newLocalRecordBeforeTaskCreated = { question: 'dau' }
  assert.equal(isRestorableAnswerRecord(newLocalRecordBeforeTaskCreated, true), true)
  assert.equal(isRestorableAnswerRecord(newLocalRecordBeforeTaskCreated, false), false)

  const previousRecord = { id: 8, finish: true, question: '上一个会话的问题' }
  const nextRunningRecord = { id: 9, question: '切换后的执行中问题' }
  assert.equal(shouldRestoreWhenAnswerRecordChanges(previousRecord, nextRunningRecord, true), true)
  assert.equal(
    shouldRestoreWhenAnswerRecordChanges(nextRunningRecord, nextRunningRecord, true),
    false
  )
  assert.equal(
    shouldRestoreWhenAnswerRecordChanges(previousRecord, { id: 10, finish: true }, true),
    false
  )

  assert.equal(shouldMarkChatTypingOnRestore([]), false)
  assert.equal(
    shouldMarkChatTypingOnRestore([{ id: 11, question: '历史已完成', finish: true }]),
    false
  )
  assert.equal(
    shouldMarkChatTypingOnRestore([
      { id: 12, question: '旧问题', finish: true },
      { id: 13, question: '切回后仍在执行', task_id: 'running-task' },
    ]),
    true
  )
  assert.equal(
    shouldMarkChatTypingOnRestore([
      { id: 14, question: '非最后一条执行中', task_id: 'running-task' },
      { id: 15, question: '最后一条已完成', finish: true },
    ]),
    false
  )
}

async function testSchedulerHonorsConcurrencyAndPriority() {
  const { createChatLoadScheduler } = loadTsModule('src/views/chat/answer/chatLoadScheduler.ts')
  const scheduler = createChatLoadScheduler({ maxConcurrency: 2 })
  const started = []
  const release = []

  function queuedTask(key, priority) {
    return scheduler.enqueue({
      key,
      priority,
      run: () =>
        new Promise((resolve) => {
          started.push(key)
          release.push(() => resolve(key))
        }),
    })
  }

  const low = queuedTask('low', 1)
  const high = queuedTask('high', 10)
  const medium = queuedTask('medium', 5)

  await flushMicrotasks(2)
  assert.deepEqual(started, ['high', 'medium'])
  release.shift()()
  await flushMicrotasks(8)
  assert.deepEqual(started, ['high', 'medium', 'low'])
  release.shift()()
  release.shift()()
  assert.deepEqual(await Promise.all([low, high, medium]), ['low', 'high', 'medium'])
}

async function testSchedulerDedupesCancelsAndSkipsStaleApply() {
  const { createChatLoadScheduler } = loadTsModule('src/views/chat/answer/chatLoadScheduler.ts')
  const scheduler = createChatLoadScheduler({ maxConcurrency: 1 })
  let calls = 0
  const applied = []
  let stale = false

  const first = scheduler.enqueue({
    key: 'chat:1:record:1',
    scope: 'chat:1',
    run: async () => {
      calls += 1
      return 'first'
    },
    apply: (value) => applied.push(value),
    isStale: () => stale,
  })
  const second = scheduler.enqueue({
    key: 'chat:1:record:1',
    scope: 'chat:1',
    run: async () => {
      calls += 1
      return 'second'
    },
  })
  assert.equal(await first, 'first')
  assert.equal(await second, 'first')
  assert.equal(calls, 1)
  assert.deepEqual(applied, ['first'])

  stale = true
  const staleResult = await scheduler.enqueue({
    key: 'chat:1:record:2',
    scope: 'chat:1',
    run: async () => 'stale',
    apply: (value) => applied.push(value),
    isStale: () => stale,
  })
  assert.equal(staleResult, 'stale')
  assert.deepEqual(applied, ['first'])

  const blocked = scheduler.enqueue({
    key: 'chat:1:slow',
    scope: 'chat:1',
    run: () => new Promise(() => {}),
  })
  const cancelled = scheduler.enqueue({
    key: 'chat:1:cancelled',
    scope: 'chat:1',
    run: async () => 'cancelled',
  })
  await Promise.resolve()
  scheduler.cancel('chat:1')
  assert.equal(await cancelled, undefined)
  assert.equal(scheduler.pendingCount(), 0)
  assert.equal(scheduler.runningCount(), 1)
  void blocked
}

async function testCachedRequestReusesSamePendingQuery() {
  const { cachedRequest, clearRequestCache } = loadTsModule('src/utils/requestDedupe.ts')
  clearRequestCache()

  let calls = 0
  const first = cachedRequest('agent-selector:3:?dslist=3', async () => {
    calls += 1
    return [{ id: 1 }]
  })
  const second = cachedRequest('agent-selector:3:?dslist=3', async () => {
    calls += 1
    return [{ id: 2 }]
  })

  assert.deepEqual(await Promise.all([first, second]), [[{ id: 1 }], [{ id: 1 }]])
  assert.equal(calls, 1)

  const third = await cachedRequest('agent-selector:3:?dslist=3', async () => {
    calls += 1
    return [{ id: 3 }]
  })
  assert.deepEqual(third, [{ id: 1 }])
  assert.equal(calls, 1)

  clearRequestCache('agent-selector:')
  const fourth = await cachedRequest('agent-selector:3:?dslist=3', async () => {
    calls += 1
    return [{ id: 4 }]
  })
  assert.deepEqual(fourth, [{ id: 4 }])
  assert.equal(calls, 2)
}

async function testSmartQaTaskStorePollsIndependentlyAndDedupes() {
  const { buildSmartQaTaskKey, createSmartQaTaskStore } = loadTsModule(
    'src/views/chat/answer/smartQaTaskStore.ts'
  )
  const calls = []
  const refreshed = []
  const loadedData = []
  const finished = []

  const store = createSmartQaTaskStore({
    sleep: async () => {},
    getTaskEvents: async (taskId, offset) => {
      calls.push({ taskId, offset })
      if (offset === 0) {
        return {
          task_id: taskId,
          status: 'running',
          events: ['data:{"type":"answer","content":"partial"}'],
          next_offset: 1,
          total: 1,
        }
      }
      return {
        task_id: taskId,
        status: 'succeeded',
        events: ['data:{"type":"finish"}'],
        next_offset: 2,
        total: 2,
      }
    },
    refreshRecord: async ({ record }) => {
      refreshed.push(record.id)
      record.finish = true
      return true
    },
    loadRecordData: async ({ record }) => {
      loadedData.push(record.id)
    },
    onFinish: ({ record }) => {
      finished.push(record.id)
    },
  })

  const record = {
    id: 11,
    chat_id: 22,
    question: 'DAU',
    task_id: 'task-1',
  }
  const key = buildSmartQaTaskKey({ tenantId: 'tenant-a', chatId: 22, recordId: 11 })
  assert.equal(key, 'tenant-a:22:11')

  const first = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 22,
    record,
    taskId: 'task-1',
    offset: 0,
  })
  const second = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 22,
    record,
    taskId: 'task-1',
    offset: 0,
  })

  assert.strictEqual(first, second)
  assert.equal(store.isTaskRunning(key), true)
  await first.promise

  assert.deepEqual(calls, [
    { taskId: 'task-1', offset: 0 },
    { taskId: 'task-1', offset: 1 },
  ])
  assert.equal(first.status, 'succeeded')
  assert.equal(record.finish, true)
  assert.deepEqual(refreshed, [11])
  assert.deepEqual(loadedData, [11])
  assert.deepEqual(finished, [11])
  assert.equal(store.isTaskRunning(key), false)
}

async function testSmartQaTaskStoreSkipsTerminalRecords() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  let calls = 0
  const store = createSmartQaTaskStore({
    sleep: async () => {},
    getTaskEvents: async () => {
      calls += 1
      return { status: 'succeeded', events: [], next_offset: 0, total: 0 }
    },
  })

  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 22,
    record: { id: 12, chat_id: 22, finish: true, task_id: 'stale-task' },
    taskId: 'stale-task',
  })

  assert.equal(entry, undefined)
  assert.equal(calls, 0)
}

async function testSmartQaTaskStoreRefreshesCallbacksWithoutDuplicatePolling() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  let calls = 0
  const finished = []
  const store = createSmartQaTaskStore({
    sleep: async () => {},
    getTaskEvents: async () => {
      calls += 1
      return { status: 'succeeded', events: ['data:{"type":"finish"}'], next_offset: 1, total: 1 }
    },
  })

  const record = { id: 31, chat_id: 41, task_id: 'task-callback' }
  const first = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 41,
    record,
    taskId: 'task-callback',
    callbacks: {
      onFinish: () => finished.push('first'),
    },
  })
  const second = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 41,
    record,
    taskId: 'task-callback',
    callbacks: {
      onFinish: () => finished.push('second'),
    },
  })

  assert.strictEqual(first, second)
  await first.promise
  assert.equal(calls, 1)
  assert.deepEqual(finished, ['second'])
}

async function testSmartQaTaskStoreDrainsUnreadEventsBeforeTerminalCallbacks() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  const offsets = []
  const received = []
  const finished = []
  const store = createSmartQaTaskStore({
    sleep: async () => {},
    getTaskEvents: async (taskId, offset) => {
      offsets.push(offset)
      if (offset === 0) {
        return {
          task_id: taskId,
          status: 'succeeded',
          events: ['data:{"type":"chart","content":"partial"}'],
          next_offset: 100,
          total: 150,
        }
      }
      return {
        task_id: taskId,
        status: 'succeeded',
        events: ['data:{"type":"finish"}'],
        next_offset: 150,
        total: 150,
      }
    },
    onEvents: ({ events }) => received.push(...events),
    onFinish: () => finished.push('finish'),
  })

  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 91,
    record: { id: 81, chat_id: 91, task_id: 'task-paged-terminal' },
    taskId: 'task-paged-terminal',
  })
  await entry.promise

  assert.deepEqual(offsets, [0, 100])
  assert.deepEqual(received, [
    'data:{"type":"chart","content":"partial"}',
    'data:{"type":"finish"}',
  ])
  assert.deepEqual(finished, ['finish'])
}

async function testSmartQaTaskStoreWaitsForTerminalRecordRefresh() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  let polls = 0
  let refreshes = 0
  const callbackOrder = []
  const sleepDurations = []
  const store = createSmartQaTaskStore({
    sleep: async (duration) => sleepDurations.push(duration),
    getTaskEvents: async () => {
      polls += 1
      return {
        status: 'succeeded',
        events: polls === 1 ? ['data:{"type":"finish"}\n\n'] : [],
        next_offset: 1,
        total: 1,
      }
    },
  })
  const record = { id: 91, chat_id: 81, task_id: 'task-terminal-refresh' }
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record,
    callbacks: {
      refreshRecord: async () => {
        refreshes += 1
        callbackOrder.push('refresh')
        return refreshes >= 2
      },
      loadRecordData: async () => callbackOrder.push('load'),
      onFinish: async () => callbackOrder.push('finish'),
    },
  })

  await entry.promise

  assert.equal(polls, 2)
  assert.equal(refreshes, 2)
  assert.deepEqual(sleepDurations, [1000])
  assert.deepEqual(callbackOrder, ['refresh', 'refresh', 'load', 'finish'])
}

async function testSmartQaTaskStoreBacksOffWhileTerminalRecordIsUnavailable() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  let refreshes = 0
  const sleepDurations = []
  const store = createSmartQaTaskStore({
    pollIntervalMs: 100,
    terminalRefreshMaxDelayMs: 250,
    sleep: async (duration) => sleepDurations.push(duration),
    getTaskEvents: async () => ({
      status: 'succeeded',
      events: [],
      next_offset: 0,
      total: 0,
    }),
  })
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record: { id: 92, chat_id: 81, task_id: 'task-terminal-backoff' },
    callbacks: {
      refreshRecord: async () => {
        refreshes += 1
        return refreshes >= 4
      },
    },
  })

  await entry.promise

  assert.deepEqual(sleepDurations, [100, 200, 250])
}

async function testSmartQaTaskStoreReportsTerminalCallbackErrors() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  const errors = []
  const store = createSmartQaTaskStore({
    getTaskEvents: async () => ({
      status: 'succeeded',
      events: [],
      next_offset: 0,
      total: 0,
    }),
  })
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record: { id: 93, chat_id: 81, task_id: 'task-terminal-load-error' },
    callbacks: {
      refreshRecord: async () => true,
      loadRecordData: async () => {
        throw new Error('load failed')
      },
      onError: async ({ error }) => errors.push(error?.message),
    },
  })
  let rejected
  try {
    await entry.promise
  } catch (error) {
    rejected = error
  }

  assert.equal(rejected, undefined)
  assert.equal(entry.status, 'failed')
  assert.deepEqual(errors, ['load failed'])
}

async function testSmartQaTaskStoreReportsFailedTerminalStatus() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  const errors = []
  const store = createSmartQaTaskStore({
    getTaskEvents: async () => ({
      status: 'failed',
      error: 'worker disconnected',
      events: [],
      next_offset: 0,
      total: 0,
    }),
  })
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record: { id: 94, chat_id: 81, task_id: 'task-terminal-failed' },
    callbacks: {
      onError: async ({ error }) => errors.push(error),
    },
  })

  await entry.promise

  assert.equal(entry.status, 'failed')
  assert.deepEqual(errors, ['worker disconnected'])
}

async function testSmartQaTaskStoreRemovesEntriesAfterEventRequestFailure() {
  const { buildSmartQaTaskKey, createSmartQaTaskStore } = loadTsModule(
    'src/views/chat/answer/smartQaTaskStore.ts'
  )
  const errors = []
  const store = createSmartQaTaskStore({
    getTaskEvents: async () => {
      throw new Error('events unavailable')
    },
  })
  const record = { id: 95, chat_id: 81, task_id: 'task-event-error' }
  const key = buildSmartQaTaskKey({ tenantId: 'tenant-a', chatId: 81, recordId: 95 })
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record,
    callbacks: {
      onError: async ({ error }) => errors.push(error?.message),
    },
  })

  await entry.promise

  assert.deepEqual(errors, ['events unavailable'])
  assert.equal(store.getTask(key), undefined)
}

async function testSmartQaTaskStoreCleansUpWhenTerminalErrorHandlerThrows() {
  const { buildSmartQaTaskKey, createSmartQaTaskStore } = loadTsModule(
    'src/views/chat/answer/smartQaTaskStore.ts'
  )
  const store = createSmartQaTaskStore({
    getTaskEvents: async () => ({
      status: 'succeeded',
      events: [],
      next_offset: 0,
      total: 0,
    }),
  })
  const key = buildSmartQaTaskKey({ tenantId: 'tenant-a', chatId: 81, recordId: 96 })
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 81,
    record: { id: 96, chat_id: 81, task_id: 'task-terminal-error-handler' },
    callbacks: {
      refreshRecord: async () => true,
      loadRecordData: async () => {
        throw new Error('load failed')
      },
      onError: async () => {
        throw new Error('error handler failed')
      },
    },
  })
  let rejected
  try {
    await entry.promise
  } catch (error) {
    rejected = error
  }

  assert.equal(rejected?.message, 'error handler failed')
  assert.equal(store.getTask(key), undefined)
}

async function testSmartQaTaskStoreDetachesCallbacksButKeepsPolling() {
  const { buildSmartQaTaskKey, createSmartQaTaskStore } = loadTsModule(
    'src/views/chat/answer/smartQaTaskStore.ts'
  )
  let calls = 0
  const finished = []
  const key = buildSmartQaTaskKey({ tenantId: 'tenant-a', chatId: 51, recordId: 41 })
  const store = createSmartQaTaskStore({
    sleep: async () => {},
    getTaskEvents: async () => {
      calls += 1
      return { status: 'succeeded', events: ['data:{"type":"finish"}'], next_offset: 1, total: 1 }
    },
  })

  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 51,
    record: { id: 41, chat_id: 51, task_id: 'task-detach' },
    taskId: 'task-detach',
    callbacks: {
      onFinish: () => finished.push('mounted-component'),
    },
  })
  store.detachTaskCallbacks(key)
  await entry.promise

  assert.equal(calls, 1)
  assert.deepEqual(finished, [])
  assert.equal(entry.status, 'succeeded')
}

async function testSmartQaTaskStoreReplaysBufferedEventsWhenCallbacksReattach() {
  const { createSmartQaTaskStore } = loadTsModule('src/views/chat/answer/smartQaTaskStore.ts')
  let sleepResolve
  const receivedWhileRemounted = []
  const store = createSmartQaTaskStore({
    sleep: async () =>
      new Promise((resolve) => {
        sleepResolve = resolve
      }),
    getTaskEvents: async (taskId, offset) => {
      if (offset === 0) {
        return {
          task_id: taskId,
          status: 'running',
          events: ['data:{"type":"sql-result","reasoning_content":"正在生成 SQL"}'],
          next_offset: 1,
          total: 1,
        }
      }
      return {
        task_id: taskId,
        status: 'succeeded',
        events: ['data:{"type":"finish"}'],
        next_offset: 2,
        total: 2,
      }
    },
  })

  const record = { id: 61, chat_id: 71, task_id: 'task-replay' }
  const entry = store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 71,
    record,
    taskId: 'task-replay',
    callbacks: {
      onEvents: () => {
        throw new Error('卸载前的回调不应该收到解绑后的事件')
      },
    },
  })
  store.detachTaskCallbacks('tenant-a:71:61')
  await flushMicrotasks(6)

  assert.equal(entry.status, 'running')

  store.ensureTask({
    tenantId: 'tenant-a',
    chatId: 71,
    record,
    taskId: 'task-replay',
    callbacks: {
      onEvents: ({ events }) => {
        receivedWhileRemounted.push(...events)
      },
    },
  })
  await flushMicrotasks(6)

  assert.deepEqual(receivedWhileRemounted, [
    'data:{"type":"sql-result","reasoning_content":"正在生成 SQL"}',
  ])

  sleepResolve()
  await entry.promise
}

function testChatTaskContextKeepsOldTaskOutOfCurrentChat() {
  const { applyBriefToTaskOwner, buildChatMessageRenderKey, resolveTaskOwnerChatId } = loadTsModule(
    'src/views/chat/answer/chatTaskContext.ts'
  )

  assert.equal(resolveTaskOwnerChatId(101, 202), 101)
  assert.equal(resolveTaskOwnerChatId(undefined, 202), 202)

  const chatList = [
    { id: 101, brief: '会话 A' },
    { id: 202, brief: '会话 B' },
  ]
  const currentChat = { id: 202, brief: '会话 B' }
  const currentChatUpdated = applyBriefToTaskOwner({
    chatList,
    currentChat,
    currentChatId: 202,
    ownerChatId: 101,
    brief: '会话 A 自动标题',
  })

  assert.equal(currentChatUpdated, false)
  assert.equal(chatList[0].brief, '会话 A 自动标题')
  assert.equal(chatList[1].brief, '会话 B')
  assert.equal(currentChat.brief, '会话 B')

  const record = { id: 301, create_time: '2026-07-20T10:00:00Z' }
  assert.notEqual(
    buildChatMessageRenderKey(101, 'assistant', record, 0),
    buildChatMessageRenderKey(202, 'assistant', record, 0)
  )
  const createTime = new Date('2026-07-20T10:00:00Z')
  assert.equal(
    buildChatMessageRenderKey(101, 'assistant', { create_time: createTime }, 0),
    buildChatMessageRenderKey(101, 'assistant', { create_time: createTime.toISOString() }, 0)
  )
  assert.notEqual(
    buildChatMessageRenderKey(101, 'assistant', { create_time: createTime }, 0),
    buildChatMessageRenderKey(101, 'assistant', { create_time: createTime }, 1),
    '同一会话内创建时间相同的不同记录必须保持唯一渲染键'
  )
}

function testChatMessageRenderKeySurvivesActiveRecordRefresh() {
  const { buildChatMessageRenderKey } = loadTsModule('src/views/chat/answer/chatTaskContext.ts')
  const record = { create_time: new Date('2026-07-21T00:42:52.497Z') }
  const initialKey = buildChatMessageRenderKey(257, 'assistant', record, 1)

  record.id = 905
  record.create_time = new Date('2026-07-21T00:42:52.627Z')

  assert.equal(
    buildChatMessageRenderKey(257, 'assistant', record, 1),
    initialKey,
    '活动记录刷新服务端 ID 和创建时间时不得替换正在消费任务事件的组件'
  )
}

function testChartAnswerDefersPostAnswerActionsUntilTerminalRefresh() {
  const chartAnswerSource = fs.readFileSync(
    path.join(root, 'src/views/chat/answer/ChartAnswer.vue'),
    'utf8'
  )
  const handlePayloadStart = chartAnswerSource.indexOf('async function handlePayload')
  const refreshRecordStart = chartAnswerSource.indexOf('async function refreshCurrentRecord')
  const handlePayloadSource = chartAnswerSource.slice(handlePayloadStart, refreshRecordStart)
  const finishCaseSource = handlePayloadSource.match(/case 'finish':[\s\S]*?break/)?.[0]
  const attachTaskStart = chartAnswerSource.indexOf('function attachGlobalTask')
  const attachTaskEnd = chartAnswerSource.indexOf('function stop(', attachTaskStart)
  const attachTaskSource = chartAnswerSource.slice(attachTaskStart, attachTaskEnd)
  const refreshCallbackSource = attachTaskSource.match(
    /refreshRecord:\s*async[\s\S]*?(?=\n\s*loadRecordData:)/
  )?.[0]
  const finishCallbackSource = attachTaskSource.match(
    /onFinish:\s*async[\s\S]*?(?=\n\s*onError:)/
  )?.[0]

  assert.ok(finishCaseSource, 'ChartAnswer 应包含流式 finish 事件处理')
  assert.doesNotMatch(
    finishCaseSource,
    /emitFinishOnce/,
    '流式 finish 只能结束答案状态，不能提前启动完成后动作'
  )
  assert.equal(
    (attachTaskSource.match(/fetchCurrentRecord\(/g) || []).length,
    1,
    '任务附加后不得通过并行记录刷新绕过队列 succeeded 和事件排空门禁'
  )
  assert.ok(refreshCallbackSource, '任务存储应配置最终记录刷新回调')
  assert.doesNotMatch(
    refreshCallbackSource,
    /markFinalAnswerReady|clearCurrentTask/,
    '记录刷新回调只确认持久化终态，不得提前解锁或清除任务'
  )
  assert.ok(finishCallbackSource, '任务存储应配置最终完成回调')
  assert.match(
    finishCallbackSource,
    /markFinalAnswerReady\(\)[\s\S]*clearCurrentTask\(currentRecord\)[\s\S]*emitFinishOnce/,
    '最终数据加载完成后才可解锁答案、清除任务并通知父组件'
  )
  assert.match(
    chartAnswerSource,
    /v-if="showTerminalResult && !message\.record\?\.error"/,
    '业务提示运行中不得展示阶段性图表，完成后应恢复合法图表'
  )
  assert.doesNotMatch(
    finishCaseSource,
    /finish:\s*true|markFinalAnswerReady|clearCurrentTask/,
    '流式 finish 不得在队列成功和持久化记录刷新前解锁最终答案'
  )
  assert.match(
    chartAnswerSource,
    /chatApi\.get\(ownerChatId,\s*\{\s*includeRecordData:\s*false\s*}\)/,
    '任务终态刷新应固定请求任务所属会话，并排除图表数据'
  )
  assert.doesNotMatch(
    handlePayloadSource,
    /_currentChat\.value\.records\[index\.value\]/,
    '旧任务事件不得通过消息下标写入当前页面会话'
  )
  assert.match(
    chartAnswerSource,
    /onFinish:\s*async\s*\(\{ record }\)\s*=>\s*\{[\s\S]*?emitFinishOnce\(Number\(record\.id \|\| currentRecord\.id\)\)/,
    '任务终态刷新完成后仍应统一通知父组件启动完成后动作'
  )
  assert.match(
    chartAnswerSource,
    /if \(latestRecord\?\.finish \|\| latestRecord\?\.finish_time\) \{[\s\S]*?await loadChartData[\s\S]*?await markFinalAnswerReady[\s\S]*?emits\('finish'/,
    '无活动任务恢复也必须先加载最终数据，再解锁答案并通知父组件'
  )
}

function testSendMessageKeepsOriginalChatContextAcrossAsyncTaskStart() {
  const chatIndexSource = fs.readFileSync(path.join(root, 'src/views/chat/index.vue'), 'utf8')
  const sendMessageStart = chatIndexSource.indexOf('const sendMessage = async')
  const sendMessageEnd = chatIndexSource.indexOf('const analysisAnswerRef', sendMessageStart)
  const sendMessageSource = chatIndexSource.slice(sendMessageStart, sendMessageEnd)

  assert.match(
    sendMessageSource,
    /const requestChatId = currentChatId\.value/,
    '发送前应固定记录所属会话 ID'
  )
  assert.match(
    sendMessageSource,
    /chat_id:\s*requestChatId/,
    '异步任务创建必须使用发送开始时捕获的会话 ID'
  )
  assert.match(
    sendMessageSource,
    /if \(currentChatId\.value !== requestChatId\) \{\s*return\s*}/,
    '任务创建返回后若用户已切换会话，不得继续操作当前页面组件'
  )
}

function testUnmountCleanupDoesNotStopTheChatGeneration() {
  const componentPaths = [
    'src/views/chat/RecommendQuestion.vue',
    'src/views/chat/RecommendQuestionQuick.vue',
    'src/views/chat/answer/AnalysisAnswer.vue',
    'src/views/chat/answer/PredictAnswer.vue',
  ]

  for (const relativePath of componentPaths) {
    const source = fs.readFileSync(path.join(root, relativePath), 'utf8')
    const unmountStart = source.indexOf('onBeforeUnmount(() => {')
    assert.ok(unmountStart >= 0, `${relativePath} 应包含卸载清理`)
    const unmountSource = source.slice(unmountStart, source.indexOf('\n})', unmountStart) + 3)
    assert.match(
      unmountSource,
      /stop\(false\)/,
      `${relativePath} 卸载时只能清理自身流，不能向父组件冒泡停止事件`
    )
  }

  const chatIndexSource = fs.readFileSync(path.join(root, 'src/views/chat/index.vue'), 'utf8')
  const stopStart = chatIndexSource.indexOf('function stop(func?:')
  const stopEnd = chatIndexSource.indexOf('const showFloatPopover', stopStart)
  const stopSource = chatIndexSource.slice(stopStart, stopEnd)
  assert.equal(
    (stopSource.match(/\.stop\(false\)/g) || []).length,
    8,
    '数据源或工作空间切换时的程序化清理不得冒泡成用户停止'
  )
  assert.doesNotMatch(
    stopSource,
    /\.stop\(\)/,
    '父组件停止子流时必须明确区分清理和用户停止'
  )
  assert.match(
    chatIndexSource,
    /function recordTerminalMessage\(record\?: ChatRecord\)[\s\S]*record\?\.stopped \? t\('chat\.task_error\.stopped'\)/,
    '用户主动停止也必须留下明确的终态消息，不能展示空白回答'
  )
}

testFinalAnswerVisibilityRequiresTerminalRefresh()
await testTerminalRecordsDoNotRestoreTasks()
await testSchedulerHonorsConcurrencyAndPriority()
await testSchedulerDedupesCancelsAndSkipsStaleApply()
await testCachedRequestReusesSamePendingQuery()
await testSmartQaTaskStorePollsIndependentlyAndDedupes()
await testSmartQaTaskStoreSkipsTerminalRecords()
await testSmartQaTaskStoreRefreshesCallbacksWithoutDuplicatePolling()
await testSmartQaTaskStoreDrainsUnreadEventsBeforeTerminalCallbacks()
await testSmartQaTaskStoreWaitsForTerminalRecordRefresh()
await testSmartQaTaskStoreBacksOffWhileTerminalRecordIsUnavailable()
await testSmartQaTaskStoreReportsTerminalCallbackErrors()
await testSmartQaTaskStoreReportsFailedTerminalStatus()
await testSmartQaTaskStoreRemovesEntriesAfterEventRequestFailure()
await testSmartQaTaskStoreCleansUpWhenTerminalErrorHandlerThrows()
await testSmartQaTaskStoreDetachesCallbacksButKeepsPolling()
await testSmartQaTaskStoreReplaysBufferedEventsWhenCallbacksReattach()
testChatTaskContextKeepsOldTaskOutOfCurrentChat()
testChatMessageRenderKeySurvivesActiveRecordRefresh()
testChartAnswerDefersPostAnswerActionsUntilTerminalRefresh()
testSendMessageKeepsOriginalChatContextAcrossAsyncTaskStart()
testUnmountCleanupDoesNotStopTheChatGeneration()
