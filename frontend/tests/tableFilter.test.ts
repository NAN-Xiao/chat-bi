import assert from 'node:assert/strict'
import test from 'node:test'

import {
  EMPTY_FILTER_VALUE,
  applyTableFilters,
  collectTableFilterOptions,
  normalizeTableFilterValue,
  searchTableFilterOptions,
} from '../src/views/chat/component/charts/tableFilter.ts'
import {
  TABLE_HEADER_ACTION_ICON_THEME,
  resolveTableHeaderActionIconFill,
} from '../src/views/chat/component/charts/tableHeaderActions.ts'

const rows = [
  { channel: '应用商店', region: '华东', amount: 10 },
  { channel: '广告', region: '华东', amount: 20 },
  { channel: '应用商店', region: '华南', amount: 30 },
  { channel: null, region: '华南', amount: 40 },
  { channel: '', region: '华北', amount: 50 },
]

test('同列多个精确值按 OR 筛选', () => {
  const filters = new Map([
    [
      'channel',
      new Set([normalizeTableFilterValue('应用商店'), normalizeTableFilterValue('广告')]),
    ],
  ])

  assert.deepEqual(
    applyTableFilters(rows, filters).map((row) => row.amount),
    [10, 20, 30]
  )
})

test('跨列筛选条件按 AND 组合', () => {
  const filters = new Map([
    ['channel', new Set([normalizeTableFilterValue('应用商店')])],
    ['region', new Set([normalizeTableFilterValue('华南')])],
  ])

  assert.deepEqual(
    applyTableFilters(rows, filters).map((row) => row.amount),
    [30]
  )
})

test('null、undefined 和空字符串统一归为空值', () => {
  assert.equal(normalizeTableFilterValue(null), EMPTY_FILTER_VALUE)
  assert.equal(normalizeTableFilterValue(undefined), EMPTY_FILTER_VALUE)
  assert.equal(normalizeTableFilterValue(''), EMPTY_FILTER_VALUE)

  const filters = new Map([['channel', new Set([EMPTY_FILTER_VALUE])]])
  assert.deepEqual(
    applyTableFilters(rows, filters).map((row) => row.amount),
    [40, 50]
  )
})

test('清空全部筛选后恢复原始数据且不修改原数组', () => {
  const snapshot = structuredClone(rows)
  const result = applyTableFilters(rows, new Map())

  assert.deepEqual(result, rows)
  assert.notEqual(result, rows)
  assert.deepEqual(rows, snapshot)
})

test('候选值按精确类型去重并统计数量', () => {
  const options = collectTableFilterOptions(
    [{ value: 1 }, { value: '1' }, { value: 1 }, { value: null }, { value: '' }],
    'value'
  )

  assert.deepEqual(
    options.map(({ label, count, isEmpty }) => ({ label, count, isEmpty })),
    [
      { label: '1', count: 2, isEmpty: false },
      { label: '1', count: 1, isEmpty: false },
      { label: '（空值）', count: 2, isEmpty: true },
    ]
  )
  assert.notEqual(options[0].key, options[1].key)
})

test('搜索候选值忽略大小写并最多返回前 200 项', () => {
  const options = collectTableFilterOptions(
    Array.from({ length: 250 }, (_, index) => ({ value: `Channel-${index}` })),
    'value'
  )

  assert.equal(searchTableFilterOptions(options, 'channel').length, 200)
  assert.deepEqual(
    searchTableFilterOptions(options, 'CHANNEL-24').map((option) => option.label),
    [
      'Channel-24',
      'Channel-240',
      'Channel-241',
      'Channel-242',
      'Channel-243',
      'Channel-244',
      'Channel-245',
      'Channel-246',
      'Channel-247',
      'Channel-248',
      'Channel-249',
    ]
  )
})

test('筛选和排序按钮使用 24px 点击区与 4px 间距', () => {
  assert.deepEqual(TABLE_HEADER_ACTION_ICON_THEME, {
    size: 24,
    margin: { left: 0, right: 4 },
  })
})

test('表头按钮悬浮时独立高亮并在离开后恢复状态色', () => {
  assert.equal(resolveTableHeaderActionIconFill('filter', true, false), '#409eff')
  assert.equal(resolveTableHeaderActionIconFill('filter', true, true), '#337ecc')
  assert.equal(resolveTableHeaderActionIconFill('sort', false, false), '#909399')
  assert.equal(resolveTableHeaderActionIconFill('sort', false, true), '#606266')
})
