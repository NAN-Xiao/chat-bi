import assert from 'node:assert/strict'

const options = await import('./builderFieldPickerOptions.ts')

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
