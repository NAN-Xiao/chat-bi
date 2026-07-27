import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ChartFullscreenDialog.vue'), 'utf8')

assert.match(
  source,
  /\.is-metric-layout,\s*\.is-table-layout\s*\{[\s\S]*?\.fullscreen-chart-stage\s*\{[\s\S]*?grid-template-rows:\s*minmax\(0, 1fr\);/,
  '没有摘要区的表格和指标卡必须让图表舞台使用单行全高轨道，不能保留空的摘要行'
)

assert.match(
  source,
  /\.has-side-summary[\s\S]*?\.fullscreen-chart-stage\s*\{[\s\S]*?grid-template-rows:\s*minmax\(0, 1fr\);/,
  '摘要位于侧栏时，图表舞台必须使用单行全高轨道，不能让图表落入收缩的 auto 行'
)
