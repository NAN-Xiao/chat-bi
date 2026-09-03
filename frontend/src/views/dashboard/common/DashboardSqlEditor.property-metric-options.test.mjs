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

test('property metric picker shares the retention analysis subject options', () => {
  assert.match(
    editorSource,
    /const propertyMetricFieldOptions = retentionEntityFieldOptions/,
    '属性指标和留存分析主体必须引用同一个候选列表'
  )
  assert.match(
    formSource,
    /class="property-metric-main-row"[\s\S]*?:options="propertyMetricFieldOptions"/,
    '属性指标下拉必须使用与留存分析主体一致的候选列表'
  )
  assert.match(
    formSource,
    /v-model="sqlBuilder\.retention\.entityField"[\s\S]*?:options="retentionEntityFieldOptions"/,
    '留存分析主体下拉必须继续使用分析主体候选列表'
  )
})
