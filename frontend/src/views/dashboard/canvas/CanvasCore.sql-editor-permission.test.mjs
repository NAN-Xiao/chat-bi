import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const currentDir = dirname(fileURLToPath(import.meta.url))
const canvasCore = readFileSync(join(currentDir, 'CanvasCore.vue'), 'utf8')
const dashboardEditor = readFileSync(join(currentDir, '../editor/DashboardEditor.vue'), 'utf8')
const editorIndex = readFileSync(join(currentDir, '../editor/index.vue'), 'utf8')

assert.match(
  canvasCore,
  /const editSql = \(id: string\) => \{[\s\S]*dashboardCanEdit\.value[\s\S]*props\.canEditSql[\s\S]*sqlEditorPermissionMessage/,
  'CanvasCore 打开 SQL 编辑器前必须同时检查 dashboardCanEdit 和 canEditSql'
)
assert.match(
  canvasCore,
  /<DashboardSqlEditor[\s\S]*:can-edit-sql="canEditSql"/,
  'CanvasCore 必须把 canEditSql 显式传给 DashboardSqlEditor'
)
assert.doesNotMatch(
  dashboardEditor,
  /canEditSql:\s*\{[\s\S]*default:\s*true/,
  'DashboardEditor 的 canEditSql 默认值不能保守性不足'
)
assert.match(
  editorIndex,
  /<DashboardEditor[\s\S]*:dashboard-info="dashboardInfo"[\s\S]*:can-edit-sql="dashboardInfo\.canEdit !== false"/,
  '看板编辑页必须显式把现有编辑能力传给 SQL 编辑权限'
)
