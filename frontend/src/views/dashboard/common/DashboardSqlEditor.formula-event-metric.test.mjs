import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(
  source,
  /function defaultMetricFieldForEvent\(/,
  '公式事件指标需要通过专门函数选择计算字段，不能直接回退到事件内部值'
)

const defaultMetricFieldForEventMatch = source.match(
  /function defaultMetricFieldForEvent\(field: string\) \{([\s\S]*?)\r?\n\}/
)

assert.ok(defaultMetricFieldForEventMatch, '需要保留事件计算字段默认值函数')
assert.doesNotMatch(
  defaultMetricFieldForEventMatch[1],
  /\.find\(isNumberMetricFieldOption\)\?\.value/,
  '切换到去重数或求和时不能自动选择第一个数值参数，避免把产品 ID 当成计算字段'
)
assert.match(
  defaultMetricFieldForEventMatch[1],
  /return ''/,
  '事件计算字段默认应为空，由用户明确选择去重或求和字段'
)

assert.match(
  source,
  /metric\.metric === metric\.field/,
  '公式事件指标从总次数切换到求和等聚合时，应识别并替换掉旧的事件内部值'
)

assert.match(
  source,
  /:options="metricMeasureFieldOptions\(token\.metric as any\)"/,
  '公式内事件指标的计算字段候选应优先使用当前事件参数，避免显示 event:PayBuyRet'
)

assert.doesNotMatch(
  source.match(/function syncFormulaAtomicMetric[\s\S]*?\n\}/)?.[0] || '',
  /\|\| metric\.field/,
  '非总次数聚合不能把事件内部值作为计算字段兜底'
)
