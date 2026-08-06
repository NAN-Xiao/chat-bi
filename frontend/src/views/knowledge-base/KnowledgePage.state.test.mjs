import assert from 'node:assert/strict'
import test from 'node:test'
import { knowledgeActionState } from './knowledgeEditorState.ts'

test('publishing disables every mutating action', () => {
  assert.deepEqual(
    knowledgeActionState({
      status: 'READY_TO_PUBLISH',
      canManage: true,
      hasDraft: true,
      publishJobStatus: 'RUNNING',
    }),
    { save: false, validate: false, publish: false, archive: false, rollback: false }
  )
})

test('a draft can publish only after validation and when no job is active', () => {
  assert.equal(
    knowledgeActionState({ status: 'READY_TO_PUBLISH', canManage: true, hasDraft: true }).publish,
    true
  )
  assert.equal(
    knowledgeActionState({ status: 'DRAFT', canManage: true, hasDraft: true }).publish,
    false
  )
})

test('a user without manage permission cannot mutate a draft', () => {
  assert.deepEqual(
    knowledgeActionState({ status: 'READY_TO_PUBLISH', canManage: false, hasDraft: true }),
    { save: false, validate: false, publish: false, archive: false, rollback: false }
  )
})
