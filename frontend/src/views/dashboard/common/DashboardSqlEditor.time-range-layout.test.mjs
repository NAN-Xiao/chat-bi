import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /const SQL_EDITOR_TIME_FIELD = 'dt'/)
assert.match(source, /const SQL_EDITOR_TIME_GRAIN = 'day'/)
assert.match(source, /const SQL_EDITOR_DATE_PARAMETER_TYPE[^\n]*= 'yyyymmdd_number'/)

const panelStart = source.indexOf('<div v-if="hasSqlSource && canUseSqlEditor" class="sql-builder-panel">')
const publicTimeRange = source.indexOf('<el-form-item v-if="hasSqlSource" label="时间范围">')
const executionDatasource = source.indexOf('<el-form-item v-if="hasSqlSource" label="执行数据源">')
assert.ok(panelStart >= 0, '需要保留 SQL 图表配置卡片')
assert.ok(publicTimeRange > panelStart, '时间范围必须位于 SQL 图表配置卡片之后')
assert.ok(executionDatasource > publicTimeRange, '时间范围必须与执行数据源同级并排在其前面')

const publicTimeRangeSource = source.slice(publicTimeRange, executionDatasource)
assert.match(publicTimeRangeSource, /<DashboardDateExpressionPicker/)
assert.doesNotMatch(
  publicTimeRangeSource,
  /BuilderFieldPicker|builderTimeGrainOptions|builderTimeRangeOptions/,
  '公共时间范围不得显示时间字段、粒度或旧范围下拉'
)

const builderPaneStart = source.indexOf('<div v-if="sqlBuilder.activeTab === \'builder\'"')
const sqlPaneStart = source.indexOf('<div v-if="sqlBuilder.activeTab === \'sql\'" class="sql-detail-pane">', builderPaneStart)
assert.ok(builderPaneStart >= 0 && sqlPaneStart > builderPaneStart, '需要识别图表配置页签模板')
const builderPaneSource = source.slice(builderPaneStart, sqlPaneStart)
assert.doesNotMatch(builderPaneSource, /<span>时间范围<\/span>/)

const resetSource = source.match(/function resetSqlBuilderState\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(resetSource, /sqlBuilder\.timeField = SQL_EDITOR_TIME_FIELD/)
assert.match(resetSource, /sqlBuilder\.timeGrain = SQL_EDITOR_TIME_GRAIN/)
assert.match(resetSource, /form\.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE/)

assert.match(source, /function fixedSqlEditorTimeFieldIssue\(\)/)
assert.match(source, /当前执行数据源缺少固定时间字段 dt/)

const missingTimeFieldGuardSource = source.match(
  /function blockMissingFixedTimeField\(\) \{([\s\S]*?)\n\}/
)?.[1] || ''
assert.match(missingTimeFieldGuardSource, /fixedSqlEditorTimeFieldIssue\(\)/)
assert.match(missingTimeFieldGuardSource, /ElMessage\.warning\(issue\)/)
assert.match(missingTimeFieldGuardSource, /return true/)
assert.doesNotMatch(missingTimeFieldGuardSource, /ElMessage\.error|preview\.status/)

const blockingIssuesSource = source.match(
  /function builderBlockingScopeIssues\(\) \{([\s\S]*?)\n\}/
)?.[1] || ''
assert.doesNotMatch(
  blockingIssuesSource,
  /fixedSqlEditorTimeFieldIssue\(\)/,
  '缺少 dt 应使用独立黄色拦截提示，不得混入配置问题列表'
)

const generateSource = source.match(/async function generateBuilderAiSql\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(generateSource, /blockMissingFixedTimeField\(\)/)

const previewSource = source.match(/async function runPreview\([^)]*\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(previewSource, /blockMissingFixedTimeField\(\)/)

const applyValidationSource = source.match(/function validateBeforeApply\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(applyValidationSource, /blockMissingFixedTimeField\(\)/)

const restoreSource = source.match(/function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(restoreSource, /sqlBuilder\.timeField = SQL_EDITOR_TIME_FIELD/)
assert.match(restoreSource, /sqlBuilder\.timeGrain = SQL_EDITOR_TIME_GRAIN/)
assert.doesNotMatch(restoreSource, /value\.timeField|value\.timeGrain/)

const saveSource = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(saveSource, /timeField: SQL_EDITOR_TIME_FIELD/)
assert.match(saveSource, /timeGrain: SQL_EDITOR_TIME_GRAIN/)

const dateFilterWriteSource = source.match(
  /function dashboardDateFilterConfigForWrite\(\) \{([\s\S]*?)\n\}/
)?.[1] || ''
assert.match(dateFilterWriteSource, /SQL_EDITOR_DATE_PARAMETER_TYPE/)

assert.doesNotMatch(source, /v-for="item in pivotDateParameterTypeOptions"/)

console.log('dashboard SQL editor time range layout contract passed')
