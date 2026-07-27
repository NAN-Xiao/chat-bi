import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /pivotDateParameterType/)
assert.match(source, /date_parameter_type:\s*form\.pivotDateParameterType/)
assert.match(source, /dashboard_start_yyyymmdd/)
assert.match(source, /validateBeforeApply[\s\S]*date_parameter_type/)
