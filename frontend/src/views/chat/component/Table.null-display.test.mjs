import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const table = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')

assert.match(
  table,
  /function resolveTableDisplayValue\([\s\S]*?value === null[\s\S]*?value === undefined[\s\S]*?return ['"]-['"]/,
  '共享 S2 表格必须把 null 和 undefined 显示为 -'
)

assert.match(
  table,
  /typeof value === ['"]string['"][\s\S]*?trim\(\)\.toLowerCase\(\) === ['"]null['"][\s\S]*?return ['"]-['"]/,
  '共享 S2 表格必须把字符串 null 显示为 -'
)

assert.match(
  table,
  /formatter:\s*\(value: any\) => \{\s*return resolveTableDisplayValue\(value, a\)\s*\}/,
  'S2 meta formatter 必须统一走空值展示格式化'
)

console.log('Table null display tests passed')
