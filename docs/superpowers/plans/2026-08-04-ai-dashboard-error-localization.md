# AI 看板错误中文化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AI 看板中的 Axios 英文状态错误转换为当前语言对应的用户提示，并保留后端返回的具体中文业务原因。

**Architecture:** 新增一个与 Vue UI 解耦的纯错误解析器，统一处理 Axios 响应、SSE 嵌套 JSON、业务 `error_type` 和无响应异常。`ChartAnswer.vue` 只负责把翻译函数传给解析器并写入记录，现有 `ErrorInfo.vue` 继续负责渲染。

**Tech Stack:** Vue 3、TypeScript、vue-i18n、Node.js `node:test`

## Global Constraints

- 仅修改 AI 看板错误展示，不改变全局 `request.ts` 行为。
- 优先保留后端返回的中文业务说明。
- 不直接展示 `Request failed with status code ...` 等 Axios 默认英文错误。
- 所有新增可见文案必须使用 i18n，提供简体中文、繁体中文和英文。

---

### Task 1: AI 看板错误解析器

**Files:**
- Create: `frontend/src/views/chat/answer/smartQaErrorMessage.ts`
- Create: `frontend/src/views/chat/answer/smartQaErrorMessage.test.mjs`

**Interfaces:**
- Consumes: `translate(key: string): string` 和任意异常值 `unknown`
- Produces: `resolveSmartQaErrorMessage(error: unknown, translate: Translate): string`

- [ ] **Step 1: 写失败测试**

创建测试，直接导入 TypeScript 纯函数并覆盖以下行为：

```js
import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveSmartQaErrorMessage } from './smartQaErrorMessage.ts'

const messages = {
  'chat.task_error.http_404': '问数任务不存在或已失效，请重新提问。',
  'chat.task_error.network': '网络连接异常，请检查网络后重试。',
  'chat.task_error.generic': '问数任务执行失败，请稍后重试。',
  'chat.permission_denied_tip': '当前账号没有访问本问题所需数据的权限。',
  'chat.task_error.data_unavailable': '当前数据源缺少本次问题所需的数据。',
}
const t = (key) => messages[key] || key

test('将 Axios 404 转换为中文任务失效提示', () => {
  const error = Object.assign(new Error('Request failed with status code 404'), {
    response: { status: 404, data: 'Task not found' },
  })
  assert.equal(resolveSmartQaErrorMessage(error, t), messages['chat.task_error.http_404'])
})

test('优先保留后端中文业务说明', () => {
  const error = { response: { status: 429, data: { message: '当前租户请求过于频繁，请稍后再试。' } } }
  assert.equal(resolveSmartQaErrorMessage(error, t), '当前租户请求过于频繁，请稍后再试。')
})

test('解析 SSE 嵌套 data_unavailable 中文消息', () => {
  const error = JSON.stringify({ error_type: 'data_unavailable', message: '当前数据源缺少英雄稀有度字段。' })
  assert.equal(resolveSmartQaErrorMessage(error, t), '当前数据源缺少英雄稀有度字段。')
})

test('无响应异常显示网络中文提示', () => {
  assert.equal(resolveSmartQaErrorMessage({ request: {} }, t), messages['chat.task_error.network'])
})

test('未知英文异常不直接展示给用户', () => {
  assert.equal(resolveSmartQaErrorMessage(new Error('opaque internal failure'), t), messages['chat.task_error.generic'])
})
```

- [ ] **Step 2: 运行测试并确认 RED**

Run: `cd frontend && node --test src/views/chat/answer/smartQaErrorMessage.test.mjs`

Expected: FAIL，提示找不到 `smartQaErrorMessage.ts` 或导出函数。

- [ ] **Step 3: 实现最小解析器**

实现以下规则：递归解析字符串 JSON、从 `response.data` 提取 `detail/message/msg/error`、识别中文、识别 `permission_denied/data_unavailable`、按状态码查 i18n 键、处理无响应和未知异常。

```ts
export type SmartQaErrorTranslate = (key: string) => string

const STATUS_KEYS: Record<number, string> = {
  400: 'chat.task_error.http_400',
  401: 'chat.task_error.http_401',
  403: 'chat.task_error.http_403',
  404: 'chat.task_error.http_404',
  422: 'chat.task_error.http_422',
  429: 'chat.task_error.http_429',
  500: 'chat.task_error.http_500',
  502: 'chat.task_error.http_502',
  503: 'chat.task_error.http_503',
  504: 'chat.task_error.http_504',
}

export function resolveSmartQaErrorMessage(
  error: unknown,
  translate: SmartQaErrorTranslate
): string {
  // 按设计文档中的优先级提取中文业务说明、业务类型和 HTTP 状态。
  return translate('chat.task_error.generic')
}
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run: `cd frontend && node --test src/views/chat/answer/smartQaErrorMessage.test.mjs`

Expected: 5 tests passed, 0 failed。

---

### Task 2: 接入 AI 看板并补齐 i18n

**Files:**
- Modify: `frontend/src/views/chat/answer/ChartAnswer.vue:1-29,204-234,462-466`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Test: `frontend/src/views/chat/answer/smartQaErrorMessage.test.mjs`

**Interfaces:**
- Consumes: `resolveSmartQaErrorMessage(error, t)` from Task 1
- Produces: AI 看板任务创建、轮询和恢复路径统一写入本地化错误文案

- [ ] **Step 1: 增加接入约束测试并确认 RED**

在测试中读取 `ChartAnswer.vue`，断言组件导入解析器、`failCurrentRecord` 调用解析器，并且不再拼接 `Error:${error}`：

```js
import fs from 'node:fs'

