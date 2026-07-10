import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'ResourceTree.vue')
const source = readFileSync(componentPath, 'utf8')

const copyDefaultBranchMatch = source.match(/} else if \(opt === 'copyDefault'\) \{[\s\S]*?\n  \}/)

assert.ok(copyDefaultBranchMatch, '需要保留复制推荐看板到我的看板的处理分支')

const copyDefaultBranch = copyDefaultBranchMatch[0]

assert.match(
  copyDefaultBranch,
  /selectedNodeKey\.value\s*=\s*record\.id/,
  '复制成功后需要选中新副本，避免左侧树停留在推荐看板节点'
)
assert.match(
  copyDefaultBranch,
  /returnMounted\.value\s*=\s*true/,
  '复制成功后需要标记已有路由选中节点，等待树刷新后恢复高亮'
)
assert.match(
  copyDefaultBranch,
  /await\s+getTree\(\)/,
  '复制成功后需要重新拉取看板树，让我的看板立即显示新副本'
)
assert.ok(
  copyDefaultBranch.indexOf('await openCopiedDashboard(record)') <
    copyDefaultBranch.indexOf('await getTree()'),
  '应先打开新副本所属数据源和路由，再刷新树，避免用旧数据源请求我的看板'
)
