import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'index.vue'), 'utf8')
const refreshCharts = source.match(/async function refreshEditorCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /createPermissionDeniedChartRegistry/)
assert.match(source, /dashboardCacheRefreshDisposition/)
assert.match(source, /shouldRetryDashboardChartFailure/)
assert.match(source, /const permissionDeniedCharts = createPermissionDeniedChartRegistry\(\)/)
assert.match(refreshCharts, /filter\(\s*\(entry\) =>[\s\S]*?!permissionDeniedCharts\.has\(entry\)/)
assert.match(
  refreshCharts,
  /dashboardCacheRefreshDisposition\(\s*cachedResult,[\s\S]*?cacheDisposition === 'permission_denied'[\s\S]*?permissionDeniedCharts\.mark\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?permissionDeniedCharts\.mark\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
const permissionBranch =
  refreshCharts.match(/if \(isPermissionDeniedResult\(result\)\) \{([\s\S]*?)\} else \{/)?.[1] || ''
assert.doesNotMatch(permissionBranch, /transientPendingCount \+= 1/)
assert.match(refreshCharts, /shouldRetryDashboardChartFailure\(result,/)
assert.match(loadCanvas, /permissionDeniedCharts\.reset\(\)/)
