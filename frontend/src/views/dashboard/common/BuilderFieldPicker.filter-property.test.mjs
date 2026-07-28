import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./BuilderFieldPicker.vue', import.meta.url), 'utf8')

assert.match(source, /type PickerMode = [^\n]*'filter-property'/, '字段选择器需要筛选属性模式')
assert.match(source, /filterPropertyTabs\?: FilterPropertyTab\[\]/, '调用方需要显式控制可见属性标签')
assert.match(source, /label: '事件属性'/, '筛选属性模式需要事件属性标签')
assert.match(source, /label: '用户属性'/, '筛选属性模式需要用户属性标签')
assert.match(source, /isTrackingEventPropertyOption\(item\)/, '事件属性标签只能匹配事件目录参数')
assert.match(source, /isEventUserPropertyOption\(item\)/, '用户属性标签只能匹配 event.userinfo JSON 字段')
assert.match(
  source,
  /const rows = isFilterPropertyMode\.value[\s\S]*?\? tabRows/,
  '当前属性标签为空时不得回退显示其他标签字段'
)
assert.match(source, /\{ immediate: true \}/, '筛选属性模式首次打开需要立即选择第一个允许标签')
assert.match(source, /暂无事件属性/, '事件属性空列表需要明确空状态')
assert.match(source, /暂无用户属性/, '用户属性空列表需要明确空状态')

const activeStyle = source.match(/\.builder-field-picker-tabs button\.active\s*\{([\s\S]*?)\n\}/)
assert.ok(activeStyle, '属性标签需要活动态样式')
assert.match(activeStyle[1], /border-color:\s*#315cff/, '活动标签需要蓝色底部指示线')
assert.match(activeStyle[1], /color:\s*#1f2633/, '活动标签文字使用深色，不使用蓝色按钮文字')

console.log('builder field picker filter property tests passed')
