import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /pivotDateParameterType/)
assert.match(source, /pivotDateParameterType:\s*SQL_EDITOR_DATE_PARAMETER_TYPE as DashboardDateParameterType/)
assert.match(source, /scanDashboardDateParameterTokens/)
assert.match(source, /buildDashboardDateSourcePreviewPivot/)
assert.match(source, /pivot:\s*sourcePreviewPivotPayload\(\)/)
assert.match(source, /validateBeforeApply[\s\S]*dashboardDateFilterConfigForWrite/)
assert.match(source, /function shouldUseDashboardDateParameters/)
assert.match(source, /dateParameterType:[\s\S]*SQL_EDITOR_DATE_PARAMETER_TYPE/)
assert.match(source, /dateExpression:[\s\S]*sqlBuilder\.timeExpression[\s\S]*cloneDashboardDateExpression/)
assert.match(source, /sqlBuilder\.dateExpressionPickerEnabled\s*=\s*enabled/)
assert.match(source, /const usesDashboardDateParameters = shouldUseDashboardDateParameters\(\)/)
assert.doesNotMatch(source, /if \(usesDashboardDateParameters && !form\.pivotDateParameterType\)/)
assert.doesNotMatch(source, /if \(form\.chartType !== 'metric' && !sqlBuilder\.timeField\)/)
assert.match(source, /function syncDashboardDateParameterUsage/)
assert.match(source, /form\.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE/)
assert.match(source, /dateExpressionPickerEnabled: usesDashboardDateParameters/)
assert.match(source, /timeExpression: usesDashboardDateParameters && sqlBuilder\.timeExpression/)
assert.match(source, /buildDashboardDateFilterConfig/)
assert.match(
  source.match(/function dashboardDateFilterConfigForWrite\(\)[\s\S]*?\n\}/)?.[0] || '',
  /SQL_EDITOR_DATE_PARAMETER_TYPE/,
  '日期筛选写入必须固定使用 YYYYMMDD 数字参数类型'
)
assert.match(source, /normalizeDashboardChartConfig/)
assert.match(source, /ElMessage\.error\('图表配置已过期，请重新配置'\)/)
assert.match(source, /date_filter:\s*dashboardDateFilterRequestPayload\(\)/)
assert.doesNotMatch(source, /date_parameter_type:\s*form\./)
assert.doesNotMatch(source, /date_expression\s*:/)
