import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')
const branch = source.match(
  /} else if \(opt === 'setDefault' \|\| opt === 'removeDefault'\) \{[\s\S]*?\n  } else if \(opt === 'copyDefault'\)/
)

assert.ok(branch, '需要保留加入或移出推荐看板的处理分支')
assert.match(branch[0], /dashboardApi\s*\.default_set\(/, '加入推荐看板必须调用后端复制接口')
assert.match(branch[0], /getTree\(\)/, '复制成功后必须刷新看板树')
assert.doesNotMatch(
  branch[0],
  /selectedNodeKey\.value\s*=/,
  '加入推荐看板后必须保持源看板选中，不能切换到推荐副本'
)
