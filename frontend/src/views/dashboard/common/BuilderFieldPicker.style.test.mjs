import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'BuilderFieldPicker.vue')
const source = readFileSync(componentPath, 'utf8')

const arrowStyleMatch = source.match(/\.builder-field-picker-arrow\s*\{([\s\S]*?)\n\}/)

assert.ok(arrowStyleMatch, '字段选择器箭头需要有独立样式')
assert.match(
  arrowStyleMatch[1],
  /display:\s*inline-flex/,
  '字段选择器箭头应使用 flex 布局，避免字符基线导致不居中'
)
assert.match(
  arrowStyleMatch[1],
  /align-items:\s*center/,
  '字段选择器箭头需要垂直居中'
)
assert.match(
  arrowStyleMatch[1],
  /justify-content:\s*center/,
  '字段选择器箭头需要水平居中'
)
