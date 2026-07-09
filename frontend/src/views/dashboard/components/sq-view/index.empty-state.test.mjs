import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

const pendingStateMatch = source.match(
  /const chartResultPending = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
const emptyStateMatch = source.match(
  /const showEmptyChartState = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
const loadingStateMatch = source.match(
  /const showFullChartLoading = computed\(([\s\S]*?)\r?\n\)\r?\nconst chartLoadingText/
)

assert.ok(pendingStateMatch, '需要显式区分图表结果是否仍在首次加载/等待中')
assert.ok(emptyStateMatch, '需要保留看板图表空数据状态判断')
assert.ok(loadingStateMatch, '需要保留看板图表全屏加载状态判断')

assert.match(
  pendingStateMatch[1],
  /props\.viewInfo\?\.status !== 'success'/,
  '图表结果未成功落定前应视为 pending，避免首次空数组误显示“没有找到数据”'
)
assert.match(
  pendingStateMatch[1],
  /props\.viewInfo\?\.dataState !== 'ready'/,
  '图表结果未 ready 前应视为 pending，避免缓存/接口结果尚未写入时误显示空态'
)
assert.match(
  pendingStateMatch[1],
  /refreshStatePending\.value/,
  '图表刷新排队或等待时应视为 pending，避免 busy 后短暂显示“没有找到数据”'
)
assert.match(
  loadingStateMatch[1],
  /chartResultPending\.value && !hasRenderedChartData\.value/,
  '首次加载且没有可渲染数据时应显示加载态，而不是空数据态'
)
assert.match(
  emptyStateMatch[1],
  /props\.viewInfo\?\.status === 'success'/,
  '只有接口或缓存明确成功返回后，才能显示“没有找到数据”'
)
assert.match(
  emptyStateMatch[1],
  /props\.viewInfo\?\.dataState === 'ready'/,
  '只有数据写入完成后，才能显示“没有找到数据”'
)
assert.match(
  emptyStateMatch[1],
  /!refreshStatePending\.value/,
  '刷新等待或排队期间不能显示“没有找到数据”'
)
