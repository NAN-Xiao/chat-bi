import assert from 'node:assert/strict'

const utils = await import('./formulaMetricUtils.ts')

const metrics = [
  { label: '指标1', value: 'metric-1' },
  { label: '指标2', value: 'metric-2' },
]
const atomicMetric = {
  id: 'atomic-1',
  field: 'event.role_upgrade',
  metric: 'user_id',
  aggregation: 'count_distinct',
  alias: '角色升级触发用户数',
  label: '角色升级.触发用户数',
  filterLogic: 'and',
  filters: [],
}

assert.deepEqual(
  utils.validateFormulaTokens(
    [
      { type: 'metric', metricId: 'metric-1' },
      { type: 'operator', value: '/' },
      { type: 'metric', metricId: 'metric-2' },
    ],
    metrics
  ),
  { valid: true, message: '' },
  '完整公式应校验通过'
)

assert.equal(
  utils.validateFormulaTokens(
    [
      { type: 'metric', metricId: 'metric-1' },
      { type: 'operator', value: '/' },
    ],
    metrics
  ).message,
  '除号后缺少指标或数字',
  '除号结尾应提示缺少右操作数'
)

assert.equal(
  utils.validateFormulaTokens(
    [
      { type: 'metric', metricId: 'metric-1' },
      { type: 'metric', metricId: 'metric-2' },
    ],
    metrics
  ).message,
  '两个指标或数字之间缺少运算符',
  '相邻指标必须提示缺少运算符'
)

assert.equal(
  utils.validateFormulaTokens([{ type: 'paren', value: '(' }, { type: 'metric', metricId: 'metric-1' }], metrics)
    .message,
  '括号不配对',
  '左括号未闭合应报错'
)

assert.deepEqual(
  utils.serializeFormulaTokensForContext(
    [
      { type: 'metric', metricId: 'metric-1' },
      { type: 'operator', value: '/' },
      { type: 'number', value: '100' },
    ],
    new Map([
      ['metric-1', '注册人数'],
      ['metric-2', '登录人数'],
    ])
  ),
  [
    { type: 'metric', metricId: 'metric-1', metricAlias: '注册人数' },
    { type: 'operator', value: '/' },
    { type: 'number', value: '100' },
  ],
  '上下文序列化应把 metricId 映射为指标别名'
)

assert.equal(
  utils.formulaTokensToText(
    [
      { type: 'metric', metricId: 'metric-1' },
      { type: 'operator', value: '/' },
      { type: 'metric', metricId: 'metric-2' },
    ],
    metrics
  ),
  '指标1 / 指标2',
  '公式展示文本应使用已有分析指标别名'
)

assert.equal(
  utils.formulaTokensToText(
    [
      { type: 'atomicMetric', metric: atomicMetric },
      { type: 'operator', value: '*' },
      { type: 'paren', value: '(' },
      { type: 'number', value: '100' },
      { type: 'paren', value: ')' },
    ],
    metrics
  ),
  '角色升级.触发用户数 * ( 100 )',
  '公式展示文本应支持公式内事件指标'
)

assert.deepEqual(
  utils.insertFormulaTokenAt(
    [
      { type: 'atomicMetric', metric: atomicMetric },
      { type: 'number', value: '100' },
    ],
    1,
    { type: 'operator', value: '*' }
  ),
  [
    { type: 'atomicMetric', metric: atomicMetric },
    { type: 'operator', value: '*' },
    { type: 'number', value: '100' },
  ],
  '应按光标位置插入公式 token'
)

assert.deepEqual(
  utils.serializeFormulaTokensForContext(
    [
      { type: 'atomicMetric', metric: atomicMetric },
      { type: 'operator', value: '*' },
      { type: 'number', value: '100' },
    ],
    new Map()
  ),
  [
    { type: 'atomicMetric', metric: atomicMetric },
    { type: 'operator', value: '*' },
    { type: 'number', value: '100' },
  ],
  '上下文序列化应保留公式内事件指标配置'
)
