import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveKnowledgePageMode, knowledgePageNotice } from './knowledgePageMode.ts'

test('page mode is resolved only from the server capability', () => {
  assert.equal(resolveKnowledgePageMode({ management_mode: 'V2' }), 'V2')
  assert.equal(resolveKnowledgePageMode({ management_mode: 'V2', v2_write_enabled: false }), 'MAINTENANCE')
  assert.equal(resolveKnowledgePageMode({ management_mode: 'MAINTENANCE' }), 'MAINTENANCE')
  assert.equal(resolveKnowledgePageMode({ management_mode: 'UPGRADING' }), 'UPGRADING')
  assert.equal(resolveKnowledgePageMode({ management_mode: 'LEGACY' }), 'LEGACY')
  assert.equal(resolveKnowledgePageMode(undefined), 'CAPABILITIES_UNAVAILABLE')
  assert.notEqual(resolveKnowledgePageMode(undefined), 'LEGACY')
})

test('upgrading and maintenance notices are read-only', () => {
  assert.deepEqual(knowledgePageNotice('UPGRADING'), {
    titleKey: 'knowledge_base.mode_upgrading_title',
    descriptionKey: 'knowledge_base.mode_upgrading_description',
    readonly: true,
  })
  assert.deepEqual(knowledgePageNotice('MAINTENANCE'), {
    titleKey: 'knowledge_base.mode_maintenance_title',
    descriptionKey: 'knowledge_base.mode_maintenance_description',
    readonly: true,
  })
})
