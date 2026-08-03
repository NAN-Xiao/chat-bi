import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const layoutSource = readFileSync('src/views/chat/component/charts/metricLayout.ts', 'utf8')
const compiled = ts.transpileModule(layoutSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveMetricLayout } = await import(moduleUrl)

const mini = resolveMetricLayout(
  { width: 213, height: 79, density: 'mini', surface: 'dashboard', hasOuterTitle: true },
  2
)
assert.equal(mini.showInnerLabel, false)
assert.equal(mini.showAccent, false)
assert.equal(mini.comparisonColumns, 2)
assert.ok(mini.requiredHeight <= 79)

const basic = resolveMetricLayout(
  { width: 360, height: 180, density: 'basic', surface: 'dashboard', hasOuterTitle: true },
  2
)
assert.equal(basic.showInnerLabel, true)
assert.equal(basic.showAccent, true)

const chatMini = resolveMetricLayout(
  { width: 213, height: 79, density: 'mini', surface: 'chat', hasOuterTitle: false },
  2
)
assert.equal(chatMini.showInnerLabel, true)

const metricSource = readFileSync('src/views/chat/component/charts/Metric.ts', 'utf8')
assert.match(metricSource, /resolveMetricLayout\(this\.layoutContext/)
assert.match(metricSource, /className = ['"]metric-comparisons['"]/)
assert.match(metricSource, /gridTemplateColumns/)
assert.match(metricSource, /if \(layout\.showInnerLabel/)
assert.match(metricSource, /if \(layout\.showAccent/)
console.log('Metric responsive tests passed')
