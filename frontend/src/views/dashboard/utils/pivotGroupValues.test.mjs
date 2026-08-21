import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildPersistedPivotGroupValueSelection,
  normalizePivotGroupValueMode,
  shouldConstrainPivotGroupValues,
} from './pivotGroupValues.ts'

test('全选保存为动态 all，不固化当前枚举', () => {
  assert.deepEqual(buildPersistedPivotGroupValueSelection('all', ['Organic', 'Facebook']), {
    group_value_mode: 'all',
    group_values: [],
  })
})

test('部分选择保存为 custom 白名单', () => {
  assert.deepEqual(buildPersistedPivotGroupValueSelection('custom', ['Organic']), {
    group_value_mode: 'custom',
    group_values: ['Organic'],
  })
})

test('旧配置按非空列表推断 custom，空列表推断 all', () => {
  assert.equal(normalizePivotGroupValueMode({ group_values: ['Organic'] }), 'custom')
  assert.equal(normalizePivotGroupValueMode({ group_values: [] }), 'all')
  assert.equal(normalizePivotGroupValueMode({}), 'all')
})

test('all 模式不约束新出现的分类，custom 模式继续过滤', () => {
  assert.equal(
    shouldConstrainPivotGroupValues({ group_value_mode: 'all', group_values: [] }),
    false
  )
  assert.equal(
    shouldConstrainPivotGroupValues({ group_value_mode: 'custom', group_values: ['Organic'] }),
    true
  )
})
