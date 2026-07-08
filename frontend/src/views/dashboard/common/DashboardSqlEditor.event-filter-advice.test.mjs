import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const nonBlockingAdviceMatch = source.match(/function isNonBlockingBuilderAdviceItem\(value: string\) \{([\s\S]*?)\r?\n\}/)

assert.ok(nonBlockingAdviceMatch, '需要保留配置 Agent 非阻断建议识别函数')
assert.match(
  nonBlockingAdviceMatch[1],
  /事件筛选条件|事件名筛选|未限定\s*event/,
  '事件类指标已自带 eventName，Agent 误报“缺少事件筛选条件”时不能阻断 SQL 生成'
)
