import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const compilerOptions = { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
const validationSource = readFileSync('src/views/chat/component/chartValidation.ts', 'utf8')
const validationCompiled = ts.transpileModule(validationSource, { compilerOptions }).outputText
const validationModuleUrl = `data:text/javascript;base64,${Buffer.from(validationCompiled).toString('base64')}`
const source = readFileSync('src/views/chat/component/charts/radialPartition.ts', 'utf8').replace(
  '@/views/chat/component/chartValidation.ts',
  validationModuleUrl
)
const compiled = ts.transpileModule(source, {
  compilerOptions,
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
  assert.equal(result.percentageField, RADIAL_PERCENTAGE_FIELD)
})

test('prepareRadialSlices preserves business fields that use the internal percentage name', () => {
  const categoryCollision = prepareRadialSlices(
    [{ [RADIAL_PERCENTAGE_FIELD]: 'A', count: 5 }],
    RADIAL_PERCENTAGE_FIELD,
    'count'
  )
  assert.equal(categoryCollision.data[0][RADIAL_PERCENTAGE_FIELD], 'A')
  assert.notEqual(categoryCollision.percentageField, RADIAL_PERCENTAGE_FIELD)
  assert.equal(categoryCollision.data[0][categoryCollision.percentageField], 100)

  const valueCollision = prepareRadialSlices(
    [{ range: 'A', [RADIAL_PERCENTAGE_FIELD]: 5 }],
    'range',
    RADIAL_PERCENTAGE_FIELD
  )
  assert.equal(valueCollision.data[0][RADIAL_PERCENTAGE_FIELD], 5)
  assert.notEqual(valueCollision.percentageField, RADIAL_PERCENTAGE_FIELD)
  assert.equal(valueCollision.data[0][valueCollision.percentageField], 100)
})

test('prepareRadialSlices accepts only valid decimal and thousands formats', () => {
  const result = prepareRadialSlices([{ range: 'A', count: '1,234.5' }], 'range', 'count')
  assert.equal(result.data[0].count, 1234.5)

  assert.throws(
    () => prepareRadialSlices([{ range: 'A', count: '1,2' }], 'range', 'count'),
    (error) => error?.code === 'invalid_value'
  )
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
  [
    'invalid_value',
    [{ range: 'A', count: Number.MAX_VALUE }, { range: 'B', count: Number.MAX_VALUE }],
    'range',
    'count',
  ],
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
