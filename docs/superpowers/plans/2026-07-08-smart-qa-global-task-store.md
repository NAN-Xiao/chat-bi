# Smart QA Global Task Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Smart Q&A 任务在切换页面、切换会话记录后继续由前端全局管理器轮询，并在用户切回时保持执行状态与最终展示一致。

**Architecture:** 新增一个前端任务运行时模块，按 `tenantId + chatId + recordId` 管理任务状态、offset 与轮询生命周期。`ChartAnswer.vue` 从“任务拥有者”降级为展示组件和任务注册入口，聊天页在加载会话时把可恢复记录重新注册到全局任务运行时。

**Tech Stack:** Vue 3、Pinia 风格 store、现有 `chatApi.startTask/getTaskEvents/getRecordTask`、Node `.mjs` 前端单测。

## Global Constraints

- 不回滚当前工作区已有改动。
- 普通 Smart Q&A 任务使用后端任务队列，不回退到流式 `/chat/question`。
- 终态以服务端为准：`finish/finish_time/error/stopped` 记录不得继续轮询。
- 任务 key 必须包含租户/会话/记录边界，避免跨工作空间串状态。
- 第一版只覆盖同一个前端应用实例内的切页面、切会话不中断；浏览器多 Tab 共享暂不做。

---

### Task 1: Global Task Runtime

**Files:**
- Create: `frontend/src/views/chat/answer/smartQaTaskStore.ts`
- Modify: `frontend/tests/chat-history-loading.test.mjs`

**Interfaces:**
- Produces: `createSmartQaTaskStore(options)`, `smartQaTaskStore`, `buildSmartQaTaskKey(input)`.
- Produces: `registerTask(input)`, `ensureTask(input)`, `pauseTask(key)`, `getTask(key)`, `isTaskRunning(key)`.

- [ ] **Step 1: Write failing tests**

Add tests proving a registered task continues polling without a mounted answer component and reaches `succeeded`.

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend; node tests/chat-history-loading.test.mjs`
Expected: FAIL because `smartQaTaskStore.ts` does not exist.

- [ ] **Step 3: Implement minimal runtime**

Create a runtime that stores task entries in module state, polls with injected APIs, updates offset, refreshes record/data on terminal status, and deduplicates duplicate registrations for the same key.

- [ ] **Step 4: Run tests**

Run: `cd frontend; node tests/chat-history-loading.test.mjs`
Expected: PASS.

### Task 2: ChartAnswer Delegation

**Files:**
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue`
- Modify: `frontend/src/views/chat/answer/taskRestore.ts`

**Interfaces:**
- Consumes: `smartQaTaskStore.ensureTask(...)`.
- Keeps exposed methods: `sendMessage`, `stop`, `restoreRecordTask`, `loadChartData`.

- [ ] **Step 1: Write failing tests or extend runtime tests**

Add assertions that duplicate task registration returns the same entry and `pauseTask` only pauses local observation when explicitly called.

- [ ] **Step 2: Verify failure**

Run the frontend node test and confirm failure before production changes.

- [ ] **Step 3: Replace component-owned polling**

Move task start/restore polling calls from `ChartAnswer.vue` into `smartQaTaskStore.ensureTask`, while preserving current emits for finish/error/loading updates.

- [ ] **Step 4: Verify tests**

Run node tests and then `npm run build` if time allows.

### Task 3: Chat Page Rehydration

**Files:**
- Modify: `frontend/src/views/chat/index.vue`

**Interfaces:**
- Consumes: `smartQaTaskStore.ensureTask(...)`.
- Uses existing `loadChatById`, `restoreChartAnswers`, `scheduleHistoricalChartDataLoads`.

- [ ] **Step 1: Write failing test for terminal-state classification if needed**

Keep terminal records from re-registering and active records registering on chat load.

- [ ] **Step 2: Register active records on chat load**

After `loadChatById` and `getChatList`, register restorable records into the global task runtime.

- [ ] **Step 3: Keep UI state synchronized**

On runtime finish, refresh record/data and trigger existing `onChartAnswerFinish` behavior for the latest record.

- [ ] **Step 4: Verify**

Run `cd frontend; node tests/chat-history-loading.test.mjs` and `cd frontend; npm run build`.
