import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/charts/radialPartition.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const {
  RADIAL_PERCENTAGE_FIELD,
  formatRadialPercentage,
  prepareRadialSlices,
} = await import(moduleUrl)

test('prepareRadialSlices returns immutable rows with percentages', () => {
  const input = [
    { range: 'A', count: 1 },
    { range: 'B', count: '3' },
  ]

  const result = prepareRadialSlices(input, 'range', 'count')

  assert.equal(result.total, 4)
  assert.deepEqual(
    result.data.map((row) => row[RADIAL_PERCENTAGE_FIELD]),
    [25, 75]
  )
  assert.deepEqual(input, [
    { range: 'A', count: 1 },
    { range: 'B', count: '3' },
  ])
})

test('formatRadialPercentage keeps at most two decimal places', () => {
  assert.equal(formatRadialPercentage(1, 3), '33.33')
  assert.equal(formatRadialPercentage(1, 4), '25')
})

const invalidCases = [
  ['missing_category_field', [{ count: 1 }], 'range', 'count'],
  ['missing_value_field', [{ range: 'A' }], 'range', 'count'],
  ['empty_category', [{ range: ' ', count: 1 }], 'range', 'count'],
  ['duplicate_category', [{ range: 'A', count: 1 }, { range: 'A', count: 2 }], 'range', 'count'],
  ['invalid_value', [{ range: 'A', count: 'abc' }], 'range', 'count'],
  ['negative_value', [{ range: 'A', count: -1 }], 'range', 'count'],
  ['zero_total', [{ range: 'A', count: 0 }], 'range', 'count'],
  [
    'too_many_categories',
    Array.from({ length: 13 }, (_, index) => ({ range: `R${index}`, count: 1 })),
    'range',
    'count',
  ],
]

for (const [code, data, categoryField, valueField] of invalidCases) {
  test(`prepareRadialSlices rejects ${code}`, () => {
    assert.throws(
      () => prepareRadialSlices(data, categoryField, valueField),
      (error) => error?.code === code
    )
  })
}
