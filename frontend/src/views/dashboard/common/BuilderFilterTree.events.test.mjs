import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'BuilderFilterTree.vue')
const source = readFileSync(componentPath, 'utf8')

const valueInputMatch = source.match(/<el-input[\s\S]*?class="builder-filter-value"[\s\S]*?\/>/)

assert.ok(valueInputMatch, '筛选值输入框需要保留独立的 el-input')
assert.match(
  valueInputMatch[0],
  /@beforeinput\.stop/,
  '筛选值输入框要阻止 beforeinput 冒泡，避免被公式编辑器的 beforeinput.prevent 拦截'
)
assert.match(
  valueInputMatch[0],
  /@paste\.stop/,
  '筛选值输入框要阻止 paste 冒泡，避免被公式编辑器的 paste.prevent 拦截'
)
