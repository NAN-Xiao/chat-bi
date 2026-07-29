import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const styleSource = source.slice(source.indexOf('<style'))
const previewSource = readFileSync(
  fileURLToPath(new URL('../../preview/SQPreview.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /v-model="dateFilterState\.draftRange"/)
assert.match(source, /@click="applyDashboardDateRange"/)
assert.match(source, /import DashboardDateExpressionPicker/)
assert.match(source, /const dateExpressionPickerEnabled = computed/)
assert.match(source, /const hasSqlDashboardSource = computed/)
assert.match(
  source,
  /const hasExplicitMcpSource = computed/,
  'MCP 图表即使带有通用 datasource 字段，也不能被误判为 SQL 图表'
)
assert.match(
  source,
  /hasSqlDashboardSource\.value[\s\S]*dateExpressionPickerEnabled/
)
assert.match(
  source,
  /const dateExpressionPickerEnabled = computed\([\s\S]*hasSqlDashboardSource\.value/,
  '新增日期控件只允许 SQL 图表在看板展示层启用，纯 MCP 图表必须保持原样'
)
assert.match(source, /<DashboardDateExpressionPicker/)
assert.match(
  source,
  /normalizeDashboardDateExpression\(props\.viewInfo\?\.pivot\?\.date_expression\)[\s\S]*\|\|\s*\(hasSqlDashboardSource\.value\s*\?\s*defaultDashboardDateExpression\(\)/,
  'SQL 图表缺少历史表达式时应使用共享的默认过去七天'
)
assert.doesNotMatch(source, /preset:\s*['"]past_30_days['"]/, '展示层不得保留过去 30 天默认值')
assert.match(source, /<DashboardDateExpressionPicker[\s\S]*variant="roi"/)
assert.match(source, /dashboard-filter-controls/)
assert.match(source, /dashboard-filter-controls--combined/)
assert.match(source, /dashboard-filter-divider/)
assert.match(source, /const pivotModeLabel = computed\(\(\) =>[\s\S]*pivotGranularityLabel\.value/)
assert.doesNotMatch(source, /pivotTimeRangeActive\.value\s*\?\s*t\('dashboard\.pivot_select_time'\)/)
assert.match(source, /v-if="showDashboardDateExpression"/)
const showDashboardDateExpressionSource =
  source.match(/const showDashboardDateExpression = computed\([\s\S]*?\n\)/)?.[0] || ''
assert.match(
  showDashboardDateExpressionSource,
  /showDashboardDateFilter\.value[\s\S]*dateExpressionPickerEnabled\.value[\s\S]*dashboardDateExpression\.value !== null/,
  '日期表达式控件只能在后端确认日期参数可执行时展示'
)
assert.match(
  source,
  /v-else-if="showDashboardDateFilter\s*&&\s*!dateExpressionPickerEnabled"/
)
assert.match(source, /async function applyDashboardDateExpression/)
assert.match(source, /buildDashboardDateExpressionPivot/)
assert.match(source, /const configuredDashboardDateExpressionKey = computed/)
assert.match(source, /import\s*{\s*ElConfigProvider,\s*ElDatePickerPanel\s*}\s*from\s*'element-plus'/)
assert.match(source, /const datePickerLocale = computed\(/)
assert.match(source, /<ElConfigProvider :locale="datePickerLocale">[\s\S]*<ElDatePickerPanel/)
assert.match(source, /v-model:visible="dateFilterPanelVisible"/)
assert.match(source, /<ElDatePickerPanel[\s\S]*v-model="dateFilterState\.draftRange"/)
assert.match(
  source,
  /class="date-filter-panel-footer"[\s\S]*@click="applyDashboardDateRange"/
)
assert.doesNotMatch(source, /<el-date-picker[\s\S]*class="date-filter-picker"/)
assert.match(source, /dateFilterCapability[\s\S]*status\s*===\s*'available'/)
assert.match(source, /pivotOverride\?:/)
assert.match(source, /buildAppliedDashboardDatePivot/)
assert.match(source, /date_parameter_type:\s*props\.viewInfo\?\.pivot\?\.date_parameter_type/)
assert.match(source, /v-if="pivotRangeEnabled\s*&&\s*!showDashboardDateFilter"/)
assert.doesNotMatch(source, /dateFilterCapability\.value\?\.defaultStart,[\s\S]{0,180}resetDashboardDateFilterState/)
assert.match(source, /const dateFilterState = ref\(/)
assert.match(source, /dateFilterState\.value = nextState/)
assert.match(source, /registerDashboardDateFilterState\(props\.viewInfo, dateFilterState\.value\)/)
assert.match(source, /const viewInfoChanged = currentDateFilterViewInfo !== props\.viewInfo/)
assert.match(source, /if \(!viewInfoChanged && !shouldInitializeDashboardDateFilterState/)
assert.doesNotMatch(source, /Object\.assign\(dateFilterState, nextState\)/)
assert.match(previewSource, /:key="item\.id \|\| index"/)
assert.match(source, /beginDashboardChartRequest\(props\.viewInfo\)/)
assert.match(source, /isDashboardChartRequestCurrent\(props\.viewInfo, requestVersion\)/)

const applyHandler = source.match(/async function applyDashboardDateRange\(\)[\s\S]*?\n}/)?.[0] || ''
assert.match(applyHandler, /dateFilterPanelVisible\.value\s*=\s*false[\s\S]*await refreshData/)
assert.match(applyHandler, /refreshData\([\s\S]*forceRefresh:\s*true/)
assert.match(applyHandler, /blocking:\s*true/)
assert.match(applyHandler, /commitDashboardDateRange/)
assert.match(applyHandler, /failDashboardDateRange/)

const expressionApplyHandler =
  source.match(/async function applyDashboardDateExpression\([\s\S]*?\n}/)?.[0] || ''
assert.match(expressionApplyHandler, /dashboardDateExpressionApplying\.value\s*=\s*true/)
assert.match(expressionApplyHandler, /refreshData\([\s\S]*forceRefresh:\s*true/)
assert.match(expressionApplyHandler, /blocking:\s*true/)
assert.match(expressionApplyHandler, /pivotOverride:\s*buildDashboardDateExpressionPivot/)
assert.match(expressionApplyHandler, /if \(succeeded\)[\s\S]*dashboardDateExpression\.value\s*=\s*next/)
assert.match(expressionApplyHandler, /finally[\s\S]*dashboardDateExpressionApplying\.value\s*=\s*false/)

const expressionSyncWatcher =
  source.match(/watch\(\s*\[\s*\(\) => props\.viewInfo,[\s\S]*?\n\)/)?.[0] || ''
assert.match(expressionSyncWatcher, /configuredDashboardDateExpressionKey/)
assert.doesNotMatch(expressionSyncWatcher, /deep:\s*true/)

const dateChangeHandler = source.match(/function onDashboardDateRangeChange\([\s\S]*?\n}/)?.[0] || ''
assert.doesNotMatch(dateChangeHandler, /refreshData\(/)
assert.doesNotMatch(source, /update_canvas|localStorage|sessionStorage/)
assert.doesNotMatch(source, /4f08e75945c3498486963e70f3c75688|ROI看板/)
assert.match(
  source,
  /\.date-expression-toolbar\s*{[\s\S]*?width:\s*fit-content/
)
assert.match(
  source,
  /:deep\(\.date-expression-trigger\)[\s\S]*?border:\s*0[\s\S]*?background:\s*transparent/
)
assert.match(
  source,
  /:deep\(\.date-expression-trigger\)[\s\S]*?background:\s*transparent[\s\S]*?&:hover[\s\S]*?background:\s*transparent/
)
assert.match(
  source,
  /:deep\(\.date-expression-trigger\)[\s\S]*?padding:\s*0\s*;[\s\S]*?justify-content:\s*flex-start/
)
assert.match(source, /\.dashboard-filter-controls--combined[\s\S]*?display:\s*flex/)
assert.match(source, /\.dashboard-filter-divider[\s\S]*?border-left:/)
assert.match(source, /\.dashboard-filter-controls--combined[\s\S]*?> \.pivot-toolbar[\s\S]*?order:\s*0/)
assert.match(source, /\.dashboard-filter-controls--combined[\s\S]*?> \.date-filter-toolbar[\s\S]*?order:\s*2/)
assert.match(
  source,
  /\.dashboard-filter-controls--combined[\s\S]*?\.pivot-chip\.pivot-link[\s\S]*?color:\s*var\(--workspace-text-primary/
)
assert.match(
  source,
  /\.dashboard-filter-controls--combined[\s\S]*?\.pivot-chip\.pivot-link[\s\S]*?font-weight:\s*400/
)
assert.match(
  styleSource,
  /> \.pivot-toolbar \.pivot-chip\.pivot-link\s*\{[^}]*font-size:\s*12px/
)
assert.match(
  styleSource,
  /> \.date-filter-toolbar\s*:deep\(\.date-expression-trigger\)\s*\{[^}]*font-size:\s*12px/
)
assert.match(
  styleSource,
  /> \.date-filter-toolbar\s*:deep\(\.date-expression-trigger\)\s*\{[^}]*\n\s+height:\s*24px/
)
assert.match(
  styleSource,
  /\.date-filter-trigger\s*\{[^}]*font-family:\s*inherit[^}]*font-size:\s*12px[^}]*line-height:\s*24px/
)
assert.match(
  styleSource,
  /\.pivot-summary\s*\{[^}]*font-family:\s*inherit[^}]*font-size:\s*12px[^}]*line-height:\s*24px/
)
assert.match(
  styleSource,
  /:deep\(\.date-expression-trigger\)\s*\{[^}]*font-family:\s*inherit[^}]*font-size:\s*12px[^}]*line-height:\s*24px/
)
assert.match(
  source,
  /\.dashboard-filter-controls--combined[\s\S]*?\.pivot-link:hover[\s\S]*?background:\s*transparent/
)
assert.match(
  source,
  /\.chart-base-container:has\(\.dashboard-filter-controls--combined\):has\(\.date-expression-toolbar\):has\(\.pivot-toolbar\)[\s\S]*?height:\s*calc\(100% - 82px\)/
)
assert.doesNotMatch(source, /:deep\(\.date-expression-trigger\)[\s\S]*?color:\s*#2f6bff/)
assert.match(
  source,
  /\.chart-base-container:has\(\.date-expression-toolbar\) \.chart-show-area[\s\S]*?height:\s*calc\(100% - 82px\)/
)
assert.match(
  source,
  /\.chart-base-container:has\(\.date-expression-toolbar\):has\(\.pivot-toolbar\) \.chart-show-area[\s\S]*?height:\s*calc\(100% - 116px\)/
)
assert.match(
  source,
  /\.insight-density-mini:has\(\.date-expression-toolbar\) \.chart-show-area[\s\S]*?height:\s*calc\(100% - 70px\)/
)
assert.match(
  source,
  /\.insight-density-basic:has\(\.date-expression-toolbar\):has\(\.pivot-toolbar\) \.chart-show-area[\s\S]*?height:\s*calc\(100% - 94px\)/
)
assert.match(
  source,
  /\.dashboard-date-filter-popper \.el-date-table td\.today\.disabled[\s\S]*\.el-date-table-cell__text[\s\S]*color:\s*var\(--el-text-color-placeholder\)/
)
