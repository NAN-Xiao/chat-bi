import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./KnowledgeCitationList.vue', import.meta.url), 'utf8')

test('citation display omits internal chunk identifiers', () => {
  assert.match(source, /知识库/)
  assert.match(source, /版本/)
  assert.doesNotMatch(source, /片段 #\{\{ item\.chunk_id \}\}/)
})
