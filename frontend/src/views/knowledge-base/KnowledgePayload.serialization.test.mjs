import assert from 'node:assert/strict'
import test from 'node:test'
import {
  applyParsedUpload,
  serializeEvent,
  serializeJsonField,
  serializeKnowledgeDraft,
} from './knowledgePayloadTypes.ts'

test('business payload preserves business question and SQL example', () => {
  const payload = serializeKnowledgeDraft({
    knowledge_type: 'BUSINESS',
    term: '收入',
    aliases: [],
    definition: '订单收入',
    formula: 'sum(amount)',
    constraints: [],
    related_objects: [],
    examples: [{ name: '收入趋势', question: '收入是多少', sql: 'select sum(amount) from orders' }],
  })
  assert.equal(payload.knowledge_type, 'BUSINESS')
  assert.equal(payload.examples[0].question, '收入是多少')
  assert.equal(payload.examples[0].sql, 'select sum(amount) from orders')
})

test('event and JSON editors preserve stable source fields', () => {
  const event = serializeEvent({
    knowledge_type: 'EVENT',
    event_name: 'pay',
    display_name: '支付',
    aliases: [],
    description: '',
    table_name: 'event',
    event_name_field: 'event_name',
    event_time_field: 'event_time',
    parameters: [{ name: 'status', data_type: 'string', value_mappings: { paid: '已付费' } }],
  })
  const json = serializeJsonField({
    knowledge_type: 'JSON_FIELD',
    schema_name: 'public',
    table_name: 'orders',
    source_field: 'payload',
    json_path: '$.order.amount',
    field_name: 'order_amount',
    display_name: '订单金额',
    data_type: 'number',
    expression: "payload->>'order'",
    aliases: [],
    description: '',
    value_mappings: { paid: '已付费' },
  })
  assert.deepEqual(event.parameters[0].value_mappings, { paid: '已付费' })
  assert.equal(json.json_path, '$.order.amount')
})

test('document reupload replaces markdown instead of merging old content', () => {
  assert.equal(applyParsedUpload('# New', '# Old\nremoved'), '# New')
})
