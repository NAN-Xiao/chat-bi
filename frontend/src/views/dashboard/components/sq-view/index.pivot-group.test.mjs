import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'index.vue')
const source = readFileSync(componentPath, 'utf8')

const syncPivotStateMatch = source.match(
  /function syncPivotStateFromView\([\s\S]*?\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction schedulePivotRefresh/
)
const renderableChartDataMatch = source.match(
  /const renderableChartData = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)

assert.ok(syncPivotStateMatch, '需要保留仪表盘透视状态初始化逻辑')
assert.match(
  syncPivotStateMatch[1],
  /configuredPivotGroupValues/,
  '已保存分组可见项时，即使旧配置 group_enabled=false，仪表盘也应按分组初始化'
)
assert.ok(renderableChartDataMatch, '需要保留仪表盘图表数据源计算逻辑')
assert.match(
  renderableChartDataMatch[1],
  /source_data/,
  '旧物化结果缺少分组字段时，应使用保存的 source_data 兜底渲染分组视图'
)
