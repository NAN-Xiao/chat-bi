import assert from 'node:assert/strict'
import test from 'node:test'
import { serializeFormulaTokensForContext } from './formulaMetricUtils.ts'

const atom = (logic, filters) => ({ id:'atom',field:'events.action',metric:'events.actor',
  aggregation:'count_distinct',alias:'人数',filterLogic:logic,filters })
const resolve = (value) => ({table:'events',field:value.split('.').at(-1)})

for (const logic of ['and','or']) {
  test(`formula wire contract preserves ${logic} root and empty filter group`, () => {
    const metric=atom(logic,[])
    const output=serializeFormulaTokensForContext([{type:'atomicMetric',metric}],new Map(),resolve)
    assert.deepEqual(output[0].metric.filters,{logic,rules:[]})
    assert.deepEqual(metric.filters,[])
  })
  test(`formula wire contract preserves ${logic}, nested groups and field resolution`, () => {
    const rules=[{id:'a',field:'events.amount',operator:'gt',value:'1'},
      {id:'g',type:'group',logic:'and',field:'',operator:'',value:'',children:[
        {id:'b',field:'events.category',operator:'eq',value:'A'}]}]
    const original=structuredClone(rules)
    const output=serializeFormulaTokensForContext([{type:'atomicMetric',metric:atom(logic,rules)}],new Map(),resolve)
    assert.deepEqual(output[0].metric.filters,{logic,rules:[
      {...rules[0],field:resolve('events.amount')},
      {...rules[1],children:[{...rules[1].children[0],field:resolve('events.category')}]}]})
    assert.deepEqual(rules,original,'serialization must not rewrite the editor draft')
  })
}
