import assert from 'node:assert/strict'
import test from 'node:test'
import { setRevenuePaymentEvent, setRevenueMetricEvent, setRevenueCostEvent, setRevenueCostMetric } from './revenueAnalysis.ts'

const config = () => ({ paymentEvent: 'paid', metricEvent: 'income', costEvent: 'expense',
  metric: { method: 'property_sum', field: 'income.amount' }, costMethod: 'property_sum', costField: 'expense.cost' })

test('changing eligibility event preserves the independent income selection', () => {
  const state = config()
  setRevenuePaymentEvent(state, 'paid-v2')
  assert.equal(state.paymentEvent, 'paid-v2')
  assert.equal(state.metricEvent, 'income')
  assert.equal(state.metric.field, 'income.amount')
  assert.equal(state.costEvent, 'expense')
  assert.equal(state.costField, 'expense.cost')
})

test('changing metric event preserves payer event and independent cost field', () => {
  const state = config()
  setRevenueMetricEvent(state, 'income-v2')
  assert.equal(state.paymentEvent, 'paid')
  assert.equal(state.metricEvent, 'income-v2')
  assert.equal(state.metric.field, '')
  assert.equal(state.costField, 'expense.cost')
})

test('reselecting either current event preserves valid properties', () => {
  const state = config()
  setRevenuePaymentEvent(state, 'paid')
  setRevenueMetricEvent(state, 'income')
  setRevenueCostEvent(state, 'expense')
  assert.deepEqual(state, config())
})

test('changing cost event clears only the cost amount field', () => {
  const state = config()
  setRevenueCostEvent(state, 'expense-v2')
  assert.deepEqual(state, { ...config(), costEvent:'expense-v2', costField:'' })
})

test('cost count needs no property and switching back does not restore stale property', () => {
  const state=config()
  setRevenueCostMetric(state,{method:'count',field:'expense.cost'})
  assert.equal(state.costMethod,'count')
  assert.equal(state.costField,'')
  assert.equal(state.metric.field,'income.amount')
  setRevenueCostMetric(state,{method:'property_sum',field:''})
  assert.equal(state.costMethod,'property_sum')
  assert.equal(state.costField,'')
})
