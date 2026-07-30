import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./ChartBlock.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /const configuredPivot = chartBaseInfo\?\.pivot/)
assert.match(source, /normalizeDashboardChartConfig/)
assert.match(source, /pivot: resolveChartPivot\(chartBaseInfo, recordeInfo\)/)
assert.match(source, /recordeInfo\['dateFilter'\] = dashboardConfig\.dateFilter/)
assert.doesNotMatch(source, /\.date_expression/)
