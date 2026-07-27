import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./SQPreviewShow.vue', import.meta.url)), 'utf8')
const editorSource = readFileSync(fileURLToPath(new URL('../editor/index.vue', import.meta.url)), 'utf8')

assert.match(source, /dateFilterCapability/)
assert.match(source, /function chartSqlPayload[\s\S]*buildAppliedDashboardDatePivot/)
assert.match(source, /CHART_DATABASE_REFRESH_CONCURRENCY\s*=\s*2/)
assert.match(source, /DASHBOARD_MODE_DEFAULT/)
assert.match(source, /getOrCreateDashboardDateFilterState\(viewInfo, viewInfo\.dateFilterCapability\)/)
assert.match(source, /buildAppliedDashboardDatePivot/)
assert.match(source, /beginDashboardChartRequest\(entry\.viewInfo,\s*'background'\)/)
assert.match(source, /isDashboardChartRequestCurrent\(viewInfo, requestVersion\)/)
assert.match(editorSource, /beginDashboardChartRequest\(entry\.viewInfo,\s*'background'\)/)
assert.match(editorSource, /isDashboardChartRequestCurrent\(viewInfo, requestVersion\)/)
assert.doesNotMatch(source, /localStorage|sessionStorage|update_canvas/)
