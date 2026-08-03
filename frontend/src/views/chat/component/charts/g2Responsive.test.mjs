import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/charts/g2Responsive.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveG2ResponsiveStyle } = await import(moduleUrl)

const miniCartesian = resolveG2ResponsiveStyle(
  { width: 280, height: 110, density: 'mini', surface: 'dashboard', hasOuterTitle: true },
  'cartesian'
)
assert.equal(miniCartesian.axisLabelFontSize, 9)
assert.equal(miniCartesian.showPointLabels, false)
assert.deepEqual(miniCartesian.padding, [4, 6, 18, 28])

const miniStructure = resolveG2ResponsiveStyle(
  { width: 240, height: 110, density: 'mini', surface: 'dashboard', hasOuterTitle: true },
  'structure'
)
assert.equal(miniStructure.legendPosition, 'bottom')
assert.equal(miniStructure.structureLabelFontSize, 9)

const files = [
  'Line.ts',
  'Area.ts',
  'Column.ts',
  'Bar.ts',
  'Scatter.ts',
  'Heatmap.ts',
  'Pie.ts',
  'Funnel.ts',
  'Sankey.ts',
  'Treemap.ts',
]
for (const file of files) {
  const chart = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(chart, /resolveG2ResponsiveStyle\(this\.layoutContext/, `${file} 必须消费共享尺寸策略`)
}
console.log('G2 responsive tests passed')
