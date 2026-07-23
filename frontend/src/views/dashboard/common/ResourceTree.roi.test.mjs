import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')

assert.match(source, /type DashboardScope = 'default' \| 'roi' \| 'my'/)
assert.match(source, /const createRoiDashboardEntry = \(\): SQTreeNode =>/)
const roiEntry = source.match(
  /const createRoiDashboardEntry = \(\): SQTreeNode =>[\s\S]*?\n\s*\}\) as SQTreeNode/
)
assert.ok(roiEntry, '必须构造固定 ROI 虚拟叶子入口')
assert.match(roiEntry[0], /id: ROI_GROUP_ID/)
assert.match(roiEntry[0], /pid: DEFAULT_GROUP_ID/)
assert.match(roiEntry[0], /name: t\('dashboard\.roi_dashboard'\)/)
assert.match(roiEntry[0], /leaf: true/)
assert.match(roiEntry[0], /node_type: 'leaf'/)
assert.match(roiEntry[0], /virtual: true/)
assert.match(roiEntry[0], /dashboard_scope: ROI_SCOPE/)
assert.match(roiEntry[0], /children: \[\]/)

const combinedTree = source.match(
  /const buildCombinedTree = \([\s\S]*?\r?\n\}\r?\n\r?\nconst findDashboardNode/
)
assert.ok(combinedTree, '必须保留组合看板树构造函数')
assert.match(combinedTree[0], /defaultChildren\.push\(createRoiDashboardEntry\(\)\)/)
assert.doesNotMatch(combinedTree[0], /normalizeRoiDashboardNodes|roiNodes/)

assert.doesNotMatch(source, /roiDashboardApi\.list|loadDashboards|requestDashboardCreation/)
assert.doesNotMatch(
  source,
  /newRoiDashboard|renameRoiDashboard|deleteRoiDashboard|ROI_DASHBOARD_TREE_REFRESH_EVENT/
)
assert.match(source, /const hasNodeMenu = \(data: SQTreeNode\) => \{\s*if \(isRoiGroupNode\(data\)\) return false/)

const nodeClick = source.match(/const nodeClick = \(data: SQTreeNode, node: any\) => \{([\s\S]*?)\n\}/)
assert.ok(nodeClick, '节点点击入口必须存在')
assert.ok(
  nodeClick[1].indexOf('isRoiGroupNode(data)') < nodeClick[1].indexOf('isVirtualNode(data)'),
  '固定 ROI 入口必须在通用虚拟节点返回前处理'
)
assert.match(nodeClick[1], /activateRoiEntry\(data\)/)

assert.match(source, /'is-roi-entry-node': isRoiGroupNode\(data\)/)
assert.match(
  source,
  /:deep\([\s\S]*\.is-roi-entry-node[\s\S]*\.ed-tree-node__expand-icon[\s\S]*visibility:\s*hidden;/,
  '固定 ROI 入口必须隐藏展开箭头'
)

console.log('ROI resource tree tests passed')
