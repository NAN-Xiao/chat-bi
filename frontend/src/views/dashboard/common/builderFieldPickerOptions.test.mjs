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
