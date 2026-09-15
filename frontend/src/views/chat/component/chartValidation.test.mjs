import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/chartValidation.ts', 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { trendDimensionError } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
assert.equal(typeof trendDimensionError, 'function')
const axis = [{ value: 'day', type: 'x' }]
assert.equal(trendDimensionError('line', axis, [56, 60, 79, 70, 79, 72, 63].map(value => ({ day: null, value }))), 'invalid_trend_dimension')
assert.equal(trendDimensionError('area', axis, [{ day: '2026-09-08' }, { day: null }]), 'invalid_trend_dimension')
assert.equal(trendDimensionError('line', axis, [{ value: 10 }]), 'invalid_trend_dimension')
assert.equal(trendDimensionError('line', [], [{ value: 10 }]), 'missing_category_field')
assert.equal(trendDimensionError('line', axis, []), undefined)
assert.equal(trendDimensionError('line', axis, [{ day: '2026-09-08', value: 0 }, { day: '2026-09-08', value: null }]), undefined)
assert.equal(trendDimensionError('table', axis, [{ day: null }]), undefined)
assert.equal(trendDimensionError('column', axis, [{ day: null }]), undefined)
assert.equal(trendDimensionError('line', axis, [{ day: 0 }, { day: false }]), undefined)
console.log('Trend dimension validation passed')
