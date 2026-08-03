import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { formatInsightDateRange } from './chartInsight.ts'

const headerSource = readFileSync(
  fileURLToPath(new URL('./ChartInsightHeader.vue', import.meta.url)),
  'utf8'
)

assert.equal(
  formatInsightDateRange(['2026-07-04', '2026-08-02']),
  '2026-07-04 - 2026-08-02',
  '看板摘要应展示后端解析的真实筛选范围，而不是周聚合键的最小最大值'
)
assert.equal(formatInsightDateRange(['2026-07-04', '2026-07-04']), '2026-07-04')
assert.equal(formatInsightDateRange(['2026-08-02', '2026-07-04']), '')
assert.equal(formatInsightDateRange(['2026-07-04', '']), '')
assert.equal(formatInsightDateRange(null), '')
assert.match(headerSource, /dateRange\?:\s*\[string, string\]\s*\|\s*null/)
assert.match(
  headerSource,
  /formatInsightDateRange\(props\.dateRange\)[\s\S]*\|\|\s*dataDateRangeLabel\.value/,
  '后端解析范围应优先于从聚合结果行推断的日期范围'
)
