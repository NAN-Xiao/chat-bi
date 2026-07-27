import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const utilsSource = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
const functionMatch = utilsSource.match(
  /const ISO_DATE_AXIS_VALUE_PATTERN[\s\S]*?^\}/m
)

assert.ok(functionMatch, '图表工具层必须提供共享日期轴标签格式化函数')

const compiled = ts.transpileModule(functionMatch[0], {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { formatCategoryAxisLabel } = await import(moduleUrl)

assert.equal(formatCategoryAxisLabel('2026-07-27'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-07-27 08:30:00'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-07-27T08:30:00Z'), '07/27')
assert.equal(formatCategoryAxisLabel('2026-02-29'), '2026-02-29')
assert.equal(formatCategoryAxisLabel('2024-02-29'), '02/29')
assert.equal(formatCategoryAxisLabel('2026-13-01'), '2026-13-01')
assert.equal(formatCategoryAxisLabel('release-2026-07-27'), 'release-2026-07-27')
assert.equal(formatCategoryAxisLabel(20260727), '20260727')
assert.equal(formatCategoryAxisLabel(null), '')
assert.equal(formatCategoryAxisLabel(undefined), '')

console.log('Chart axis date label behavior tests passed')