test('ChartAnswer 统一使用 AI 看板错误解析器', () => {
  const source = fs.readFileSync(new URL('./ChartAnswer.vue', import.meta.url), 'utf8')
  assert.match(source, /resolveSmartQaErrorMessage\(error, t\)/)
  assert.doesNotMatch(source, /Error:\$\{error\}/)
})
```

Run: `cd frontend && node --test src/views/chat/answer/smartQaErrorMessage.test.mjs`

Expected: FAIL，因为组件尚未调用解析器。

- [ ] **Step 2: 修改组件接入解析器**

在 `ChartAnswer.vue` 中导入 `useI18n` 和解析器，初始化 `const { t } = useI18n()`，将 `normalizeTaskError` 替换为解析器调用：

```ts
function failCurrentRecord(currentRecord: ChatRecord, error?: unknown) {
  const message = resolveSmartQaErrorMessage(error, t)
  updateOwnedRecord(currentRecord, { error: message })
  clearCurrentTask(currentRecord)
  _loading.value = false
  emits('error', currentRecord.id)
}
```

任务创建的 `catch` 也调用 `failCurrentRecord(currentRecord, error)`，不得再拼接英文 `Error:${error}`。

- [ ] **Step 3: 添加 i18n 文案**

在三个语言文件的 `chat` 节点下添加 `task_error`，键名保持一致。简体中文必须包含：

```json
"task_error": {
  "http_400": "请求参数有误，请检查后重试。",
  "http_401": "登录状态已失效，请重新登录。",
  "http_403": "当前账号没有执行此操作的权限。",
  "http_404": "问数任务不存在或已失效，请重新提问。",
  "http_422": "请求参数校验失败，请重新提问。",
  "http_429": "请求过于频繁，请稍后重试。",
  "http_500": "问数服务处理异常，请稍后重试。",
  "http_502": "问数服务网关异常，请稍后重试。",
  "http_503": "问数服务暂时不可用，请稍后重试。",
  "http_504": "问数服务响应超时，请稍后重试。",
  "data_unavailable": "当前数据源缺少本次问题所需的数据。",
  "network": "网络连接异常，请检查网络后重试。",
  "generic": "问数任务执行失败，请稍后重试。"
}
```

繁体中文和英文提供语义等价文案。

- [ ] **Step 4: 运行目标测试并确认 GREEN**

Run: `cd frontend && node --test src/views/chat/answer/smartQaErrorMessage.test.mjs`

Expected: 6 tests passed, 0 failed。

---

### Task 3: 完整验证

**Files:**
- Verify: `frontend/src/views/chat/answer/smartQaErrorMessage.ts`
- Verify: `frontend/src/views/chat/answer/ChartAnswer.vue`
- Verify: `frontend/src/i18n/zh-CN.json`
- Verify: `frontend/src/i18n/zh-TW.json`
- Verify: `frontend/src/i18n/en.json`

**Interfaces:**
- Consumes: Tasks 1-2 的完整实现
- Produces: 可构建、可回归验证的 AI 看板中文错误展示

- [ ] **Step 1: 运行 AI 看板相关测试**

Run: `cd frontend && node --test src/views/chat/answer/*.test.mjs`

Expected: 0 failed。

- [ ] **Step 2: 运行前端构建**

Run: `cd frontend && npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均成功，退出码为 0。

- [ ] **Step 3: 检查差异**

Run: `git diff --check && git status --short`

Expected: `git diff --check` 无输出；状态只包含本任务的设计、计划、实现和测试文件。

- [ ] **Step 4: 提交（仅在用户明确要求时）**

```powershell
git add -- docs/superpowers/specs/2026-08-04-ai-dashboard-error-localization-design.md `
  docs/superpowers/plans/2026-08-04-ai-dashboard-error-localization.md `
  frontend/src/views/chat/answer/smartQaErrorMessage.ts `
  frontend/src/views/chat/answer/smartQaErrorMessage.test.mjs `
  frontend/src/views/chat/answer/ChartAnswer.vue `
  frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json
git commit -m "修复 AI 看板英文错误提示"
```
