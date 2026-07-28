import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const editor = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const tree = readFileSync(new URL('./BuilderFilterTree.vue', import.meta.url), 'utf8')

assert.match(editor, /const eventUserPropertyOptions = computed\(\(\) =>/, '编辑器需要独立的 event.userinfo 候选')
assert.match(editor, /isEventUserPropertyOption\(option, 'event'\)/, '用户属性必须严格限定 event 表')

const metricOptions = editor.match(/function metricFilterFieldOptions[\s\S]*?\n\}/)?.[0] || ''
assert.match(metricOptions, /trackingEventPropertyOptionsByEvent/, '指标筛选需要当前事件参数')
assert.match(metricOptions, /eventUserPropertyOptions\.value/, '指标筛选需要 event.userinfo 用户属性')
assert.match(
  metricOptions,
  /\(eventOption\.eventTable \|\| eventOption\.table\) !== 'event'/,
  '指标筛选事件属性必须严格限定 event 表'
)
assert.doesNotMatch(metricOptions, /eventDetailFieldOptions/, '指标筛选不得混入事件公共物理字段')

assert.match(tree, /pickerMode\?: 'property' \| 'filter-property'/, '筛选树需要透传字段选择器模式')
assert.match(tree, /filterPropertyTabs\?: Array<'event' \| 'user'>/, '筛选树需要透传允许标签')
assert.match(tree, /:filter-property-tabs="filterPropertyTabs"/, '递归筛选树必须保留允许标签')

assert.match(editor, /:filter-property-tabs="\['event', 'user'\]"/, '指标筛选需要两个属性标签')
assert.match(editor, /:filter-property-tabs="\['user'\]"/, '全局筛选只能显示用户属性')
assert.match(editor, /:field-options="eventUserPropertyOptions"/, '全局筛选候选只能使用 event.userinfo')
assert.match(editor, /function builderFilterScopeIssues\(\)/, '旧配置需要独立筛选范围校验')
assert.match(editor, /字段不属于当前筛选范围/, '失效字段需要明确错误信息')
assert.match(editor, /builderBlockingScopeIssues\(\)/, 'SQL 生成前需要合并事件范围和筛选范围错误')

console.log('dashboard SQL editor filter property scope tests passed')
