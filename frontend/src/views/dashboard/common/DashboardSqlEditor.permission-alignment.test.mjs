import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(source, /canEditSql/, 'SQL 编辑抽屉必须接收 canEditSql 权限')
assert.match(source, /canUseSqlEditor\s*=\s*computed/, 'SQL 编辑抽屉必须抽出统一权限 computed')
assert.match(source, /sqlEditorPermissionMessage/, 'SQL 编辑抽屉必须提供统一的无权限提示')
assert.match(source, /canUseSqlEditor\.value[\s\S]*generateBuilderAiSql/, '图表配置生成 SQL 必须受统一权限控制')
assert.match(source, /canUseSqlEditor\.value[\s\S]*runPreview/, 'SQL 明细预览必须受统一权限控制')
assert.match(source, /canUseSqlEditor\.value[\s\S]*validateBeforeApply/, '应用到画布必须受统一权限控制')
assert.match(
  source,
  /v-if="hasSqlSource && canUseSqlEditor"[\s\S]*图表配置[\s\S]*SQL 明细/,
  '图表配置和 SQL 明细必须共用 canUseSqlEditor 挂载条件'
)
assert.doesNotMatch(
  source,
  /chartConfigPermission|canEditChartConfig|chart_config/,
  '不得新增独立图表配置权限口径'
)
