import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./ChatChartSelection.vue', import.meta.url)),
  'utf8'
)

assert.match(source, /\['table', 'metric'\]\.includes\(type\)/)
assert.match(source, /normalizeDashboardChartConfig/)
assert.match(source, /return \{[\s\S]*\.\.\.defaultPivot,[\s\S]*\.\.\.configuredPivot/)
assert.doesNotMatch(source, /\.date_expression/)
