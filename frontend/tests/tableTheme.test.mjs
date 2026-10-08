import assert from 'node:assert/strict'
import { test } from 'node:test'
import { existsSync, readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
test('S2 body, headers, selection and text follow dark tokens', () => {
  const file = 'src/views/chat/component/charts/tableTheme.ts'
  assert.ok(existsSync(file), 'S2 needs its own theme adapter')
  const exports = {}
  const values = {
    '--workspace-card-bg': '#202733',
    '--workspace-control-bg': '#283343',
    '--workspace-text-primary': '#f1f5fb',
    '--workspace-border': '#394556',
    '--workspace-control-hover-bg': '#34445b',
    '--workspace-active-bg': '#2c3d57',
    '--theme-chart-blue': '#79a6ff',
  }
  vm.runInNewContext(
    ts.transpileModule(readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    { exports, getComputedStyle: () => ({ getPropertyValue: (k) => values[k] || '' }) }
  )
  const { theme } = exports.getTableTheme({})
  assert.equal(theme.dataCell.cell.backgroundColor, '#202733')
  assert.equal(theme.colCell.cell.backgroundColor, '#283343')
  assert.equal(theme.dataCell.text.fill, '#f1f5fb')
  assert.equal(theme.dataCell.cell.interactionState.selected.backgroundColor, '#2c3d57')
})
