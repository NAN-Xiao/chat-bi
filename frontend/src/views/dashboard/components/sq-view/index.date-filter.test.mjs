import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const previewSource = readFileSync(
  fileURLToPath(new URL('../../preview/SQPreview.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /v-model="dateFilterState\.draftRange"/)
assert.match(source, /@click="applyDashboardDateRange"/)
assert.match(source, /import DashboardDateExpressionPicker/)
assert.match(source, /const dateExpressionPickerEnabled = computed/)
assert.match(
  source,
  /sourceConfig\?\.sql\?\.builder\?\.dateExpressionPickerEnabled\s*===\s*true/
)
assert.match(source, /<DashboardDateExpressionPicker/)
assert.match(source, /v-if="showDashboardDateExpression"/)
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
  /\.date-expression-toolbar\s*{[\s\S]*?width:\s*fit-content[\s\S]*?:deep\(\.date-expression-trigger\)[\s\S]*?width:\s*auto/
)
assert.match(
  source,
  /:deep\(\.date-expression-trigger\)[\s\S]*?border:\s*0[\s\S]*?background:\s*transparent[\s\S]*?color:\s*#2f6bff/
)
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
