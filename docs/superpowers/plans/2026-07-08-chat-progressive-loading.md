# Chat Progressive Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement progressive Chat conversation loading so records render immediately, the latest unfinished answer restores first, and historical chart data loads with bounded concurrency.

**Architecture:** Add a focused frontend scheduler utility for prioritized bounded async work. Keep task restoration inside `ChartAnswer.vue`, but let `Chat index.vue` orchestrate historical chart data loading and invalidate stale work by chat load version. Share answer restoration predicates through `taskRestore.ts`.

**Tech Stack:** Vue 3 Composition API, TypeScript, existing Node `.mjs` test harness with `typescript.transpileModule`, Element Plus Secondary, existing `chatApi`.

## Global Constraints

- Do not change backend task execution.
- Do not change SQL generation, semantic-layer logic, metric definitions, datasource permissions, or hidden analysis/predict action policy.
- Use finite historical chart-data concurrency, default `maxConcurrency = 3`.
- The latest unfinished answer restoration must not wait behind historical chart-data jobs.
- Stale async work from an older chat must not write into the current chat.
- Keep changes scoped to Chat progressive loading and related tests.

---

### Task 1: Priority Scheduler Utility

**Files:**
- Create: `frontend/src/views/chat/answer/chatLoadScheduler.ts`
- Modify: `frontend/tests/chat-history-loading.test.mjs`

**Interfaces:**
- Produces: `createChatLoadScheduler(options?: { maxConcurrency?: number }): ChatLoadScheduler`
- Produces: `ChatLoadScheduler.enqueue<T>(task: ChatLoadTask<T>): Promise<T | undefined>`
- Produces: `ChatLoadScheduler.cancel(scope?: string): void`
- Produces: `ChatLoadScheduler.pendingCount(): number`
- Produces: `ChatLoadScheduler.runningCount(): number`
- Produces: `ChatLoadTask<T>` with `{ key: string; scope?: string; priority?: number; run: () => Promise<T>; apply?: (value: T) => void; isStale?: () => boolean }`

- [ ] **Step 1: Write failing scheduler tests**

Add tests to `frontend/tests/chat-history-loading.test.mjs`:

```javascript
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

  assert.deepEqual(started, ['high', 'medium'])
  release.shift()()
  await Promise.resolve()
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
  scheduler.cancel('chat:1')
  assert.equal(await cancelled, undefined)
  assert.equal(scheduler.pendingCount(), 0)
  void blocked
}
```

At the bottom of the file, call both new tests before existing completion.

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
```

Expected: FAIL because `src/views/chat/answer/chatLoadScheduler.ts` does not exist or `createChatLoadScheduler` is not exported.

- [ ] **Step 3: Implement scheduler**

Create `frontend/src/views/chat/answer/chatLoadScheduler.ts`:

```typescript
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

