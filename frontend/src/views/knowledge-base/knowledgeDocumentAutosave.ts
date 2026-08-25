import type { DocumentBlock, DocumentPayload } from './knowledgePayloadTypes'

function editableBlock(block: DocumentBlock) {
  return {
    id: block.id,
    title: block.title,
    markdown: block.markdown,
    enabled: block.enabled,
  }
}

export function documentEditableSignature(payload: DocumentPayload) {
  return JSON.stringify({
    blocks: payload.blocks.map(editableBlock),
    tags: payload.tags,
    datasource_neutral: payload.datasource_neutral,
    object_references: payload.object_references,
  })
}

export function sameEditableBlock(left?: DocumentBlock, right?: DocumentBlock) {
  if (!left || !right) return false
  return (
    left.id === right.id &&
    left.title === right.title &&
    left.markdown === right.markdown &&
    left.enabled === right.enabled
  )
}

export function mergePersistedDocument(
  live: DocumentPayload,
  requestSnapshot: DocumentPayload,
  persisted: DocumentPayload
): DocumentPayload {
  const snapshotById = new Map(requestSnapshot.blocks.map((block) => [block.id, block]))
  const persistedById = new Map(persisted.blocks.map((block) => [block.id, block]))

  return {
    ...live,
    structure_revision: persisted.structure_revision,
    blocks: live.blocks.map((liveBlock) => {
      const persistedBlock = persistedById.get(liveBlock.id)
      if (!persistedBlock) return liveBlock
      const snapshotBlock = snapshotById.get(liveBlock.id)
      if (sameEditableBlock(liveBlock, snapshotBlock)) return { ...persistedBlock }
      return { ...liveBlock, block_revision: persistedBlock.block_revision }
    }),
  }
}
