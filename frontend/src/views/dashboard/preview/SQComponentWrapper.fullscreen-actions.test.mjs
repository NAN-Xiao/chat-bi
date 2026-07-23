import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8')

const actionBarStyleMatch = source.match(/\.preview-chart-actions \{([\s\S]*?)\r?\n\}/)

assert.ok(actionBarStyleMatch, '需要保留看板图表操作栏样式')
assert.match(
  actionBarStyleMatch[1],
  /pointer-events:\s*auto;/,
  '图表操作栏在显示动画前也必须可命中，避免首次点击穿透到图表内容层'
)
assert.doesNotMatch(
  actionBarStyleMatch[1],
  /pointer-events:\s*none;/,
  '图表操作栏不能在默认状态禁用指针事件，否则全屏等按钮可能无法收到点击'
)
