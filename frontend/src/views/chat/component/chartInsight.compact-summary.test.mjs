import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(path.join(here, 'ChartInsightHeader.vue'), 'utf8')

assert.match(
  source,
  /&\.mini\s*\{[\s\S]*?\.insight-stat-meta\s*\{[\s\S]*?display:\s*(?:block|flex)/,
  'mini 密度在空间允许时必须显示数据摘要'
)
assert.match(
  source,
  /&\.basic\s*\{[\s\S]*?\.insight-stat-meta\s*\{[\s\S]*?display:\s*(?:block|flex)/,
  'basic 密度在空间允许时必须显示数据摘要'
)
