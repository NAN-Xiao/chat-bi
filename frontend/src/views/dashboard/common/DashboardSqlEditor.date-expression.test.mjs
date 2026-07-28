import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)
const cardSource = readFileSync(
  fileURLToPath(new URL('../components/sq-view/index.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /import DashboardDateExpressionPicker/)
assert.match(source, /dateExpressionPickerEnabled/)
assert.match(source, /timeExpression/)
assert.match(source, /date_expression/)
assert.match(source, /const dateExpressionEnabled = computed/)
assert.match(source, /function applyDateExpression/)
assert.match(source, /v-if="dateExpressionEnabled"/)
assert.match(source, /<DashboardDateExpressionPicker/)
assert.match(
  source,
  /function previewPivotPayload\(\)[\s\S]*!dateExpressionEnabled\.value[\s\S]*return buildPivotConfig/
)
assert.doesNotMatch(
  source,
  /4f08e75945c3498486963e70f3c75688|ROI看板|dashboardMode\s*===\s*['"]roi/
)
assert.match(cardSource, /import DashboardDateExpressionPicker/)
assert.match(cardSource, /dateExpressionPickerEnabled/)
assert.match(cardSource, /<DashboardDateExpressionPicker/)
assert.doesNotMatch(cardSource, /4f08e75945c3498486963e70f3c75688|ROI看板/)

console.log('dashboard SQL editor date expression integration contract passed')
