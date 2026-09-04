import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const editorSource = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)
const formSource = readFileSync(
  fileURLToPath(new URL('./DashboardAnalysisModelForm.vue', import.meta.url)),
  'utf8'
)

test('property metric picker shares the property grouping user-property options', () => {
  assert.match(
    editorSource,
    /const propertyMetricFieldOptions = propertyFieldOptions/,
    '属性指标和属性分组必须引用同一个用户公共属性候选列表'
  )
  assert.match(
    formSource,
    /class="property-metric-main-row"[\s\S]*?:options="propertyMetricFieldOptions"/,
    '属性指标下拉必须使用属性分析候选列表'
  )
  assert.match(
    formSource,
    /:options="isPropertyAnalysis \? propertyMetricFieldOptions : builderFieldOptions"/,
    '属性分组下拉必须使用与属性指标一致的候选列表'
  )
})
