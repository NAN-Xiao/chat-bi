import assert from 'node:assert/strict'
import test from 'node:test'
import { documentEditableSignature, mergePersistedDocument } from './knowledgeDocumentAutosave.ts'

function payload(blocks, structureRevision = 1) {
  return {
    knowledge_type: 'DOCUMENT',
    blocks,
    structure_revision: structureRevision,
    tags: [],
    datasource_neutral: false,
    object_references: [],
  }
}

function block(id, markdown, revision = 1) {
  return { id, title: id, markdown, enabled: true, block_revision: revision }
}

test('editable signature ignores server revisions', () => {
  assert.equal(
    documentEditableSignature(payload([block('a', '正文', 1)], 1)),
    documentEditableSignature(payload([block('a', '正文', 9)], 12))
  )
})

test('an older save response cannot overwrite text typed while it was in flight', () => {
  const snapshot = payload([block('a', '请求快照', 1)])
  const live = payload([block('a', '请求期间的新输入', 1)])
  const persisted = payload([block('a', '请求快照', 2)], 3)

  const merged = mergePersistedDocument(live, snapshot, persisted)

  assert.equal(merged.blocks[0].markdown, '请求期间的新输入')
  assert.equal(merged.blocks[0].block_revision, 2)
  assert.equal(merged.structure_revision, 3)
})

test('unchanged snapshot content adopts the persisted block and revision', () => {
  const snapshot = payload([block('a', '正文', 1)])
  const persisted = payload([{ ...block('a', '正文', 2), title: '服务端标题' }], 4)

  const merged = mergePersistedDocument(snapshot, snapshot, persisted)

  assert.equal(merged.blocks[0].title, '服务端标题')
  assert.equal(merged.blocks[0].block_revision, 2)
})

test('a local reorder made during save remains authoritative', () => {
  const snapshot = payload([block('a', 'A'), block('b', 'B')])
  const live = payload([block('b', 'B'), block('a', 'A')])
  const persisted = payload([block('a', 'A', 2), block('b', 'B', 2)], 5)

  const merged = mergePersistedDocument(live, snapshot, persisted)

  assert.deepEqual(
    merged.blocks.map(({ id }) => id),
    ['b', 'a']
  )
  assert.equal(merged.structure_revision, 5)
})
