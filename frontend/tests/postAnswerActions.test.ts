import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldShowStopReplyButton } from '../src/views/chat/answer/postAnswerActions.ts'

test('主回答仍在生成时显示停止按钮', () => {
  assert.equal(
    shouldShowStopReplyButton({
      hasUnfinishedGeneration: true,
      hasRecommendQuestionsLoading: false,
    }),
    true
  )
})

test('仅推荐问题仍在生成时不显示停止按钮', () => {
  assert.equal(
    shouldShowStopReplyButton({
      hasUnfinishedGeneration: false,
      hasRecommendQuestionsLoading: true,
    }),
    false
  )
})

test('主回答和推荐问题都结束后不显示停止按钮', () => {
  assert.equal(
    shouldShowStopReplyButton({
      hasUnfinishedGeneration: false,
      hasRecommendQuestionsLoading: false,
    }),
    false
  )
})
