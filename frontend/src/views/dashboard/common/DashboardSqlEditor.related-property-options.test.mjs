import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const editor = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const form = readFileSync(new URL('./DashboardAnalysisModelForm.vue', import.meta.url), 'utf8')

test('keeps related property options broader than event filter options', () => {
  const filterOptions = editor.match(/function eventFilterFieldOptions[\s\S]*?\n\}/)?.[0] || ''
  const relatedOptions = editor.match(/function relatedPropertyOptions[\s\S]*?\n\}/)?.[0] || ''

  assert.match(filterOptions, /eventScopedPropertyOptions/, '事件筛选必须继续使用受限筛选候选')
  assert.doesNotMatch(filterOptions, /otherProperties/, '事件筛选不得混入其他普通属性')
  assert.match(relatedOptions, /eventRelatedPropertyOptions/, '关联属性需要复用统一合并逻辑')
  assert.match(
    relatedOptions,
    /trackingEventPropertyOptionsByEvent/,
    '关联属性需要包含当前事件专属属性'
  )
  assert.match(
    relatedOptions,
    /allEventProperties: trackingEventPropertyOptions\.value/,
    '其他属性需要排除事件目录中任一事件的专属属性'
  )
  assert.match(
    relatedOptions,
    /otherProperties: builderFieldOptions\.value/,
    '关联属性需要从当前事件范围取得 uid、userinfo 等公共属性'
  )
})

test('uses complete related property options for retention, funnel, and interval analyses', () => {
  assert.match(
    editor,
    /function retentionPropertyOptions[\s\S]*?return relatedPropertyOptions\(eventValue\)/,
    '留存关联属性必须使用完整候选'
  )
  assert.match(
    editor,
    /function funnelPropertyOptions[\s\S]*?return retentionPropertyOptions\(eventValue\)/,
    '漏斗关联属性必须使用完整候选'
  )
  assert.match(
    editor,
    /intervalStartPropertyOptions = computed\(\(\) => relatedPropertyOptions/,
    '间隔起点关联属性必须使用完整候选'
  )
  assert.match(
    editor,
    /const intervalEndPropertyOptions = computed[\s\S]*?const options = relatedPropertyOptions/,
    '间隔终点关联属性必须使用完整候选'
  )
  assert.match(
    form,
    /:options="intervalStartPropertyOptions"[\s\S]*?mode="property"[\s\S]*?placeholder="起点事件属性"/,
    '间隔起点关联属性必须展示当前事件属性和公共属性'
  )
  assert.match(
    form,
    /:options="intervalEndPropertyOptions"[\s\S]*?mode="property"[\s\S]*?placeholder="终点事件属性"/,
    '间隔终点关联属性必须展示当前事件属性和公共属性'
  )
})
