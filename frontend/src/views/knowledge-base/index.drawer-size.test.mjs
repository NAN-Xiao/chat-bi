import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')

assert.match(
  source,
  /v-model="detailVisible"[\s\S]*?size="64%"[\s\S]*?modal-class="knowledge-base-drawer knowledge-document-drawer"/,
  'knowledge detail drawer should use about two thirds of the viewport'
)

assert.match(
  source,
  /\.knowledge-document-drawer\s*\{[\s\S]*?\.ed-drawer\s*\{[^}]*max-width:\s*1280px/s,
  'knowledge detail drawer should have a desktop maximum width'
)

assert.doesNotMatch(
  source,
  /v-model="detailVisible"[\s\S]*?size="calc\(100% - 48px\)"/,
  'knowledge detail drawer should not remain nearly fullscreen'
)

console.log('Knowledge base detail drawer size tests passed')
