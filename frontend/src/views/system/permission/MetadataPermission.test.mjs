import assert from 'node:assert/strict'
import test from 'node:test'
import { permissionRulesToSaveEntries } from './permissionFieldEntries.ts'

test('metadata permission entries preserve stable targets when saving', () => {
  const target = {
    object_type: 'EVENT_PROPERTY',
    event_name: 'order_paid',
    event_property_key: 'amount',
    canonical_key: 'event-property:order_paid:amount',
    enable: false,
  }
  const [entry] = permissionRulesToSaveEntries([
    {
      type: 'event_property',
      permissions: [target],
      permission_list: ['temporary-id'],
      table_id: null,
    },
  ])
  assert.deepEqual(entry.permissions, [target])
  assert.deepEqual(entry.permission_list, [])
})

test('metadata permissions do not submit a physical table id', () => {
  const [entry] = permissionRulesToSaveEntries([
    {
      type: 'schema',
      permissions: [{ catalog_key: 'main', schema_key: 'sales', enable: false }],
      table_id: 42,
    },
  ])
  assert.equal('table_id' in entry, false)
  assert.equal(entry.permissions[0].schema_key, 'sales')
})
