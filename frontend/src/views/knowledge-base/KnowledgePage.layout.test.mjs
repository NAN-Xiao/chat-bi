import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const pageSource = readFileSync(join(directory, 'index.vue'), 'utf8')
const routerSource = readFileSync(join(directory, '../../router/index.ts'), 'utf8')
const editorSource = readFileSync(join(directory, 'KnowledgePayloadEditor.vue'), 'utf8')

test('knowledge page keeps the four editors split behind one orchestration layer', () => {
  assert.match(pageSource, /KnowledgeBaseV2Panel/)
  assert.match(editorSource, /DocumentEditor/)
  assert.match(editorSource, /BusinessKnowledgeEditor/)
  assert.match(editorSource, /EventKnowledgeEditor/)
  assert.match(editorSource, /JsonFieldKnowledgeEditor/)
})

test('existing Skills and knowledge routes remain available', () => {
  assert.match(routerSource, /path:\s*'data-skills'/)
  assert.match(routerSource, /path:\s*'knowledge-base'/)
})
