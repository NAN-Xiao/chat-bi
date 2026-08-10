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
    }),
    true
  )
})
