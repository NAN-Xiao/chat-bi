import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./ChartBlock.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /const configuredPivot = chartBaseInfo\?\.pivot/)
assert.match(source, /configuredPivot\.enabled === false && !configuredPivot\.date_expression/)
assert.match(source, /recordeInfo\['pivot'\] = resolveChartPivot\(chartBaseInfo, recordeInfo\)/)
