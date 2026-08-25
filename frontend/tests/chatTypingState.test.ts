import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldMarkRecordTyping } from '../src/views/chat/chatTypingState.ts'

test('重新生成时旧记录不显示生成中的 loading', () => {
  assert.equal(
    shouldMarkRecordTyping({
      recordIndex: 0,
      lastRecordIndex: 1,
      isTyping: true,
      isUnfinished: true,
      hasActiveTask: false,
    }),
    false
  )
})

test('当前最后一条未完成记录显示生成中的 loading', () => {
  assert.equal(
    shouldMarkRecordTyping({
      recordIndex: 1,
      lastRecordIndex: 1,
      isTyping: true,
      isUnfinished: true,
      hasActiveTask: false,
    }),
    true
  )
})

test('非最后一条记录拥有活动任务时仍显示生成中的 loading', () => {
  assert.equal(
    shouldMarkRecordTyping({
      recordIndex: 0,
      lastRecordIndex: 1,
      isTyping: true,
      isUnfinished: true,
      hasActiveTask: true,
    }),
    true
  )
})

test('页面恢复时活动任务不依赖页面级 typing 状态', () => {
  assert.equal(
    shouldMarkRecordTyping({
      recordIndex: 0,
      lastRecordIndex: 1,
      isTyping: false,
      isUnfinished: true,
      hasActiveTask: true,
    }),
    true
  )
})

test('终态记录即使残留 task_id 也不显示生成中的 loading', () => {
  assert.equal(
    shouldMarkRecordTyping({
      recordIndex: 0,
      lastRecordIndex: 1,
      isTyping: true,
      isUnfinished: false,
      hasActiveTask: true,
    }),
    false
  )
})
