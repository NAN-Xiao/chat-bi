import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'index.vue'), 'utf8')
const refreshCharts = source.match(/async function refreshEditorCharts\([\s\S]*?\n\}/)?.[0] || ''
const loadCanvas = source.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(source, /const permissionDeniedChartIds = new Set<string>\(\)/)
assert.match(refreshCharts, /filter\(\s*\(entry\) =>[\s\S]*?!isPermissionDeniedChart\(entry\)/)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(cachedResult\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, cachedResult\)/
)
assert.match(
  refreshCharts,
  /isPermissionDeniedResult\(result\)[\s\S]*?markPermissionDeniedChart\(entry\)[\s\S]*?applyChartResult\(viewInfo, result\)/
)
const permissionBranch =
  refreshCharts.match(/if \(isPermissionDeniedResult\(result\)\) \{([\s\S]*?)\} else \{/)?.[1] || ''
assert.doesNotMatch(permissionBranch, /transientPendingCount \+= 1/)
assert.match(loadCanvas, /resetPermissionDeniedCharts\(\)/)
