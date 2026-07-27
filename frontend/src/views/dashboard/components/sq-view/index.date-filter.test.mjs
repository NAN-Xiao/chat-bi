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
assert.match(applyHandler, /refreshData\([\s\S]*forceRefresh:\s*true/)
assert.match(applyHandler, /blocking:\s*true/)
assert.match(applyHandler, /commitDashboardDateRange/)
assert.match(applyHandler, /failDashboardDateRange/)

const dateChangeHandler = source.match(/function onDashboardDateRangeChange\([\s\S]*?\n}/)?.[0] || ''
assert.doesNotMatch(dateChangeHandler, /refreshData\(/)
assert.doesNotMatch(source, /update_canvas|localStorage|sessionStorage/)
