import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const directory = dirname(fileURLToPath(import.meta.url))
const pageSource = readFileSync(join(directory, 'index.vue'), 'utf8')
const routerSource = readFileSync(join(directory, '../../router/index.ts'), 'utf8')
const menuItemSource = readFileSync(join(directory, '../../components/layout/MenuItem.vue'), 'utf8')
const editorSource = readFileSync(join(directory, 'KnowledgePayloadEditor.vue'), 'utf8')
const layoutSource = readFileSync(join(directory, '../../components/layout/LayoutDsl.vue'), 'utf8')

test('knowledge page keeps the four editors split behind one orchestration layer', () => {
  assert.match(pageSource, /KnowledgeBaseV2Panel/)
  assert.match(editorSource, /DocumentEditor/)
  assert.match(editorSource, /BusinessKnowledgeEditor/)
  assert.match(editorSource, /EventKnowledgeEditor/)
  assert.match(editorSource, /JsonFieldKnowledgeEditor/)
})

test('knowledge management expands to platform and workspace child menus', () => {
  assert.match(routerSource, /path:\s*'data-skills'/)
  assert.match(routerSource, /path:\s*'knowledge-base'/)
  assert.match(routerSource, /redirect:\s*'\/system\/knowledge-base\/platform'/)
  assert.match(routerSource, /path:\s*'platform'[\s\S]*title:\s*t\('knowledge_base\.platform_knowledge_base'\)/)
  assert.match(routerSource, /path:\s*'workspace'[\s\S]*title:\s*t\('knowledge_base\.workspace_knowledge_base'\)/)
  assert.match(menuItemSource, /if \(children\?\.length\)/)
  assert.match(menuItemSource, /ElSubMenu/)
  assert.match(menuItemSource, /children\.map/)
})

test('knowledge page keeps capability and list failures separate from legacy and empty states', () => {
  assert.match(pageSource, /pageMode\.value = 'CAPABILITIES_UNAVAILABLE'/)
  assert.match(pageSource, /listError\.value = true/)
  assert.match(pageSource, /v-if="listError"/)
  assert.match(pageSource, /v-else-if="!visibleCards\.length"/)
  assert.doesNotMatch(pageSource, /catch[\s\S]{0,180}pageMode\.value = 'LEGACY'/)
})

test('knowledge page exposes platform knowledge as read-only to non-managers', () => {
  assert.match(pageSource, /<el-option label="平台知识库" value="PLATFORM_PUBLIC"/)
  assert.match(pageSource, /<el-option label="工作空间知识库" value="ADMIN_PUBLIC"/)
  assert.match(pageSource, /v-if="canCreateKnowledge"/)
  assert.match(pageSource, /if \(!row\.can_manage\) return/)
})

test('workspace management keeps a usable content width on mobile', () => {
  assert.match(layoutSource, /@media \(max-width: 680px\)/)
  assert.match(layoutSource, /\.workspace-admin-sidebar \{[\s\S]*?flex-basis: 64px/)
  assert.match(layoutSource, /\.workspace-admin-sidebar :deep\(\.menu-title-text\)[\s\S]*?display: none/)
  assert.match(layoutSource, /\.workspace-admin-content \.content-main \{[\s\S]*?padding: 14px 12px/)
})
