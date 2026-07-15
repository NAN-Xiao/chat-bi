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
  vm.runInNewContext(output, {
    exports: module.exports,
    module,
    require,
    URLSearchParams,
    setTimeout,
    clearTimeout,
  }, { filename: filePath })
  return module.exports
}

async function flushMicrotasks(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await Promise.resolve()
  }
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
  assert.equal(shouldRestoreWhenAnswerRecordChanges(nextRunningRecord, nextRunningRecord, true), false)
  assert.equal(shouldRestoreWhenAnswerRecordChanges(previousRecord, { id: 10, finish: true }, true), false)

  assert.equal(shouldMarkChatTypingOnRestore([]), false)
  assert.equal(shouldMarkChatTypingOnRestore([{ id: 11, question: '历史已完成', finish: true }]), false)
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

function testChartAnswerDefersPostAnswerActionsUntilTerminalRefresh() {
  const chartAnswerSource = fs.readFileSync(
    path.join(root, 'src/views/chat/answer/ChartAnswer.vue'),
    'utf8'
  )
  const handlePayloadStart = chartAnswerSource.indexOf('async function handlePayload')
  const refreshRecordStart = chartAnswerSource.indexOf('async function refreshCurrentRecord')
  const handlePayloadSource = chartAnswerSource.slice(handlePayloadStart, refreshRecordStart)
  const finishCaseSource = handlePayloadSource.match(/case 'finish':[\s\S]*?break/)?.[0]

  assert.ok(finishCaseSource, 'ChartAnswer 应包含流式 finish 事件处理')
  assert.doesNotMatch(
    finishCaseSource,
    /emitFinishOnce/,
    '流式 finish 只能结束答案状态，不能提前启动完成后动作'
  )
  assert.match(
    chartAnswerSource,
    /chatApi\.get\(_currentChatId\.value,\s*\{\s*includeRecordData:\s*false\s*}\)/,
    '任务终态刷新应排除图表数据，避免旧的整会话大响应延迟覆盖推荐问题'
  )
  assert.match(
    chartAnswerSource,
    /onFinish:\s*async\s*\(\{ record }\)\s*=>\s*\{[\s\S]*?emitFinishOnce\(Number\(record\.id \|\| currentRecord\.id\)\)/,
    '任务终态刷新完成后仍应统一通知父组件启动完成后动作'
  )
}

await testTerminalRecordsDoNotRestoreTasks()
await testSchedulerHonorsConcurrencyAndPriority()
await testSchedulerDedupesCancelsAndSkipsStaleApply()
await testCachedRequestReusesSamePendingQuery()
await testSmartQaTaskStorePollsIndependentlyAndDedupes()
await testSmartQaTaskStoreSkipsTerminalRecords()
await testSmartQaTaskStoreRefreshesCallbacksWithoutDuplicatePolling()
await testSmartQaTaskStoreDetachesCallbacksButKeepsPolling()
await testSmartQaTaskStoreReplaysBufferedEventsWhenCallbacksReattach()
testChartAnswerDefersPostAnswerActionsUntilTerminalRefresh()
