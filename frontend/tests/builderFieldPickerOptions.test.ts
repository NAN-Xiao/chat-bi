import assert from 'node:assert/strict'
import test from 'node:test'

import {
  eventScopedPropertyOptions,
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
    userProperties: [userProperty],
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
    userProperties: [duplicate],
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
    userProperties: [fieldOption({})],
    activeEventTable: 'event',
  }), [])
})
