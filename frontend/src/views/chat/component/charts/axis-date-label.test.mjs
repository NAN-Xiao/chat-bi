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

const chartFiles = ['Line.ts', 'Area.ts', 'Column.ts', 'Bar.ts', 'Scatter.ts', 'Heatmap.ts']
const categoryAxisChartFiles = ['Line.ts', 'Area.ts', 'Column.ts', 'Bar.ts', 'Heatmap.ts']
for (const file of chartFiles) {
  const source = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(
    source,
    /formatCategoryAxisLabel/,
    `${file} 必须复用共享日期轴标签格式化函数`
  )
  assert.match(
    source,
    /axis:\s*\{[\s\S]*?x:\s*\{[\s\S]*?labelFormatter:\s*formatCategoryAxisLabel/,
    `${file} 的横轴必须使用共享日期格式`
  )
  if (categoryAxisChartFiles.includes(file)) {
    assert.match(
      source,
      /scale:\s*\{[\s\S]*?x:\s*\{[\s\S]*?type:\s*['\"]band['\"]/,
      `${file} 的分类横轴必须使用 band scale，避免数值维度生成小数刻度`
    )
  }
}

assert.match(
  utilsSource,
  /function buildMixedUnitComboOptions[\s\S]*?const xAxisOptions = \{[\s\S]*?labelFormatter:\s*formatCategoryAxisLabel/,
  '混合单位图表横轴必须使用共享日期格式'
)

const tableSource = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')
assert.doesNotMatch(
  tableSource,
  /formatCategoryAxisLabel/,
  '明细表不得接入日期轴短格式'
)

console.log('Chart axis date label behavior tests passed')
