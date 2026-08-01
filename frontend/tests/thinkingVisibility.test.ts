import assert from 'node:assert/strict'
import test from 'node:test'

import {
  initialThinkingVisibility,
  isThinkingActive,
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

test('加载中时也算思考中', () => {
  assert.equal(isThinkingActive(false, true), true)
  assert.equal(isThinkingActive(false, false), false)
})
