import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./ChartSelection.vue', import.meta.url)),
  'utf8'
)

assert.match(
  source,
  /\.chart-selection-container\s*\{[\s\S]*?:deep\(\.chart-base-container:has\(\.date-expression-toolbar\)\s+\.header-bar\)\s*\{[\s\S]*?min-height:\s*28px[\s\S]*?margin-bottom:\s*6px/,
  '图表选择抽屉中的日期控件应与标题保持紧凑间距'
)
