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

const nodeClick = source.match(/const nodeClick = \(data: SQTreeNode, node: any\) => \{([\s\S]*?)\n\}/)
assert.ok(nodeClick, '节点点击入口必须存在')
assert.ok(
  nodeClick[1].indexOf('createDashboardNodeClickPlan') < nodeClick[1].indexOf('isVirtualNode(data)'),
  'default/my 虚拟根必须先应用普通 store 清理计划，再处理 virtual return'
)

const resetTreeState = source.match(/const resetTreeState = \(\) => \{([\s\S]*?)\n\}/)
assert.ok(resetTreeState, '树重置入口必须存在')
assert.match(resetTreeState[1], /shouldResetOrdinaryDashboardStore\(currentRouteDashboardScope\(\)\)/)
assert.match(resetTreeState[1], /roiDashboardStore\.reset\(\)/)

const workspaceSwitchHandler = source.match(
  /name: WORKSPACE_CONTEXT_CHANGE_EVENT,[\s\S]*?callback: \(event\?: any\) => \{([\s\S]*?)\r?\n  \},\r?\n\}\)/
)
assert.ok(workspaceSwitchHandler, '必须监听工作空间切换事件')
assert.match(workspaceSwitchHandler[1], /resetTreeState\(\)/)
assert.ok(
  workspaceSwitchHandler[1].indexOf('resetTreeState()') <
    workspaceSwitchHandler[1].indexOf("if (event?.phase === 'changing')"),
  '切换开始时必须先清空旧 ROI 树状态'
)
assert.match(source, /const requestTenantId = userStore\.getTenantId \|\| 'default'/)
assert.match(source, /\(userStore\.getTenantId \|\| 'default'\) === requestTenantId/)

const roiMenu = source.match(
  /if \(isRoiGroupNode\(data\)\) \{([\s\S]*?)\r?\n  \}\r?\n  if \(isDefaultGroupNode/
)
assert.ok(roiMenu, 'ROI 根组需要独立菜单')
assert.doesNotMatch(roiMenu[1], /setRoiDatasource|openDatasourceSettings/)
assert.match(roiMenu[1], /newRoiDashboard/)
assert.match(roiMenu[1], /toggleTreeEditing/)
assert.doesNotMatch(roiMenu[1], /newFolder|setDefault|copyDefault/)
