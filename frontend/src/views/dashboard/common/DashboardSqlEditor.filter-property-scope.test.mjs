import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const editor = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const tree = readFileSync(new URL('./BuilderFilterTree.vue', import.meta.url), 'utf8')

assert.match(editor, /import \{ datasourceApi \} from '@\/api\/datasource'/, '看板需要复用数据源字段接口')
assert.match(editor, /datasourceApi\.fieldList\(/, '默认事件表需要加载权限受控字典字段')
assert.match(editor, /fieldList\(table\.id, \{\s*fieldName: ''/, '字段接口请求必须传入字段名，避免后端参数校验失败')
assert.match(editor, /source_field|sourceField/, '字段合并需要保留 JSON 宿主字段')
assert.match(editor, /json_path|jsonPath/, '字段合并需要保留 JSON 路径')

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

const metricFilterRecovery = editor.match(/function recoverMissingMetricFiltersFromSql[\s\S]*?\n\}/)?.[0] || ''
assert.match(
  metricFilterRecovery,
  /metricFilterRecoveryCandidates\([\s\S]*selectableFilterOptions: metricFilterFieldOptions\(item\)/,
  'SQL 回填指标筛选必须复用当前合法筛选候选，不能把事件标识恢复成普通筛选'
)
assert.doesNotMatch(
  metricFilterRecovery,
  /const candidates = unique\(\[\s*item\.field/,
  'SQL 回填不得直接把事件指标字段作为筛选候选'
)

assert.match(tree, /pickerMode\?: 'property' \| 'filter-property'/, '筛选树需要透传字段选择器模式')
assert.match(tree, /filterPropertyTabs\?: Array<'all' \| 'event' \| 'user'>/, '筛选树需要透传允许标签')
assert.match(tree, /:filter-property-tabs="filterPropertyTabs"/, '递归筛选树必须保留允许标签')

const metricFilterTabBindings = editor.match(/:filter-property-tabs="\['all', 'event', 'user'\]"/g) || []
assert.equal(metricFilterTabBindings.length, 2, '指标筛选和公式指标筛选都需要全部、事件、用户三个标签')
assert.match(editor, /:filter-property-tabs="\['user'\]"/, '全局筛选只能显示用户属性')
assert.match(editor, /:field-options="eventUserPropertyOptions"/, '全局筛选候选只能使用 event.userinfo')
assert.match(editor, /function builderFilterScopeIssues\(\)/, '旧配置需要独立筛选范围校验')
assert.match(editor, /字段不属于当前筛选范围/, '失效字段需要明确错误信息')
assert.match(editor, /builderBlockingScopeIssues\(\)/, 'SQL 生成前需要合并事件范围和筛选范围错误')

console.log('dashboard SQL editor filter property scope tests passed')
