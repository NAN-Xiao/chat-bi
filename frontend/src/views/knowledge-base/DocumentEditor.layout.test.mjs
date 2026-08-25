import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const editorSource = readFileSync(join(directory, 'editors/DocumentEditor.vue'), 'utf8')
const markdownEditorSource = readFileSync(
  join(directory, 'editors/KnowledgeMarkdownEditor.vue'),
  'utf8'
)
const frameSource = readFileSync(join(directory, 'editors/KnowledgeContentFrame.vue'), 'utf8')
const panelSource = readFileSync(join(directory, 'KnowledgeBaseV2Panel.vue'), 'utf8')

test('document editor renders every block with one active rich-text editor', () => {
  assert.match(editorSource, /v-for="\(block, index\) in modelValue\.blocks"/)
  assert.match(editorSource, /<KnowledgeMarkdownEditor[\s\S]*?v-if="activeBlockId === block\.id"/)
  assert.match(editorSource, /v-else[\s\S]*?v-dompurify-html="renderMarkdown\(block\.markdown\)"/)
  assert.match(editorSource, /class="document-canvas"/)
  assert.match(editorSource, /class="document-canvas" @contextmenu\.prevent/)
  assert.doesNotMatch(editorSource, /type="textarea"|class="markdown-editor"/)
})

test('toolbar exposes only the confirmed document commands', () => {
  for (const command of [
    'markdownEditor?.undo()',
    'markdownEditor?.redo()',
    'applyBlockFormat',
    'markdownEditor?.toggleBulletList()',
    'markdownEditor?.toggleOrderedList()',
    'markdownEditor?.toggleBlockquote()',
  ]) {
    assert.ok(editorSource.includes(command), `${command} should remain available`)
  }
  assert.doesNotMatch(editorSource, /toggleBold|toggleItalic|toggleUnderline|insertTable|setLink/)
  assert.doesNotMatch(editorSource, /aria-label="(?:加粗|斜体|下划线|表格|链接)"/)
  assert.match(markdownEditorSource, /TableKit\.configure/)
  assert.match(markdownEditorSource, /contentType: 'markdown'/)
  assert.match(markdownEditorSource, /\['b', 'i', 'u', 'k'\]/)
})

test('loading or switching blocks does not rewrite existing Markdown', () => {
  assert.match(markdownEditorSource, /onUpdate: \(\{ editor: instance \}\) =>/)
  assert.match(markdownEditorSource, /if \(applyingExternalContent \|\| props\.readonly\) return/)
  assert.match(markdownEditorSource, /contentType: 'markdown'/)
  assert.match(markdownEditorSource, /emitUpdate: false/)
  assert.doesNotMatch(markdownEditorSource, /onCreate:[\s\S]*?emit\('update:modelValue'/)
})

test('all knowledge-block structure actions remain available', () => {
  assert.match(editorSource, /async function addBlock\(\)/)
  assert.match(editorSource, /async function copyBlock\(block: DocumentBlock\)/)
  assert.match(editorSource, /function moveBlock\(blockId: string, offset: -1 \| 1\)/)
  assert.match(editorSource, /async function removeBlock\(block: DocumentBlock\)/)
  assert.match(editorSource, /updateBlock\(block\.id, \{ title: \$event \}\)/)
  assert.match(editorSource, /updateBlock\(block\.id, \{ enabled: \$event \}\)/)
  assert.match(editorSource, /普通文档至少需要保留一个知识块/)
  assert.match(editorSource, /await ElMessageBox\.confirm/)
})

test('shared content frame supports an editable title slot', () => {
  assert.match(editorSource, /import KnowledgeContentFrame from '.\/KnowledgeContentFrame\.vue'/)
  assert.match(frameSource, /<slot name="title">/)
  assert.match(frameSource, /class="content-frame-title"/)
})

test('page mode replaces the main editor drawer and keeps history auxiliary', () => {
  assert.match(panelSource, /v-else-if="selected" class="knowledge-editor-page"/)
  assert.doesNotMatch(panelSource, /class="knowledge-editor-drawer"|size="760px"/)
  assert.match(panelSource, /v-model="historyVisible" title="版本历史" size="420px"/)
  assert.match(panelSource, /class="knowledge-editor-page"[\s\S]*?<KnowledgePayloadEditor/)
})

test('directory and toolbar stay usable on narrow screens', () => {
  assert.match(editorSource, /@media \(max-width: 680px\)/)
  assert.match(editorSource, /\.directory-list \{[\s\S]*?overflow-x: auto;/)
  assert.match(editorSource, /\.format-toolbar \{[\s\S]*?overflow-x: auto;/)
  assert.match(
    editorSource,
    /\.document-canvas \{[\s\S]*?width: 100%;[\s\S]*?padding: 14px 10px 64px;/
  )
  assert.match(panelSource, /\.knowledge-lifecycle-actions \{[\s\S]*?overflow-x: auto;/)
})
