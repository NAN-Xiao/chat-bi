import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')

assert.match(source, /type DashboardScope = 'default' \| 'my'/)
assert.doesNotMatch(source, /ROI_GROUP_ID|ROI_SCOPE|createRoiDashboardEntry|isRoiGroupNode/)
assert.doesNotMatch(source, /useRoiDashboardStore|canAccessRoiDashboard|roiNavigationBehavior/)

const combinedTree = source.match(
  /const buildCombinedTree = \([\s\S]*?\r?\n\}\r?\n\r?\nconst findDashboardNode/
)
assert.ok(combinedTree, '必须保留普通组合看板树构造函数')
assert.doesNotMatch(combinedTree[0], /roi|ROI/)
assert.match(combinedTree[0], /normalizeDefaultDashboardNodes/)
assert.match(combinedTree[0], /normalizeMyDashboardNodes/)

console.log('Resource tree no-ROI tests passed')
