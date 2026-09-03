import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/charts/compactDate.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { formatCompactDateByAxis } = await import(moduleUrl)

assert.equal(formatCompactDateByAxis(20260827, { value: 'cohort_date' }), '2026-08-27')
assert.equal(formatCompactDateByAxis('20260901', { name: '日期', value: 'cohort' }), '2026-09-01')
assert.equal(formatCompactDateByAxis(20260229, { value: 'cohort_date' }), null)
assert.equal(formatCompactDateByAxis(20240229, { value: 'cohort_date' }), '2024-02-29')
assert.equal(formatCompactDateByAxis(20260827, { value: 'cohort_size' }), null)
assert.equal(formatCompactDateByAxis(20260827, { value: 'date_id' }), null)
assert.equal(formatCompactDateByAxis(20260827, { name: '日期编号', value: 'cohort' }), null)

const utilsSource = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
const tableSource = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')
assert.match(
  utilsSource,
  /const compactDate = formatCompactDateByAxis\(value, axis\)[\s\S]*?return compactDate/,
  '共享表格数值格式化前必须先处理明确日期字段的 YYYYMMDD 值'
)
assert.match(
  tableSource,
  /collectTableFilterOptions\([\s\S]*?resolveTableDisplayValue\(value, fieldAxis\)/,
  '表格列筛选应与单元格复用相同的日期显示格式'
)

console.log('Compact table date formatting tests passed')
