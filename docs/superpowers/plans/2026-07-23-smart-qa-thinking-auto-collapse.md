# Smart Q&A 思考过程自动展开与收起实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Smart Q&A 在答案生成期间默认展开思考过程，并在生成完成后自动收起，同时尊重生成期间的用户手动收起操作。

**Architecture:** 将无 UI 依赖的显示状态转换提取为 `thinkingVisibility.ts`，由 `BaseAnswer.vue` 在初始挂载和 `message.isTyping` 边沿变化时调用。流式内容更新不改变 `isTyping`，因此不会覆盖用户手动选择；完成边沿统一收起。

**Tech Stack:** Vue 3 Composition API、TypeScript、Node.js 内置测试运行器。

## Global Constraints

- 新任务进入生成态时默认展开，历史已完成消息首次挂载时保持收起。
- 用户在生成期间手动收起后，流式内容更新不得再次展开。
- `message.isTyping` 从 `true` 变为 `false` 时自动收起，完成后仍允许手动展开。
- 不修改后端持久化、SSE 协议或 reasoning 字段。
- 不删除现有 `chat.expand_thinking_block` 配置，仅停止在该组件中用它决定生成态初始展示。

---

### Task 1: 思考过程显示状态机

**Files:**
- Create: `frontend/src/views/chat/answer/thinkingVisibility.ts`
- Create: `frontend/tests/thinkingVisibility.test.ts`
- Modify: `frontend/src/views/chat/answer/BaseAnswer.vue`

**Interfaces:**
- Produces: `initialThinkingVisibility(isTyping: boolean): boolean`
- Produces: `transitionThinkingVisibility(currentShow: boolean, previousTyping: boolean, currentTyping: boolean): boolean`
- Consumes: `BaseAnswer.vue` 的 `props.message.isTyping` 和现有 `show` 状态。

- [ ] **Step 1: 编写失败的状态转换测试**

创建 `frontend/tests/thinkingVisibility.test.ts`，断言以下行为：初始生成态展开、初始完成态收起、进入生成态展开、生成期间保持当前状态、完成时收起。

```typescript
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  initialThinkingVisibility,
  transitionThinkingVisibility,
} from '../src/views/chat/answer/thinkingVisibility.ts'

test('初始生成态默认展开思考过程', () => {
  assert.equal(initialThinkingVisibility(true), true)
})

test('初始完成态默认收起思考过程', () => {
  assert.equal(initialThinkingVisibility(false), false)
})

test('进入生成态时展开思考过程', () => {
  assert.equal(transitionThinkingVisibility(false, false, true), true)
})

test('生成期间保留用户手动选择', () => {
  assert.equal(transitionThinkingVisibility(false, true, true), false)
  assert.equal(transitionThinkingVisibility(true, true, true), true)
})

test('生成完成时收起思考过程', () => {
  assert.equal(transitionThinkingVisibility(true, true, false), false)
})
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `cd frontend; node --test tests/thinkingVisibility.test.ts`

Expected: FAIL，错误指向 `thinkingVisibility.ts` 模块不存在。

- [ ] **Step 3: 实现最小状态转换函数**

创建 `frontend/src/views/chat/answer/thinkingVisibility.ts`：

```typescript
export function initialThinkingVisibility(isTyping: boolean): boolean {
  return isTyping
}

export function transitionThinkingVisibility(
  currentShow: boolean,
  previousTyping: boolean,
  currentTyping: boolean
): boolean {
  if (previousTyping === currentTyping) {
    return currentShow
  }
  return currentTyping
}
```

- [ ] **Step 4: 运行状态转换测试并确认通过**

Run: `cd frontend; node --test tests/thinkingVisibility.test.ts`

Expected: PASS，5 个测试全部通过。

- [ ] **Step 5: 将状态转换接入 BaseAnswer**

在 `BaseAnswer.vue` 中导入 `watch` 和两个状态转换函数，移除 `useChatConfigStore` 依赖。挂载时使用 `initialThinkingVisibility`，并监听 `props.message.isTyping`：

```typescript
watch(
  () => !!props.message.isTyping,
  (currentTyping, previousTyping) => {
    show.value = transitionThinkingVisibility(show.value, previousTyping, currentTyping)
  }
)

onMounted(() => {
  show.value = initialThinkingVisibility(!!props.message.isTyping)
})
```

- [ ] **Step 6: 运行针对性测试和 TypeScript 构建检查**

Run: `cd frontend; node --test tests/thinkingVisibility.test.ts`

Expected: PASS，5 个测试全部通过。

Run: `cd frontend; npm run build`

Expected: exit code 0，Vue TypeScript 检查和 Vite 构建成功。

- [ ] **Step 7: 检查最终差异**

Run: `git diff -- frontend/src/views/chat/answer/BaseAnswer.vue frontend/src/views/chat/answer/thinkingVisibility.ts frontend/tests/thinkingVisibility.test.ts docs/superpowers/specs/2026-07-23-smart-qa-thinking-auto-collapse-design.md docs/superpowers/plans/2026-07-23-smart-qa-thinking-auto-collapse.md`

Expected: 只包含本功能的状态机、组件接线、测试和文档，不包含用户现有后端改动。
