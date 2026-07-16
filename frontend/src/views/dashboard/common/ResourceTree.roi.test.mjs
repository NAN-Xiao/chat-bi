import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')

assert.match(source, /type DashboardScope = 'default' \| 'roi' \| 'my'/)
assert.match(source, /canManageCurrentWorkspace/)
assert.match(source, /canAccessRoiDashboard\(userStore\)/)
assert.match(source, /buildCombinedTree\(defaultNodes, roiNodes, myNodes\)/)
assert.ok(source.indexOf('DEFAULT_GROUP_ID') < source.indexOf('ROI_GROUP_ID'))
assert.ok(source.indexOf('ROI_GROUP_ID') < source.indexOf('MY_GROUP_ID'))
assert.match(source, /dashboard_scope: ROI_SCOPE/)
assert.match(source, /raw_id: rawId/)
assert.match(source, /`\$\{ROI_SCOPE\}:\$\{dashboardId\}`/)
assert.match(source, /roiDashboardApi\.list\(\)/)
assert.match(source, /dashboardMode/)
assert.match(source, /ROI_SCOPE/)
assert.doesNotMatch(source, /roiDashboardStore\.dashboards\s*=/)
assert.match(
  source,
  /const clickPlan = createDashboardNodeClickPlan\(getDashboardScope\(data\)\)[\s\S]*if \(clickPlan\.resetOrdinaryDashboardSelection\)/
)

const roiMenu = source.match(
  /if \(isRoiGroupNode\(data\)\) \{([\s\S]*?)\r?\n  \}\r?\n  if \(isDefaultGroupNode/
)
assert.ok(roiMenu, 'ROI 根组需要独立菜单')
assert.match(roiMenu[1], /setRoiDatasource/)
assert.match(roiMenu[1], /newRoiDashboard/)
assert.match(roiMenu[1], /toggleTreeEditing/)
assert.doesNotMatch(roiMenu[1], /newFolder|setDefault|copyDefault/)
