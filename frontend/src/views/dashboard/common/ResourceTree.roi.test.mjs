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
  /resolveInitialDashboardRoutePlan\(\s*routeScope,\s*routeResourceId,\s*!!findFirstRoiDashboardNode\(\)\s*\)/,
  'ROI 空路由必须通过纯函数决定初始选择'
)
assert.match(
  source,
  /if \(routePlan\.selectFirstRoiDashboard\) return findFirstRoiDashboardNode\(\)/,
  'ROI 空路由有子看板时必须选择第一个 ROI 叶子'
)
assert.match(
  source,
  /if \(routePlan\.clearSelection\) return undefined/,
  'ROI 空路由无子看板时必须清空选择而非回退普通看板'
)
assert.match(
  source,
  /if \(routePlan\.waitForRoiBranch\) return roiLoaded/,
  'ROI 空路由必须等待 ROI 分支后再初始化'
)
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

assert.match(
  source,
  /if \(opt === 'renameRoiDashboard'\) \{\s*if \(!canManageCurrentWorkspace\.value \|\| !isRoiDashboardNode\(data\) \|\| !isLeafDashboardNode\(data\)\) return/,
  'ROI 重命名命令必须拒绝固定入口'
)
assert.match(
  source,
  /if \(opt === 'deleteRoiDashboard'\) \{\s*if \(!canManageCurrentWorkspace\.value \|\| !isRoiDashboardNode\(data\) \|\| !isLeafDashboardNode\(data\)\) return/,
  'ROI 删除命令必须拒绝固定入口'
)
assert.match(
  source,
  /const operation = async \(opt: string, data: SQTreeNode\) => \{\s*if \(isRoiGroupNode\(data\) && !isAllowedRoiGroupOperation\(opt\)\) return/,
  '固定 ROI 入口必须在通用操作分发前按白名单拦截命令'
)

assert.match(
  source,
  /'is-roi-entry-node': isRoiGroupNode\(data\)/,
  'ROI 固定入口必须具有独立视觉角色 class'
)

const roiEntryIcon = source.match(
  /<el-icon\s+v-else-if="isRoiGroupNode\(data\)"\s+class="tree-node-icon icon-primary">([\s\S]*?)<\/el-icon>/
)
assert.ok(roiEntryIcon, 'ROI 固定入口必须使用普通看板图标分支')
assert.match(roiEntryIcon[1], /name="icon_dashboard_grid_add"/)
assert.match(roiEntryIcon[1], /<icon_dashboard_grid_add class="svg-icon"/)
assert.doesNotMatch(roiEntryIcon[1], /icon_dashboard_group_color/)

assert.match(
  source,
  /v-else-if="data\.node_type !== 'leaf'"[\s\S]*?group-color-icon[\s\S]*?icon_dashboard_group_color/,
  '其它虚拟分组必须继续使用彩色分组图标'
)
const roiEntryIconBranchIndex = source.indexOf('v-else-if="isRoiGroupNode(data)"')
const virtualGroupIconBranchIndex = source.indexOf('v-else-if="data.node_type !== \'leaf\'"')
assert.ok(
  roiEntryIconBranchIndex >= 0 &&
    virtualGroupIconBranchIndex >= 0 &&
    roiEntryIconBranchIndex < virtualGroupIconBranchIndex,
  'ROI 图标分支必须位于通用虚拟分组分支之前，否则会被彩色分组图标抢先匹配'
)
assert.match(
  source,
  /&\.is-roi-entry-node\s*\{\s*padding-left:\s*calc\(var\(--dashboard-tree-indent, 0px\) \+ 18px\);\s*\}/,
  'ROI 固定入口必须复用普通叶子的 18px 左内边距'
)

const roiEntryExpandIconRule = source.match(
  /:deep\(\s*\.ed-tree-node__content:has\(\s*> \.custom-tree-node\.is-roi-entry-node\s*\)\s*> \.ed-tree-node__expand-icon\s*\)\s*\{([\s\S]*?)\n\s*\}/
)
assert.ok(roiEntryExpandIconRule, 'ROI 固定入口必须有专用的展开图标占位规则')
assert.doesNotMatch(roiEntryExpandIconRule[0], /\.is-leaf|\.expanded/, '该规则只能命中 ROI 固定入口')
assert.match(roiEntryExpandIconRule[1], /flex:\s*0 0 2px;/, 'ROI 展开箭头不能增加流式占位')
assert.match(roiEntryExpandIconRule[1], /width:\s*2px;/, 'ROI 展开箭头宽度必须保持 2px')
assert.match(roiEntryExpandIconRule[1], /overflow:\s*visible;/, 'ROI 展开箭头必须保持可见')
assert.doesNotMatch(roiEntryExpandIconRule[1], /visibility:\s*hidden|transform:/, 'ROI 规则不能隐藏或旋转展开箭头')

assert.match(
  combinedTree[0],
  /createDashboardGroup\([\s\S]*?ROI_GROUP_ID[\s\S]*?ROI_SCOPE/,
  '样式统一不得把 ROI 固定入口改成真实叶子记录'
)
