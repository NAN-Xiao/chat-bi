# Smart Q&A 继续提问刷新竞态修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除主任务终态刷新覆盖“继续提问”推荐结果的竞态，使推荐问题无需刷新页面即可显示。

**Architecture:** 流式 `finish` 只负责更新答案完成状态；任务终态先执行轻量记录刷新，再统一通知父组件启动推荐问题生成。现有任务轮询、图表数据独立加载和推荐问题接口保持不变。

**Tech Stack:** Vue 3、TypeScript、Node.js 内置测试运行器、现有 Smart Q&A 任务存储。

## Global Constraints

- 不为业务字段或数据源增加硬编码逻辑。
- 不增加静默字段回退；通过确定的执行顺序消除覆盖竞态。
- 不把图表数据重新放回整会话刷新请求。
- 保持错误、停止、恢复和任务去重行为不变。

---

### Task 1: 串行化答案完成与推荐问题生成

**Files:**
- Modify: `frontend/tests/chat-history-loading.test.mjs`
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue`

**Interfaces:**
- Consumes: `chatApi.get(id, { includeRecordData: false })`、`smartQaTaskStore` 的 `refreshRecord`/`onFinish` 回调顺序。
- Produces: 流式 `finish` 不提前发送父组件完成通知；终态刷新后由 `onFinish` 发送唯一通知。

- [x] **Step 1: Write the failing test**

在 `frontend/tests/chat-history-loading.test.mjs` 增加源码契约测试，断言：

```js
const chartAnswerSource = fs.readFileSync(
  path.join(root, 'src/views/chat/answer/ChartAnswer.vue'),
  'utf8'
)
const finishPayloadSection = chartAnswerSource.match(
  /case 'finish':[\s\S]*?break\s*\n\s*}/
)?.[0]
assert.ok(finishPayloadSection)
assert.doesNotMatch(finishPayloadSection, /emitFinishOnce/)
assert.match(
  chartAnswerSource,
  /chatApi\.get\(_currentChatId\.value,\s*\{\s*includeRecordData:\s*false\s*}\)/
)
assert.match(
  chartAnswerSource,
  /onFinish:[\s\S]*?emitFinishOnce\(Number\(record\.id \|\| currentRecord\.id\)\)/
)
```

- [x] **Step 2: Run test to verify it fails**

Run: `node frontend/tests/chat-history-loading.test.mjs`

Expected: FAIL，因为流式 `finish` 仍调用 `emitFinishOnce`，且刷新未使用 `includeRecordData: false`。

- [x] **Step 3: Write minimal implementation**

在 `ChartAnswer.vue` 中：

```ts
case 'finish':
  currentRecord.finish = true
  _currentChat.value.records[index.value].finish = true
  await markFinalAnswerReady()
  clearCurrentTask(currentRecord)
  break
```

并将刷新改为：

```ts
const chat = await chatApi.get(_currentChatId.value, { includeRecordData: false })
```

保留任务终态 `onFinish` 中现有的 `emitFinishOnce(...)`。

- [x] **Step 4: Run focused tests**

Run:

```powershell
node frontend/tests/chat-history-loading.test.mjs
node frontend/tests/chat-post-answer-actions.test.mjs
```

Expected: 两个测试均通过。

- [x] **Step 5: Run frontend type/build verification**

Run: `npm run build`（工作目录 `frontend`）

Expected: `vue-tsc -b` 与 Vite 构建通过。

- [x] **Step 6: Review diff and working tree boundaries**

Run: `git diff --check` 和针对本任务文件的 `git diff`。

Expected: 无空白错误；不包含用户现有工作簿与埋点文档改动。