export function createChatLoadScheduler(options: { maxConcurrency?: number } = {}): ChatLoadScheduler {
  const maxConcurrency = Math.max(1, options.maxConcurrency ?? 3)
  const queue: QueueItem[] = []
  const activeByKey = new Map<string, Promise<unknown | undefined>>()
  let running = 0
  let sequence = 0

  function sortQueue() {
    queue.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.sequence - b.sequence)
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
          pump()
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
      pump()
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
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
```

Expected: PASS.

### Task 2: Shared Answer Restoration Predicates

**Files:**
- Modify: `frontend/src/views/chat/answer/taskRestore.ts`
- Modify: `frontend/src/views/chat/index.vue`
- Modify: `frontend/tests/chat-history-loading.test.mjs`

**Interfaces:**
- Consumes: `isRestorableAnswerRecord(record, isLatestRecord)`
- Produces: parent Chat page uses the shared predicate for unfinished state.

- [ ] **Step 1: Ensure predicate tests exist**

`frontend/tests/chat-history-loading.test.mjs` must assert:

```javascript
assert.equal(isRestorableAnswerRecord({ id: 6, task_id: 'running-task', analysis: 'partial' }, true), true)
assert.equal(isRestorableAnswerRecord({ id: 7, analysis: 'partial' }, true), true)
assert.equal(isRestorableAnswerRecord({ id: 7, analysis: 'partial' }, false), false)
```

- [ ] **Step 2: Run predicate tests**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
```

Expected: PASS once Task 1 is complete and current predicate behavior is present.

- [ ] **Step 3: Confirm Chat page consumes shared predicate**

`frontend/src/views/chat/index.vue` should import:

```typescript
import { isRestorableAnswerRecord } from './answer/taskRestore'
```

and implement:

```typescript
function isUnfinishedAnswerRecord(record?: ChatRecord) {
  const recordIndex = record ? currentChat.value.records.indexOf(record) : -1
  return isRestorableAnswerRecord(record, recordIndex === currentChat.value.records.length - 1)
}
```

- [ ] **Step 4: Run tests**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
```

Expected: PASS.

### Task 3: ChartAnswer External Chart Data Loader

**Files:**
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue`

**Interfaces:**
- Produces: `loadChartData(recordId?: number): Promise<void>`
- Produces: exposed method `{ loadChartData }`
- Existing `getChatData(recordId)` remains as compatibility wrapper.

- [ ] **Step 1: Add minimal implementation with existing behavior**

Change `getChatData` from fire-and-forget to returning the Promise chain through a new function:

```typescript
function loadChartData(recordId?: number) {
  if (!recordId) {
    return Promise.resolve()
  }
  const currentRecord = _currentChat.value.records.find((record) => record.id === recordId)
  if (hasRecordData(currentRecord)) {
    return Promise.resolve()
  }

  loadingData.value = true
  return chatApi
    .get_chart_data(recordId)
    .then((response) => {
      _currentChat.value.records.forEach((record) => {
        if (record.id === recordId) {
          record.data = response
          if (response?.status === 'business_notice') {
            record.chart = ''
            record.analysis_notice = response.notice
            record.analysis = response.message || response.reason || record.analysis
          }
        }
      })
    })
    .finally(() => {
      loadingData.value = false
      emits('scrollBottom')
    })
}

function getChatData(recordId?: number) {
  void loadChartData(recordId)
}
```

Expose:

```typescript
defineExpose({ sendMessage, index: () => index.value, stop, restoreRecordTask, loadChartData })
```

- [ ] **Step 2: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: `vue-tsc -b && vite build` exits 0.

### Task 4: Parent Progressive Historical Chart Loading

**Files:**
- Modify: `frontend/src/views/chat/index.vue`
- Test: `frontend/tests/chat-history-loading.test.mjs`

**Interfaces:**
- Consumes: `createChatLoadScheduler`
- Consumes: `answer.loadChartData(recordId)`
- Produces: `scheduleVisibleChartDataLoad()`
- Produces: `scheduleHistoricalChartDataLoads()`

- [ ] **Step 1: Add scheduler import and state**

Add imports:

```typescript
import { createChatLoadScheduler } from './answer/chatLoadScheduler'
```

Add module state near `chartAnswerRef`:

```typescript
const chartLoadScheduler = createChatLoadScheduler({ maxConcurrency: 3 })
let chatLoadVersion = 0

function nextChatLoadVersion() {
  chatLoadVersion += 1
  chartLoadScheduler.cancel()
  return chatLoadVersion
}
```

- [ ] **Step 2: Increment load version on chat replacement**

In `loadChatById`, before assigning `currentChat.value = info`, call:

```typescript
const version = nextChatLoadVersion()
currentChat.value = info
```

After `onClickHistory(info)`, call:

```typescript
scheduleHistoricalChartDataLoads(version)
```

In `createNewChatSimple`, `createNewChat`, and `resetChatContext` if present, call `nextChatLoadVersion()` before replacing or clearing `currentChat`.

- [ ] **Step 3: Add helper to collect answer refs**

Add:

```typescript
function getChartAnswerRefs() {
  const refs = chartAnswerRef.value
  if (!refs) {
    return []
  }
  return refs instanceof Array ? refs : [refs]
}
```

Update `restoreChartAnswers()` to use `getChartAnswerRefs()`.

- [ ] **Step 4: Add historical load scheduler**

Add:

```typescript
function recordHasChartData(record?: ChatRecord) {
  if (!record?.data) {
    return false
  }
  if (typeof record.data === 'string') {
    return record.data.trim().length > 0
  }
  return true
}

function shouldScheduleChartData(record?: ChatRecord) {
  return !!record?.id && !!record.chart && !recordHasChartData(record)
}

function findChartAnswerByRecordIndex(recordIndex: number) {
  return getChartAnswerRefs().find((answer) => answer?.index?.() === recordIndex)
}

function scheduleHistoricalChartDataLoads(version = chatLoadVersion) {
  nextTick(() => {
    const chatId = currentChatId.value
    if (!chatId || version !== chatLoadVersion) {
      return
    }
    currentChat.value.records.forEach((record, index) => {
      if (!shouldScheduleChartData(record) || isUnfinishedAnswerRecord(record)) {
        return
      }
      const distanceFromLatest = currentChat.value.records.length - index
      const priority = distanceFromLatest <= 5 ? 50 - distanceFromLatest : 10 - distanceFromLatest
      chartLoadScheduler.enqueue({
        key: `chat:${chatId}:record:${record.id}:chart-data`,
        scope: `chat:${chatId}`,
        priority,
        isStale: () => version !== chatLoadVersion || currentChatId.value !== chatId,
        run: async () => {
          const answer = findChartAnswerByRecordIndex(index)
          await answer?.loadChartData?.(record.id)
        },
      }).catch((error) => {
        console.error('Load historical chart data failed:', error)
      })
    })
  })
}
```

- [ ] **Step 5: Trigger scheduler after restoring visible chat state**

After `restoreChartAnswers()` in `restoreCurrentChatFromSession()` and `restoreVisibleChatState()`, call:

```typescript
scheduleHistoricalChartDataLoads(chatLoadVersion)
```

- [ ] **Step 6: Run tests and build**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
npm run build
```

Expected: test exits 0; build exits 0.

### Task 5: Final Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run targeted test**

Run:

```powershell
cd frontend
node tests/chat-history-loading.test.mjs
```

Expected: exit 0.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: exit 0. Existing Rollup/Vite chunk warnings may appear.

- [ ] **Step 3: Inspect diff**

Run:

```powershell
git diff -- frontend/src/views/chat/index.vue frontend/src/views/chat/answer/ChartAnswer.vue frontend/src/views/chat/answer/taskRestore.ts frontend/src/views/chat/answer/chatLoadScheduler.ts frontend/tests/chat-history-loading.test.mjs
```

Expected: diff only includes progressive loading, restoration predicates, scheduler, and tests.
