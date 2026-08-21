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
assert.match(source, /metricDateExpressionEnabled:\s*false/)
const dateParameterUsageSource = source.match(
  /function shouldUseDashboardDateParameters\(\)[\s\S]*?\n}/
)?.[0] || ''
assert.match(
  dateParameterUsageSource,
  /return Boolean\(sqlBuilder\.timeField\)/,
  '所有包含时间字段的 SQL 图表都应使用日期表达式控件',
)
assert.doesNotMatch(
  dateParameterUsageSource,
  /chartType|metricDateExpressionEnabled/,
  '指标卡日期表达式控件不得再受图表类型或历史开关限制',
)
assert.match(
  source,
  /metricDateExpressionEnabled:\s*sqlBuilder\.metricDateExpressionEnabled\s*===\s*true/,
  '保存 builder 时应保留历史指标卡日期表达式字段',
)
assert.match(
  source,
  /sqlBuilder\.metricDateExpressionEnabled\s*=\s*value\.metricDateExpressionEnabled\s*===\s*true/,
  '恢复 builder 时应保留历史指标卡日期表达式字段',
)
assert.match(
  source,
  /const dateExpressionEnabled = computed\(\s*\(\) => hasSqlSource\.value && sqlBuilder\.dateExpressionPickerEnabled === true && shouldUseDashboardDateParameters\(\)/
)
assert.match(source, /timeExpression/)
assert.match(source, /date_expression/)
assert.match(source, /const dateExpressionEnabled = computed/)
assert.match(source, /dateExpressionPickerEnabled:\s*true/)
assert.match(source, /sqlBuilder\.dateExpressionPickerEnabled\s*=\s*true/)
assert.doesNotMatch(
  source,
  /DEFAULT_DASHBOARD_DATE_PARAMETER_TYPE|pivotDateParameterType:\s*DEFAULT_DASHBOARD_DATE_PARAMETER_TYPE/,
  '日期参数类型缺失时不得静默猜测默认类型'
)
assert.doesNotMatch(
  source,
  /if \(usesDashboardDateParameters && !form\.pivotDateParameterType\)/,
  '固定日期参数类型后不得继续要求用户选择日期格式'
)
assert.match(source, /defaultDashboardDateExpression/, 'SQL 日期控件应使用共享默认值工厂')
assert.doesNotMatch(source, /preset:\s*['"]past_30_days['"]/, 'SQL 日期控件不得保留过去 30 天默认值')
const initEditorSource = source.match(/function initEditor\(\)[\s\S]*?\n}/)?.[0] || ''
assert.match(
  initEditorSource,
  /restoreSqlBuilderState\([^)]*\)[\s\S]*?normalizeDashboardDateExpression\(normalizedConfig\.dateFilter\?\.expression\)[\s\S]*?if \(pivotDateExpression\) \{[\s\S]*?cloneDashboardDateExpression\(pivotDateExpression\)/,
  '有效的已保存日期表达式应优先于构建器表达式'
)
assert.doesNotMatch(
  source,
  /else if \(!pivotDateExpression\) \{\s*dateExpressionConfigError\.value = '日期表达式执行配置缺失'/,
  '旧图表缺少已保存日期表达式时应使用默认值，而非阻止执行'
)
assert.match(
  source,
  /else if\s*\(\s*pivotDateExpression\s*&&\s*JSON\.stringify\(sqlBuilder\.timeExpression\) !== JSON\.stringify\(pivotDateExpression\)\s*\)/,
  '已保存日期表达式存在但与当前值不一致时仍应阻止执行'
)
assert.match(source, /function applyDateExpression/)
assert.match(source, /<el-form-item v-if="hasSqlSource" label="时间范围">/)
assert.match(source, /<DashboardDateExpressionPicker/)
assert.doesNotMatch(
  source,
  /class="builder-date-expression-options"|class="builder-date-expression-hint"/,
  'SQL 日期控件下方不再显示日期参数类型和提示'
)
assert.doesNotMatch(
  source,
  /<el-checkbox[\s\S]*dateExpressionPickerEnabled/,
  '日期控件默认启用后不再显示手动勾选项'
)
assert.match(
  source,
  /\.sql-editor-time-range-picker\s*:deep\(\.date-expression-trigger\)[\s\S]*?width:\s*100%/,
  'SQL 抽屉的公共日期入口应填满表单项宽度'
)
assert.match(
  source,
  /if\s*\(\s*!isExternalSnapshotChart\(viewInfo\)[\s\S]*?viewInfo\?\.datasource/,
  'MCP 快照不能仅凭 datasource 字段被推断为 SQL 数据源'
)
assert.match(
  source,
  /<DashboardDateExpressionPicker[\s\S]*?variant="roi"/,
  'SQL 编辑抽屉的日期表达式选择器应使用统一的 ROI 样式'
)
assert.match(
  source,
  /function dashboardDateFilterConfigForWrite\(\)[\s\S]*buildDashboardDateFilterConfig/
)
const dateFilterWriteSource = source.match(
  /function dashboardDateFilterConfigForWrite\(\)[\s\S]*?\n}/
)?.[0] || ''
assert.match(
  dateFilterWriteSource,
  /sqlBuilder\.timeExpression\s*\?\s*cloneDashboardDateExpression\(sqlBuilder\.timeExpression\)/,
  '独立 dateFilter 必须直接使用已恢复的日期表达式，不能依赖 SQL Builder timeField'
)
assert.doesNotMatch(
  dateFilterWriteSource,
  /dateExpressionEnabled/,
  'dateFilter 写入和预览签名不得被 SQL Builder timeField 间接禁用'
)
const modelValueWatchSource = source.match(
  /watch\(\s*\(\) => props\.modelValue,[\s\S]*?\n\)/
)?.[0] || ''
assert.match(
  modelValueWatchSource,
  /try\s*\{[\s\S]*initEditor\(\)[\s\S]*catch\s*\(error\)/,
  'SQL 编辑器初始化异常必须被捕获，不能中断 Vue 更新'
)
assert.match(
  modelValueWatchSource,
  /DASHBOARD_DATE_FILTER_MIGRATION_REQUIRED[\s\S]*ElMessage\.error[\s\S]*visible\.value\s*=\s*false/,
  '未迁移日期配置必须显示明确提示并关闭半初始化抽屉'
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
