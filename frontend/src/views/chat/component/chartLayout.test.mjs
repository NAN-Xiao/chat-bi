import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/chartLayout.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveChartDensity, buildChartLayoutContext } = await import(moduleUrl)

assert.equal(resolveChartDensity(213, 79), 'mini')
assert.equal(resolveChartDensity(360, 180), 'basic')
assert.equal(resolveChartDensity(720, 420), 'regular')
assert.equal(resolveChartDensity(263, 123, 'mini'), 'mini')
assert.equal(resolveChartDensity(280, 140, 'mini'), 'basic')
assert.equal(resolveChartDensity(416, 216, 'regular'), 'regular')
assert.deepEqual(
  buildChartLayoutContext({ width: 213, height: 79, surface: 'dashboard', hasOuterTitle: true }),
  { width: 213, height: 79, density: 'mini', surface: 'dashboard', hasOuterTitle: true }
)
console.log('Chart layout tests passed')
