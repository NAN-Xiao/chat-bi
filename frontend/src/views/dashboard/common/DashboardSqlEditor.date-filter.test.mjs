import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /pivotDateParameterType/)
assert.match(source, /date_parameter_type:\s*form\.pivotDateParameterType/)
assert.match(source, /scanDashboardDateParameterTokens/)
assert.match(source, /buildDashboardDateSourcePreviewPivot/)
assert.match(source, /pivot:\s*sourcePreviewPivotPayload\(\)/)
assert.match(source, /dashboardDateParameterTokens/)
assert.match(source, /validateBeforeApply[\s\S]*date_parameter_type/)
