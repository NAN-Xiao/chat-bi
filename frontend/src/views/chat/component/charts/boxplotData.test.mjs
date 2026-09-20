import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

function moduleUrl(path, replacements = {}) {
  let code = ts.transpileModule(readFileSync(path, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  for (const [from, to] of Object.entries(replacements)) code = code.replaceAll(from, to)
  return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
}
const validation = moduleUrl('src/views/chat/component/chartValidation.ts')
const { prepareBoxplotData } = await import(
  moduleUrl('src/views/chat/component/charts/boxplotData.ts', {
    '@/views/chat/component/chartValidation.ts': validation,
  })
)
const axes = [
  { value: 'category', type: 'x' },
  { value: 'value', type: 'y' },
]
const rows = (values, category = 'A') => values.map((value) => ({ category, value }))

test('calculates interpolated quartiles, Tukey whiskers and outliers without mutating samples', () => {
  const input = rows([100, 4, 3, 2, 1, 0])
  const original = structuredClone(input)
  const result = prepareBoxplotData(axes, input)
  assert.deepEqual(result.boxes[0], {
    category: 'A',
    series: '',
    low: 0,
    q1: 1.25,
    median: 2.5,
    q3: 3.75,
    high: 4,
    count: 6,
  })
  assert.deepEqual(result.outliers, [{ category: 'A', series: '', value: 100 }])
  assert.deepEqual(input, original)
})
test('groups each series independently, including outliers', () => {
  const result = prepareBoxplotData(
    [...axes, { value: 'group', type: 'series' }],
    [
      ...rows([1, 2, 3, 4, 100]).map((r) => ({ ...r, group: 'one' })),
      ...rows([100, 101, 102, 103, 104]).map((r) => ({ ...r, group: 'two' })),
      ...rows([-8, -4, 0], 'B').map((r) => ({ ...r, group: 'one' })),
    ]
  )
  assert.deepEqual(
    result.boxes.map((b) => [b.category, b.series, b.median]),
    [
      ['A', 'one', 3],
      ['A', 'two', 102],
      ['B', 'one', -4],
    ]
  )
  assert.deepEqual(result.outliers, [{ category: 'A', series: 'one', value: 100 }])
})
test('handles singleton, constant, negative and numeric string samples', () => {
  const result = prepareBoxplotData(axes, [...rows(['-2']), ...rows([0, 0, 0], 'B')])
  assert.deepEqual(
    result.boxes.map(({ low, q1, median, q3, high }) => [low, q1, median, q3, high]),
    [
      [-2, -2, -2, -2, -2],
      [0, 0, 0, 0, 0],
    ]
  )
  assert.deepEqual(result.outliers, [])
})
test('rejects missing bindings and multiple metrics rather than substituting fields', () => {
  for (const [binding, code] of [
    [[], 'missing_category_field'],
    [[axes[0]], 'missing_value_field'],
    [[...axes, { value: 'other', type: 'y' }], 'multiple_value_fields'],
    [[...axes, { value: 'other', type: 'x' }], 'multiple_category_fields'],
  ])
    assert.throws(
      () => prepareBoxplotData(binding, rows([1])),
      (e) => e.code === code
    )
})
test('rejects missing fields, empty categories and invalid values', () => {
  assert.throws(
    () => prepareBoxplotData(axes, [{ value: 1 }]),
    (e) => e.code === 'missing_category_field'
  )
  assert.throws(
    () => prepareBoxplotData(axes, [{ category: 'A' }]),
    (e) => e.code === 'missing_value_field'
  )
  assert.throws(
    () => prepareBoxplotData(axes, rows([1], '')),
    (e) => e.code === 'empty_category'
  )
  for (const value of [null, undefined, '', ' ', 'bad', Infinity, NaN, true, [], '0x10']) {
    assert.throws(
      () => prepareBoxplotData(axes, rows([value])),
      (e) => e.code === 'invalid_value'
    )
  }
  assert.throws(
    () => prepareBoxplotData([...axes, { value: 'absent', type: 'series' }], rows([1])),
    (e) => e.code === 'invalid_boxplot_series'
  )
})
test('empty results remain empty', () => {
  assert.deepEqual(prepareBoxplotData(axes, []), { boxes: [], outliers: [] })
})
