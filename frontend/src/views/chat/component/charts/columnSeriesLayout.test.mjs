import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const helperPath = 'src/views/chat/component/charts/columnSeriesLayout.ts'
assert.equal(existsSync(helperPath), true, '应提供柱状图系列布局策略')

const source = readFileSync(helperPath, 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveColumnSeriesTransform } = await import(moduleUrl)

assert.deepEqual(resolveColumnSeriesTransform('stacked', true), [{ type: 'stackY' }])
assert.deepEqual(resolveColumnSeriesTransform('grouped', true), [{ type: 'dodgeX' }])
assert.equal(resolveColumnSeriesTransform('grouped', false), undefined)

const columnSource = readFileSync('src/views/chat/component/charts/Column.ts', 'utf8')
const groupedSource = readFileSync('src/views/chat/component/charts/GroupedColumn.ts', 'utf8')
const utilsSource = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
const registrySource = readFileSync('src/views/chat/component/index.ts', 'utf8')
const baseSource = readFileSync('src/views/chat/component/BaseChart.ts', 'utf8')

assert.match(columnSource, /resolveColumnSeriesTransform\(this\.seriesLayout/)
assert.match(groupedSource, /chartName:\s*'grouped_column'/)
assert.match(groupedSource, /seriesLayout:\s*'grouped'/)
assert.match(utilsSource, /intervalTransform/)
assert.match(registrySource, /grouped_column:\s*GroupedColumn/)
assert.match(baseSource, /\| 'grouped_column'/)
