import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
const tokens = {
  '--theme-chart-palette': '#79a6ff, #42d49a, #f5b45e, #af98f5',
  '--theme-chart-grid': '#384658',
  '--theme-chart-label': '#8b9cb2',
  '--theme-chart-legend': '#8b9cb2',
  '--theme-chart-value': '#f1f5fb',
  '--theme-panel-bg': '#202733',
  '--theme-overlay-bg': '#283343',
  '--theme-overlay-border': '#53647b',
  '--theme-text-primary': '#f1f5fb',
}
const exports = {}
vm.runInNewContext(
  ts.transpileModule(readFileSync('src/views/chat/component/charts/theme.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  { exports, getComputedStyle: () => ({ getPropertyValue: (key) => tokens[key] || '' }) }
)
test('canvas palette, axis and tooltip use applied theme', () => {
  assert.equal(typeof exports.getChartTheme, 'function')
  const theme = exports.getChartTheme({})
  assert.equal(theme.axis.gridStroke, '#384658')
  assert.equal(theme.axis.labelFill, '#8b9cb2')
  assert.equal(theme.category10[0], '#79a6ff')
  assert.equal(theme.tooltip.css['.g2-tooltip']['background-color'], '#283343')
})
test('explicit chart colors remain authoritative', () => {
  const color = { range: ['#123456'] }
  const spec = exports.withChartThemeOptions({ scale: { color } })
  assert.equal(spec.scale.color.range[0], '#123456')
})
