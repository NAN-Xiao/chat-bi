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
