import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
test('treemap passes the hierarchy through G2 inline data connector', () => {
  const exports = {}
  class BaseG2Chart {
    chart = {
      options: (value) => {
        if (value) this.options = value
        return this.options || {}
      },
    }
    init(axis, data) {
      this.axis = axis
      this.data = data
    }
  }
  const deps = {
    BaseG2Chart,
    axisLabel: (a) => a.name,
    formatNumber: String,
    toNumber: Number,
    withChartThemeOptions: (x) => x,
    resolveG2ResponsiveStyle: () => ({}),
    getAxesWithFilter: (axes) =>
      Object.fromEntries(
        ['x', 'y', 'series'].map((type) => [type, axes.filter((a) => a.type === type)])
      ),
  }
  vm.runInNewContext(
    ts.transpileModule(readFileSync('src/views/chat/component/charts/Treemap.ts', 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    { exports, require: () => deps, console }
  )
  const chart = new exports.Treemap({})
  chart.init(
    [
      { type: 'x', value: 'category' },
      { type: 'y', value: 'amount' },
    ],
    [{ category: 'A', amount: 10 }]
  )
  assert.equal(chart.options.data.type, 'inline')
  assert.equal(chart.options.data.value.children[0].name, 'A')
  assert.equal(chart.options.data.value.children[0].value, 10)
})
