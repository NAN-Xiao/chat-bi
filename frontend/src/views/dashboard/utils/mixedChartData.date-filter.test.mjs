import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./mixedChartData.ts', import.meta.url)), 'utf8')

assert.match(source, /buildDashboardDateFilterRequestForView/)
assert.match(source, /canShowDashboardDateFilter\(viewInfo\?\.dateFilterCapability\)/)
assert.match(source, /getOrCreateDashboardDateFilterState\(viewInfo, viewInfo\.dateFilterCapability\)/)
assert.match(source, /date_filter:\s*buildDashboardDateFilterRequestForView\(/)
