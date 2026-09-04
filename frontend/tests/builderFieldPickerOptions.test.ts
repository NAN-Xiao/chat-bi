import assert from 'node:assert/strict'
import test from 'node:test'

import {
  eventRelatedPropertyOptions,
  eventScopedPropertyOptions,
  preferredBuilderEntityField,
  propertyAnalysisFieldOptions,
  type FieldOption,
} from '../src/views/dashboard/common/builderFieldPickerOptions.ts'

function fieldOption(overrides: Partial<FieldOption>): FieldOption {
  return {
    label: '字段',
    value: 'event.userinfo.channel',
    table: 'event',
    field: 'channel',
    ...overrides,
  }
}

test('preferred entity field uses the configured subject role', () => {
  const namedUidWithoutRole = fieldOption({
    label: '用户 ID',
    value: 'event.uid_alias',
    field: 'uid_alias',
  })
  const subjectField = fieldOption({
    label: '用户 ID',
    value: 'event.uid',
    field: 'uid',
    fieldRole: 'subject_id',
  })

  assert.equal(preferredBuilderEntityField([namedUidWithoutRole, subjectField]), 'event.uid')
  assert.equal(preferredBuilderEntityField([namedUidWithoutRole]), '')
})

test('retention events without dedicated properties still expose common user properties', () => {
  const eventOption = fieldOption({
    label: '当日活跃',
    value: 'tracking-event:event.event:EPSDKLogin',
    field: 'event',
    kind: 'tracking-event',
    eventName: 'EPSDKLogin',
    eventTable: 'event',
  })
  const userProperty = fieldOption({
    label: '渠道',
    sourceField: 'userinfo',
    jsonPath: '$.channel',
    isJsonSubfield: true,
  })

  assert.deepEqual(eventScopedPropertyOptions({
    eventOption,
    eventProperties: [],
    publicProperties: [userProperty],
    activeEventTable: 'event',
  }), [userProperty])
})

test('event and user properties are merged without duplicate values', () => {
  const eventOption = fieldOption({
    value: 'tracking-event:event.event:Login',
    field: 'event',
    kind: 'tracking-event',
    eventName: 'Login',
    eventTable: 'event',
  })
  const eventProperty = fieldOption({
    value: 'tracking-property:event.event:Login:channel',
    kind: 'tracking-property',
    eventName: 'Login',
  })
  const duplicate = fieldOption({
    ...eventProperty,
    label: '重复渠道',
  })

  assert.deepEqual(eventScopedPropertyOptions({
    eventOption,
    eventProperties: [eventProperty],
    publicProperties: [duplicate],
    activeEventTable: 'event',
  }), [eventProperty])
})

test('properties are unavailable outside the active event table', () => {
  const eventOption = fieldOption({
    value: 'tracking-event:other.event:Login',
    table: 'other',
    field: 'event',
    kind: 'tracking-event',
    eventName: 'Login',
    eventTable: 'other',
  })

  assert.deepEqual(eventScopedPropertyOptions({
    eventOption,
    publicProperties: [fieldOption({})],
    activeEventTable: 'event',
  }), [])
})

test('related properties include selected event properties plus uid and userinfo common properties', () => {
  const eventOption = fieldOption({
    value: 'tracking-event:event.event:Login',
    field: 'event',
    kind: 'tracking-event',
    eventName: 'Login',
    eventTable: 'event',
  })
  const eventProperty = fieldOption({
    value: 'tracking-property:event.event:Login:session_id',
    field: 'session_id',
    kind: 'tracking-property',
    eventName: 'Login',
    sourceField: 'personal',
    jsonPath: '$.session_id',
  })
  const uidProperty = fieldOption({
    label: '用户 ID',
    value: 'event.uid',
    field: 'uid',
    fieldRole: 'subject_id',
  })
  const eventPropertySchemaField = fieldOption({
    value: 'event.personal.session_id',
    field: 'personal.session_id',
    sourceField: 'personal',
    jsonPath: '$.session_id',
    isJsonSubfield: true,
  })
  const userProperty = fieldOption({
    label: '渠道',
    value: 'event.userinfo.channel',
    field: 'userinfo.channel',
    sourceField: 'userinfo',
    jsonPath: '$.channel',
    isJsonSubfield: true,
  })

  assert.deepEqual(eventRelatedPropertyOptions({
    eventOption,
    eventProperties: [eventProperty],
    allEventProperties: [eventProperty],
    otherProperties: [eventPropertySchemaField, uidProperty, userProperty],
    activeEventTable: 'event',
  }), [eventProperty, uidProperty, userProperty])
})

test('related properties exclude schema fields owned by other events and fields from other tables', () => {
  const eventOption = fieldOption({
    value: 'tracking-event:event.event:Login',
    field: 'event',
    kind: 'tracking-event',
    eventName: 'Login',
    eventTable: 'event',
  })
  const otherEventProperty = fieldOption({
    value: 'tracking-property:event.event:Purchase:order_id',
    field: 'order_id',
    kind: 'tracking-property',
    eventName: 'Purchase',
    sourceField: 'personal',
    jsonPath: '$.order_id',
  })
  const otherEventSchemaField = fieldOption({
    value: 'event.personal.order_id',
    field: 'personal.order_id',
    sourceField: 'personal',
    jsonPath: '$.order_id',
    isJsonSubfield: true,
  })
  const otherTableProperty = fieldOption({
    value: 'users.channel',
    table: 'users',
    field: 'channel',
  })

  assert.deepEqual(eventRelatedPropertyOptions({
    eventOption,
    eventProperties: [otherEventProperty],
    allEventProperties: [otherEventProperty],
    otherProperties: [otherEventSchemaField, otherTableProperty],
    activeEventTable: 'event',
  }), [])
})

test('property analysis exposes all public properties for an active event scope', () => {
  const eventProperty = fieldOption({
    value: 'tracking-property:event.event:Login:resolution',
    field: 'resolution',
    kind: 'tracking-property',
    eventName: 'Login',
  })
  const userProperty = fieldOption({
    value: 'event.userinfo.channel',
    field: 'userinfo.channel',
    sourceField: 'userinfo',
    jsonPath: '$.channel',
    isJsonSubfield: true,
  })
  const timeField = fieldOption({
    value: 'event.event_time',
    field: 'event_time',
    type: 'timestamp',
  })
  const uidProperty = fieldOption({
    label: '用户 ID',
    value: 'event.uid',
    field: 'uid',
  })

  assert.deepEqual(propertyAnalysisFieldOptions({
    eventScopeActive: true,
    builderFields: [eventProperty, userProperty, timeField],
    publicProperties: [userProperty, uidProperty],
  }), [userProperty, uidProperty])
})

test('property analysis retains datasource fields when event scope is inactive', () => {
  const field = fieldOption({
    value: 'orders.status',
    table: 'orders',
    field: 'status',
  })

  assert.deepEqual(propertyAnalysisFieldOptions({
    eventScopeActive: false,
    builderFields: [field],
    publicProperties: [],
  }), [field])
})

test('property analysis does not fall back when an event scope is configured but invalid', () => {
  const field = fieldOption({
    value: 'orders.status',
    table: 'orders',
    field: 'status',
  })

  assert.deepEqual(propertyAnalysisFieldOptions({
    eventScopeMode: 'event',
    eventScopeActive: false,
    builderFields: [field],
    publicProperties: [],
  }), [])
})
