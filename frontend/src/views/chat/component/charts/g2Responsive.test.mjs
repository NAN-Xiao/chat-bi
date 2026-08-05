import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/charts/g2Responsive.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveCategoryAxisResponsiveOptions, resolveG2ResponsiveStyle } = await import(moduleUrl)

const miniCartesian = resolveG2ResponsiveStyle(
  { width: 280, height: 110, density: 'mini', surface: 'dashboard', hasOuterTitle: true },
  'cartesian'
)
assert.equal(miniCartesian.axisLabelFontSize, 9)
assert.equal(miniCartesian.showPointLabels, false)
assert.deepEqual(miniCartesian.padding, [4, 6, 18, 28])

const miniCategoryAxis = resolveCategoryAxisResponsiveOptions(miniCartesian)
assert.equal(miniCategoryAxis.labelAutoEllipsis, false)
assert.doesNotThrow(
  () => miniCategoryAxis.labelFilter('2026-07-01', 0),
  'G2 自动布局仅传 datum 和 index 时，分类轴过滤器不得读取缺失的数组参数'
)
assert.equal(
  miniCategoryAxis.labelFilter('2026-07-01', 0),
  true,
  '缺少完整刻度数组时必须保留标签，由 G2 自身完成自动隐藏'
)
const thirtyTicks = Array.from({ length: 30 }, (_, index) => `2026-07-${String(index + 1).padStart(2, '0')}`)
const visibleMiniTicks = thirtyTicks.filter((tick, index, array) =>
  miniCategoryAxis.labelFilter(tick, index, array)
)
assert.ok(visibleMiniTicks.length <= miniCartesian.maxCategoryAxisLabels)
assert.equal(visibleMiniTicks[0], '2026-07-01')
assert.equal(visibleMiniTicks.at(-1), '2026-07-30')
for (let index = 1; index < visibleMiniTicks.length; index++) {
  assert.notEqual(visibleMiniTicks[index], visibleMiniTicks[index - 1])
}

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
  'Funnel.ts',
  'Sankey.ts',
  'Treemap.ts',
]
for (const file of files) {
  const chart = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(chart, /resolveG2ResponsiveStyle\(this\.layoutContext/, `${file} 必须消费共享尺寸策略`)
}

const radialPartitionChart = readFileSync(
  'src/views/chat/component/charts/RadialPartitionChart.ts',
  'utf8'
)
assert.match(
  radialPartitionChart,
  /resolveG2ResponsiveStyle\(this\.layoutContext/,
  '共享径向图渲染器必须消费共享尺寸策略'
)
for (const file of ['Pie.ts', 'Donut.ts']) {
  const chart = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(chart, /extends RadialPartitionChart/, `${file} 必须继承共享径向图渲染器`)
}

for (const file of ['Line.ts', 'Area.ts', 'Column.ts']) {
  const chart = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(
    chart,
    /buildMixedUnitComboOptions\([\s\S]*?responsive[\s\S]*?\)/,
    `${file} 的混合单位图也必须传入共享尺寸策略`
  )
}

const chartUtils = readFileSync('src/views/chat/component/charts/utils.ts', 'utf8')
assert.match(
  chartUtils,
  /resolveCategoryAxisResponsiveOptions/,
  '混合单位图横轴必须复用分类轴抽样策略，避免 30 天日期重叠'
)
console.log('G2 responsive tests passed')
