import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'canvasUtils.ts'), 'utf8')

assert.match(
  source,
  /function parseDashboardJsonPayload<T>\(value: unknown, fallback: T\): T/,
  '看板加载需要通过统一的安全 JSON 解析函数处理接口 payload'
)
assert.match(
  source,
  /value === undefined \|\| value === null \|\| value === ''/,
  '空字符串、null、undefined 的看板 payload 应回退为空数组或空对象，避免 JSON.parse 抛错中断加载'
)
assert.doesNotMatch(
  source,
  /JSON\.parse\(canvasInfo\.(component_data|canvas_style_data|canvas_view_info)/,
  'load_resource_prepare 不能直接解析接口字段，否则快速切换或空 payload 会打断看板初始化'
)
assert.match(
  source,
  /parseDashboardJsonPayload<any\[]>\(canvasInfo\.component_data, \[]\)/,
  'component_data 为空时应回退为空组件数组'
)
assert.match(
  source,
  /parseDashboardJsonPayload<Record<string, any>>\(canvasInfo\.canvas_view_info, \{}\)/,
  'canvas_view_info 为空时应回退为空图表信息对象'
)
