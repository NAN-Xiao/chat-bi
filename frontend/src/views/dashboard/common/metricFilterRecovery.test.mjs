import assert from 'node:assert/strict'

const { metricFilterRecoveryCandidates } = await import('./metricFilterRecovery.ts')

const trackingEvent = {
  value: 'tracking-event:event.event:ShopBuyComplete',
  table: 'event',
  kind: 'tracking-event',
}
const eventProperty = {
  value: 'tracking-property:event.event:ShopBuyComplete:item_id',
  table: 'event',
  kind: 'tracking-property',
}
const userProperty = {
  value: 'event.userinfo.country',
  table: 'event',
}

assert.deepEqual(
  metricFilterRecoveryCandidates({
    metricField: trackingEvent.value,
    metricMeasureField: trackingEvent.value,
    metricFieldOption: trackingEvent,
    selectableFilterOptions: [eventProperty, userProperty],
    schemaFieldOptions: [
      { value: 'event.event', table: 'event' },
      userProperty,
    ],
  }),
  [eventProperty.value, userProperty.value],
  '事件指标只能从当前可选属性恢复筛选，不能把隐式事件名条件恢复成普通筛选'
)

assert.deepEqual(
  metricFilterRecoveryCandidates({
    metricField: 'orders.amount',
    metricMeasureField: 'orders.order_id',
    metricFieldOption: { value: 'orders.amount', table: 'orders' },
    selectableFilterOptions: [],
    schemaFieldOptions: [
      { value: 'orders.amount', table: 'orders' },
      { value: 'orders.channel', table: 'orders' },
      { value: 'users.country', table: 'users' },
    ],
  }),
  ['orders.amount', 'orders.order_id', 'orders.channel'],
  '普通数据源仍应保留指标字段、计算字段和同表字段的 SQL 筛选恢复能力'
)

console.log('dashboard metric filter recovery tests passed')
