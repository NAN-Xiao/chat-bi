import assert from 'node:assert/strict'

const options = await import('./builderFieldPickerOptions.ts')

assert.equal(
  options.fieldOptionDisplayName({
    label: 'adinfo.adId',
    value: 'event.adinfo.adId',
    table: 'event',
    field: 'adinfo.adId',
    displayName: '广告 ID',
    sourceField: 'adinfo',
    jsonPath: '$.adId',
    isJsonSubfield: true,
  }),
  '广告 ID',
  'JSON 子字段应优先显示显式业务名称'
)

assert.equal(
  options.fieldOptionDisplayName({
    label: 'adinfo.adId',
    value: 'event.adinfo.adId',
    table: 'event',
    field: 'adinfo.adId',
    sourceField: 'adinfo',
    jsonPath: '$.adId',
    isJsonSubfield: true,
  }),
  'adId',
  'JSON 子字段没有显示名时应显示叶子属性名'
)

assert.equal(
  options.fieldOptionDisplayName({
    label: '业务日期（分区字段）',
    value: 'event.dt',
    table: 'event',
    field: 'dt',
  }),
  '业务日期（分区字段）',
  '普通字段继续使用现有 label'
)

assert.equal(
  options.isSelectableFieldOption({
    label: '用户画像字段',
    value: 'user.country',
    table: 'user',
    tableRole: 'daily_user_snapshot',
    field: 'country',
    type: 'varchar',
  }),
  false,
  '对象组/用户快照表里的字段不应出现在字段选择器和表 tab 中'
)

assert.equal(
  options.isSelectableFieldOption({
    label: '事件名',
    value: 'event.event',
    table: 'event',
    tableRole: 'event_fact',
    field: 'event',
    type: 'varchar',
  }),
  true,
  '事件明细表字段应继续展示'
)

assert.equal(
  options.isSelectableFieldOption({
    label: 'JSON 叶子字段',
    value: 'event.ext.level',
    table: 'event',
    tableRole: 'event_fact',
    field: 'ext.level',
    type: 'number',
    semanticType: 'number',
    sourceField: 'ext',
    jsonPath: '$.level',
    isJsonSubfield: true,
  }),
  true,
  'JSON 叶子字段不是对象组容器，应继续展示'
)

assert.equal(
  options.isNumericFieldOption({
    label: '金额',
    value: 'event.personal.money',
    table: 'event',
    field: 'personal.money',
    semanticType: '数值',
  }),
  true,
  '中文数值语义类型应可用于数值聚合'
)

assert.equal(
  options.isNumericFieldOption({
    label: '用户标识',
    value: 'event.uid',
    table: 'event',
    field: 'uid',
    category: '文本',
  }),
  false,
  '中文文本类别不能被当作数值字段'
)

assert.equal(
  options.isTimeFieldOption({
    label: '事件日期',
    value: 'event.dt',
    table: 'event',
    field: 'dt',
    propertyType: '日期',
  }),
  true,
  '中文日期属性类型应作为时间范围字段'
)

assert.equal(
  options.preferredBuilderTimeField(
    [
      {
        label: '事件写入时间戳',
        value: 'event.time',
        table: 'event',
        field: 'time',
        type: 'bigint',
        semanticType: 'timestamp_ms',
        comment: '事件精确发生时间；业务日期或按自然日统计优先使用 dt。',
      },
      {
        label: '业务日期（分区字段）',
        value: 'event.dt',
        table: 'event',
        field: 'dt',
        type: 'bigint',
        category: 'time',
        semanticType: 'date',
      },
    ].filter(options.isTimeFieldOption)
  ),
  'event.dt',
  '新图表的时间范围应优先选择业务日期或分区日期字段'
)

assert.equal(
  options.preferredBuilderTimeField([
    {
      label: '创建时间',
      value: 'event.created_at',
      table: 'event',
      field: 'created_at',
      type: 'timestamp',
    },
    {
      label: '事件日期',
      value: 'event.event_date',
      table: 'event',
      field: 'event_date',
      type: 'date',
    },
  ]),
  'event.event_date',
  '没有业务日期或分区日期字段时应继续优先选择事件日期'
)

const trackingProperty = {
  label: '获得金币',
  value: 'tracking-property:event.event:ResourceChange:gold',
  table: 'event',
  field: 'gold',
  kind: 'tracking-property',
  eventName: 'ResourceChange',
  sourceField: 'personal',
  jsonPath: '$.gold',
  isJsonSubfield: true,
}

assert.equal(
  options.isTrackingEventPropertyOption(trackingProperty),
  true,
  'tracking-property 应识别为事件属性'
)

const eventUserProperty = {
  label: '国家',
  value: 'event.userinfo.country',
  table: 'event',
  field: 'userinfo.country',
  sourceField: 'userinfo',
  jsonPath: '$.country',
  expression: "JSON_UNQUOTE(JSON_EXTRACT(`event`.`userinfo`, '$.country'))",
  isJsonSubfield: true,
  type: 'text',
}

assert.equal(
  options.isEventPublicPropertyOption(eventUserProperty),
  true,
  'event.userinfo JSON 叶子字段应识别为公共属性'
)
assert.equal(
  options.isEventPublicPropertyOption({ ...eventUserProperty, table: 'user', value: 'user.userinfo.country' }),
  false,
  'user 表的 userinfo 字段不得进入事件公共属性'
)
assert.equal(
  options.isEventPublicPropertyOption({ ...eventUserProperty, sourceField: 'personal', value: 'event.personal.country' }),
  true,
  '其他事件公共 JSON 宿主列的叶子字段也应进入公共属性'
)
assert.equal(
  options.isEventPublicPropertyOption({ ...eventUserProperty, jsonPath: '', isJsonSubfield: false, field: 'userinfo', type: 'json' }),
  false,
  'userinfo 容器本身不得识别为可筛选公共属性'
)
assert.equal(
  options.isEventPublicPropertyOption(trackingProperty),
  false,
  '事件目录参数不得重复进入公共属性'
)

const eventUid = {
  label: '用户 ID',
  value: 'event.uid',
  table: 'event',
  field: 'uid',
  type: 'text',
}
assert.equal(options.isEventPublicPropertyOption(eventUid), true, 'event.uid 应识别为公共属性')
assert.deepEqual(
  options.eventPublicPropertyOptions({
    fields: [eventUid, eventUserProperty, { ...trackingProperty, kind: undefined, value: 'event.personal.gold', field: 'personal.gold' }],
    eventProperties: [trackingProperty],
    activeEventTable: 'event',
  }).map((item) => item.value),
  ['event.uid', 'event.userinfo.country'],
  '公共属性候选应保留 uid 和 userinfo 叶子，并排除事件专属参数'
)
