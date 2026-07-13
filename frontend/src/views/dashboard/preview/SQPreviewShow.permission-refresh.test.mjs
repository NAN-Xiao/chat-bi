import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')
const autoRefresh = source.match(/function scheduleNextDashboardAutoRefresh\([\s\S]*?\n\}/)?.[0] || ''
const refreshCharts = source.match(/async function refreshDashboardCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasData = \(params: any\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /const permissionDeniedChartIds = new Set<string>\(\)/)
assert.match(source, /function markPermissionDeniedChart\(entry: [^)]*\)/)
assert.match(source, /function isPermissionDeniedChart\(entry: [^)]*\)/)
assert.match(source, /function resetPermissionDeniedCharts\(\)/)
assert.match(autoRefresh, /filter\(\s*\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(refreshCharts, /filter\(\s*\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(cachedResult\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
assert.match(loadCanvas, /resetPermissionDeniedCharts\(\)/)
