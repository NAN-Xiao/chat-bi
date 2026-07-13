import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')
const autoRefresh = source.match(/function scheduleNextDashboardAutoRefresh\([\s\S]*?\n\}/)?.[0] || ''
const refreshCharts = source.match(/async function refreshDashboardCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasData = \(params: any\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /createPermissionDeniedChartRegistry/)
assert.match(source, /dashboardCacheRefreshDisposition/)
assert.match(source, /shouldRetryDashboardChartFailure/)
assert.match(source, /const permissionDeniedCharts = createPermissionDeniedChartRegistry\(\)/)
assert.match(autoRefresh, /filter\(\s*\(entry\) =>[\s\S]*?!permissionDeniedCharts\.has\(entry\)/)
assert.match(refreshCharts, /filter\(\s*\(entry\) =>[\s\S]*?!permissionDeniedCharts\.has\(entry\)/)
assert.match(
  refreshCharts,
  /dashboardCacheRefreshDisposition\(\s*cachedResult,[\s\S]*?cacheDisposition === 'permission_denied'[\s\S]*?permissionDeniedCharts\.mark\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?permissionDeniedCharts\.mark\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
assert.match(refreshCharts, /shouldRetryDashboardChartFailure\(result,/)
assert.match(loadCanvas, /permissionDeniedCharts\.reset\(\)/)
