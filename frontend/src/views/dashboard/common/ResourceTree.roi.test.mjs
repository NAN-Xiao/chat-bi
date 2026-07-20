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
const combinedTree = source.match(
  /const buildCombinedTree = \([\s\S]*?\r?\n\}\r?\n\r?\nconst findDashboardNode/
)
assert.ok(combinedTree, '必须保留组合看板树构造函数')
assert.match(
  combinedTree[0],
  /const defaultChildren = normalizeDefaultDashboardNodes\(defaultNodes\)/,
  '普通推荐看板应先形成独立子节点列表'
)
assert.match(
  combinedTree[0],
  /defaultChildren\.push\([\s\S]*?ROI_GROUP_ID[\s\S]*?normalizeRoiDashboardNodes\(roiNodes\)/,
  'ROI 虚拟入口必须追加到推荐看板内部'
)
assert.doesNotMatch(
  combinedTree[0],
  /\.\.\.\(canManageCurrentWorkspace\.value/,
  'ROI 入口不能继续作为顶层分组'
)

assert.match(
  source,
  /const findDashboardGroupNode = \([\s\S]*?findDashboardGroupNode\(node\.children \|\| \[\], groupId\)/,
  '嵌套后的 ROI 虚拟入口必须支持递归定位'
)
assert.match(
  source,
  /collectTreeOrderItems\([\s\S]*?DEFAULT_SCOPE,[\s\S]*?\(node\) => getDashboardScope\(node\) === DEFAULT_SCOPE/,
  '普通推荐排序必须排除 ROI 子树'
)
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
assert.match(
  source,
  /const resolveRoiGroupTarget = \(data: SQTreeNode\)[\s\S]*?findFirstLeafDashboardNode\(data\.children \|\| \[\]\)/,
  '固定 ROI 入口必须解析当前或首个下属看板'
)
assert.match(
  source,
  /const syncEmptyRoiRoute = \(\)[\s\S]*?dashboardMode: ROI_SCOPE/,
  '无下属看板时必须进入明确的 ROI 空路由'
)

const nodeClick = source.match(/const nodeClick = \(data: SQTreeNode, node: any\) => \{([\s\S]*?)\n\}/)
assert.ok(nodeClick, '节点点击入口必须存在')
assert.ok(
  nodeClick[1].indexOf('createDashboardNodeClickPlan') < nodeClick[1].indexOf('isVirtualNode(data)'),
  'default/my 虚拟根必须先应用普通 store 清理计划，再处理 virtual return'
)
assert.ok(
  nodeClick[1].indexOf('isRoiGroupNode(data)') < nodeClick[1].indexOf('isVirtualNode(data)'),
  '固定 ROI 入口必须在通用虚拟节点返回前处理'
)
assert.match(nodeClick[1], /activateRoiGroupNode\(data\)/)

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
assert.doesNotMatch(
  roiMenu[1],
  /deleteRoiDashboard|renameRoiDashboard|copyDefault|removeDefault/,
  '固定 ROI 入口不得出现删除、重命名或普通推荐看板命令'
)
assert.doesNotMatch(roiMenu[1], /newFolder|setDefault|copyDefault/)
