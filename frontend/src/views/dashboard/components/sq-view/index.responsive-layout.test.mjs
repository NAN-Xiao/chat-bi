import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const style = source.slice(source.indexOf('<style scoped'))

assert.match(source, /ref="chartShowAreaRef"[^>]*class="chart-show-area"/)
assert.match(source, /surface="dashboard"/)
assert.match(source, /:has-outer-title="true"/)
assert.match(
  style,
  /\.chart-base-container\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column/s
)
assert.match(style, /\.header-bar\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(style, /\.dashboard-filter-controls\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(
  style,
  /\.chart-show-area\s*\{[^}]*flex:\s*1\s+1\s+auto[^}]*height:\s*auto/s
)
assert.doesNotMatch(style, /\.chart-show-area\s*\{[^}]*height:\s*calc\(/s)
assert.doesNotMatch(
  style,
  /:has\([^)]*(?:pivot-toolbar|date-expression-toolbar)[^)]*\)[^{]*\.chart-show-area\s*\{[^}]*height:/s
)
assert.doesNotMatch(style, /\.chart-loading-info\s*\{[^}]*min-height:\s*140px/s)
console.log('SQView responsive layout tests passed')
