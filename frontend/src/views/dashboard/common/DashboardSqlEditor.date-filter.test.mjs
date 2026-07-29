import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /pivotDateParameterType/)
assert.match(source, /pivotDateParameterType:\s*'' as DashboardDateParameterType/)
assert.match(source, /scanDashboardDateParameterTokens/)
assert.match(source, /buildDashboardDateSourcePreviewPivot/)
assert.match(source, /pivot:\s*sourcePreviewPivotPayload\(\)/)
assert.match(source, /validateBeforeApply[\s\S]*dashboardDateFilterConfigForWrite/)
assert.match(source, /function shouldUseDashboardDateParameters/)
assert.match(source, /dateParameterType:[\s\S]*form\.pivotDateParameterType/)
assert.match(source, /dateExpression:[\s\S]*sqlBuilder\.timeExpression[\s\S]*cloneDashboardDateExpression/)
assert.match(source, /生成 SQL 前请先选择日期参数类型/)
assert.match(source, /sqlBuilder\.dateExpressionPickerEnabled\s*=\s*enabled/)
assert.match(source, /const usesDashboardDateParameters = shouldUseDashboardDateParameters\(\)/)
assert.match(source, /if \(usesDashboardDateParameters && !form\.pivotDateParameterType\)/)
assert.doesNotMatch(source, /if \(form\.chartType !== 'metric' && !sqlBuilder\.timeField\)/)
assert.match(source, /function syncDashboardDateParameterUsage/)
assert.match(source, /form\.pivotDateParameterType = ''/)
assert.match(source, /dateExpressionPickerEnabled: usesDashboardDateParameters/)
assert.match(source, /timeExpression: usesDashboardDateParameters && sqlBuilder\.timeExpression/)
assert.match(source, /buildDashboardDateFilterConfig/)
assert.match(source, /normalizeDashboardChartConfig/)
assert.match(source, /date_filter:\s*dashboardDateFilterRequestPayload\(\)/)
assert.doesNotMatch(source, /date_parameter_type:\s*form\./)
assert.doesNotMatch(source, /date_expression\s*:/)
