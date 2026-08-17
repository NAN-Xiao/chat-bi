import assert from 'node:assert/strict'
import test from 'node:test'
import { serializeKnowledgeDraft } from './knowledgePayloadTypes.ts'

test('document serialization preserves metadata hidden from the block editor', () => {
  const payload = serializeKnowledgeDraft({
    knowledge_type: 'DOCUMENT',
    blocks: [{ id: 'block-1', title: '正文', markdown: '内容', enabled: true, block_revision: 2 }],
    structure_revision: 3,
    tags: ['内部'],
    datasource_neutral: false,
    object_references: [{ object_type: 'TABLE', schema: 'public', table: 'orders' }],
  })
  assert.deepEqual(payload.tags, ['内部'])
  assert.equal(payload.datasource_neutral, false)
  assert.deepEqual(payload.object_references, [{ object_type: 'TABLE', schema: 'public', table: 'orders' }])
})
