import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)), 'utf8')
const supportsPivotConfig = source.match(
  /const supportsPivotConfig = computed\(\(\) =>([\s\S]*?)\r?\n\)/
)

assert.ok(supportsPivotConfig, '需要保留透视支持范围判断')
assert.match(
  supportsPivotConfig[1],
  /!isDistributionAnalysis\.value/,
  '分布 SQL 已按主体和区间完成聚合，不能再启用会改变业务口径的通用透视'
)
assert.match(
  source,
  /if \(sqlBuilder\.analysisModel === 'distribution' \|\| result\.analysis_model === 'distribution'\) \{[\s\S]*?form\.pivotEnabled = false[\s\S]*?form\.pivotTimeField = ''[\s\S]*?form\.pivotGroupField = ''[\s\S]*?\r?\n  \}/,
  '切换为分布分析后必须清除此前图表遗留的透视配置'
)
