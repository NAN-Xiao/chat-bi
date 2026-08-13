import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const panelSource = readFileSync(new URL('./KnowledgeBaseV2Panel.vue', import.meta.url), 'utf8')
const legacySource = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')

test('V2 create and edit flows expose the source upload control', () => {
  assert.match(panelSource, /label="文档内容"/)
  assert.match(panelSource, /拖拽或点击上传源文件/)
  assert.match(panelSource, /knowledgeBaseApi\.replaceDraftFile/)
  assert.match(panelSource, /accept="\.md,\.markdown,\.docx,\.xlsx"/)
  assert.match(panelSource, /payload\.knowledge_type === 'DOCUMENT'/)
})

test('legacy and V2 upload selectors support the same file extensions', () => {
  assert.match(legacySource, /accept="\.md,\.markdown,\.docx,\.xlsx"/)
  assert.match(legacySource, /name\.endsWith\('\.xlsx'\)/)
})
