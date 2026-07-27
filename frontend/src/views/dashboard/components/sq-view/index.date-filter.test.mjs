import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')

assert.match(source, /v-model="dateFilterState\.draftRange"/)
assert.match(source, /@click="applyDashboardDateRange"/)
assert.match(source, /dateFilterCapability[\s\S]*status\s*===\s*'available'/)
assert.match(source, /pivotOverride\?:/)
assert.match(source, /pivotOverride\s*\?\?\s*getPivotPayload\(\)/)

const applyHandler = source.match(/async function applyDashboardDateRange\(\)[\s\S]*?\n}/)?.[0] || ''
assert.match(applyHandler, /refreshData\([\s\S]*forceRefresh:\s*true/)
assert.match(applyHandler, /blocking:\s*true/)
assert.match(applyHandler, /commitDashboardDateRange/)
assert.match(applyHandler, /failDashboardDateRange/)

const dateChangeHandler = source.match(/function onDashboardDateRangeChange\([\s\S]*?\n}/)?.[0] || ''
assert.doesNotMatch(dateChangeHandler, /refreshData\(/)
assert.doesNotMatch(source, /update_canvas|localStorage|sessionStorage/)
