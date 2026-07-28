import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardDateExpressionPicker.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /defineModel<DashboardDateExpression \| null>/)
assert.match(source, /cloneDashboardDateExpression/)
assert.match(source, /function openPicker/)
assert.match(source, /function closeWithoutApply/)
assert.match(source, /function applyDraft/)
assert.match(source, /emit\('apply', next\)/)
assert.match(source, /preset-options/)
assert.match(source, /endpoint-mode/)
assert.match(source, /picker-footer/)
assert.match(source, /动态时间/)
assert.match(source, /静态时间/)
assert.doesNotMatch(source, /resourceId|dashboardMode|ROI看板|sq-view/)

console.log('dashboard date expression picker contract passed')
