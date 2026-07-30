# 仪表盘筛选事件属性与用户属性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将仪表盘指标筛选区分为事件属性和用户属性，并将全局筛选严格限制为 `event.userinfo` 的已配置 JSON 子字段。

**Architecture:** 复用现有 `FieldOption`、跟踪事件目录和 Schema JSON 元数据，在前端用纯函数完成字段分类，由现有字段选择器增加筛选属性标签模式。`DashboardSqlEditor` 负责按当前事件组装指标筛选候选、按 `event.userinfo` 组装全局筛选候选，并在 SQL 生成前对旧配置执行失败关闭校验；后端继续使用字段对象中的 JSON 表达式，并补齐全局 JSON 字段映射校验和提示词约束。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Node.js `assert` 测试、Python 3、pytest、FastAPI 后端 SQL 生成器。

## Global Constraints

- 指标内筛选显示“事件属性”和“用户属性”两个标签。
- 全局筛选只显示“用户属性”，不渲染、禁用或预留“事件属性”。
- 事件属性只来自当前指标所选事件的跟踪事件目录叶子参数。
- 用户属性只来自已授权的 `event.userinfo` 已配置 JSON 叶子字段。
- 不读取 `user` 表，不展示 `uid`、`dt`、`event` 等事件公共物理字段，不扫描 JSON 样本。
- 不新增数据库字段、后端属性目录接口或持久化的属性类型状态。
- 不静默替换、删除或跨表回退旧配置中的失效字段。
- 代码注释、校验提示和 Git 提交信息使用中文。

---

## File Structure

- `frontend/src/views/dashboard/common/builderFieldPickerOptions.ts`：提供事件属性和 `event.userinfo` 用户属性的结构化分类纯函数。
- `frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`：验证分类边界和容器字段排除规则。
- `frontend/src/views/dashboard/common/BuilderFieldPicker.vue`：增加筛选属性标签模式、标签内搜索和空状态。
- `frontend/src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs`：验证标签文案、样式和筛选模式结构。
- `frontend/src/views/dashboard/common/BuilderFilterTree.vue`：递归透传筛选选择器模式和允许展示的标签。
- `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：组装指标/全局筛选候选，并在 SQL 生成前校验字段范围。
- `frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`：验证候选范围、两类筛选差异和失效配置阻断。
- `backend/apps/dashboard/crud/ai_sql_generator.py`：校验全局 JSON 筛选字段映射，并明确 `event.userinfo` SQL 生成约束。
- `backend/tests/test_dashboard_ai_sql_generator.py`：验证全局 JSON 映射失败关闭和提示词约束。

### Task 1: 建立筛选属性分类纯函数

**Files:**
- Modify: `frontend/src/views/dashboard/common/builderFieldPickerOptions.ts:1-189`
- Test: `frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`

**Interfaces:**
- Consumes: 现有 `FieldOption`、`isSelectableFieldOption(option)`。
- Produces: `isTrackingEventPropertyOption(option: FieldOption): boolean` 和 `isEventUserPropertyOption(option: FieldOption, eventTable?: string): boolean`。

- [ ] **Step 1: 写入失败测试**

在 `builderFieldPickerOptions.test.mjs` 末尾加入以下断言：

```javascript
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
  options.isEventUserPropertyOption(eventUserProperty),
  true,
  'event.userinfo JSON 叶子字段应识别为用户属性'
)
assert.equal(
  options.isEventUserPropertyOption({ ...eventUserProperty, table: 'user', value: 'user.userinfo.country' }),
  false,
  'user 表的 userinfo 字段不得进入筛选用户属性'
)
assert.equal(
  options.isEventUserPropertyOption({ ...eventUserProperty, sourceField: 'personal', value: 'event.personal.country' }),
  false,
  '其他 JSON 宿主列不得识别为用户属性'
)
assert.equal(
  options.isEventUserPropertyOption({ ...eventUserProperty, jsonPath: '', isJsonSubfield: false }),
  false,
  'userinfo 容器本身不得识别为可筛选用户属性'
)
assert.equal(
  options.isEventUserPropertyOption(trackingProperty),
  false,
  '事件目录参数不得重复进入用户属性'
)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run：

```powershell
cd frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
```

Expected：FAIL，错误包含 `options.isTrackingEventPropertyOption is not a function`。

- [ ] **Step 3: 写入最小实现**

在 `builderFieldPickerOptions.ts` 的 `isSelectableFieldOption` 后加入：

```typescript
export function isTrackingEventPropertyOption(option: FieldOption) {
  return option.kind === 'tracking-property' && isSelectableFieldOption(option)
}

export function isEventUserPropertyOption(option: FieldOption, eventTable = 'event') {
  return (
    option.kind !== 'tracking-property' &&
    option.table === eventTable &&
    normalizeRole(option.sourceField) === 'userinfo' &&
    Boolean(String(option.jsonPath || '').trim()) &&
    isSelectableFieldOption(option)
  )
}
```

这里显式排除 `tracking-property`，防止某个事件参数恰好以 `userinfo` 为宿主时同时出现在两个标签中。

- [ ] **Step 4: 运行测试并确认通过**

Run：

```powershell
cd frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
```

Expected：PASS，并输出 `builder field picker option tests passed`。

- [ ] **Step 5: 提交分类函数**

```powershell
git add frontend/src/views/dashboard/common/builderFieldPickerOptions.ts frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs
git commit -m "新增筛选属性分类规则"
```

### Task 2: 在字段选择器中实现属性标签模式

**Files:**
- Modify: `frontend/src/views/dashboard/common/BuilderFieldPicker.vue:1-650`
- Create: `frontend/src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs`

**Interfaces:**
- Consumes: Task 1 的 `isTrackingEventPropertyOption`、`isEventUserPropertyOption`。
- Produces: `PickerMode` 新值 `filter-property`，以及 prop `filterPropertyTabs: Array<'event' | 'user'>`。

- [ ] **Step 1: 创建失败测试**

创建 `BuilderFieldPicker.filter-property.test.mjs`：

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./BuilderFieldPicker.vue', import.meta.url), 'utf8')

assert.match(source, /type PickerMode = [^\n]*'filter-property'/, '字段选择器需要筛选属性模式')
assert.match(source, /filterPropertyTabs\?: FilterPropertyTab\[\]/, '调用方需要显式控制可见属性标签')
assert.match(source, /label: '事件属性'/, '筛选属性模式需要事件属性标签')
assert.match(source, /label: '用户属性'/, '筛选属性模式需要用户属性标签')
assert.match(source, /isTrackingEventPropertyOption\(item\)/, '事件属性标签只能匹配事件目录参数')
assert.match(source, /isEventUserPropertyOption\(item\)/, '用户属性标签只能匹配 event.userinfo JSON 字段')
assert.match(source, /isFilterPropertyMode\.value \? tabRows : keywordRows/, '当前属性标签为空时不得回退显示其他标签字段')
assert.match(source, /\{ immediate: true \}/, '筛选属性模式首次打开需要立即选择第一个允许标签')
assert.match(source, /暂无事件属性/, '事件属性空列表需要明确空状态')
assert.match(source, /暂无用户属性/, '用户属性空列表需要明确空状态')

const activeStyle = source.match(/\.builder-field-picker-tabs button\.active\s*\{([\s\S]*?)\n\}/)
assert.ok(activeStyle, '属性标签需要活动态样式')
assert.match(activeStyle[1], /border-color:\s*#315cff/, '活动标签需要蓝色底部指示线')
assert.match(activeStyle[1], /color:\s*#1f2633/, '活动标签文字使用深色，不使用蓝色按钮文字')

console.log('builder field picker filter property tests passed')
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run：

```powershell
cd frontend
node src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs
```

Expected：FAIL，首个错误为“字段选择器需要筛选属性模式”。

- [ ] **Step 3: 扩展选择器类型和 props**

将导入和类型定义调整为：

```typescript
import {
  fieldOptionDisplayName,
  isEventUserPropertyOption,
  isNumericFieldOption,
  isSelectableFieldOption,
  isTimeFieldOption,
  isTrackingEventPropertyOption,
} from './builderFieldPickerOptions'

type PickerMode = 'field' | 'property' | 'metric' | 'time' | 'tracking-event' | 'filter-property'
type FilterPropertyTab = 'event' | 'user'
```

在 props 中加入：

```typescript
filterPropertyTabs?: FilterPropertyTab[]
```

在默认值中加入：

```typescript
filterPropertyTabs: () => [],
```

并在 `isTrackingEventMode` 后加入：

```typescript
const isFilterPropertyMode = computed(() => props.mode === 'filter-property')
```

- [ ] **Step 4: 实现标签、过滤和空状态**

用以下实现替换 `tabOptions`：

```typescript
const filterPropertyTabOptions: Array<{ label: string; value: FilterPropertyTab }> = [
  { label: '事件属性', value: 'event' },
  { label: '用户属性', value: 'user' },
]

const tabOptions = computed(() => {
  if (isFilterPropertyMode.value) {
    return filterPropertyTabOptions.filter((item) => props.filterPropertyTabs.includes(item.value))
  }
  return [
    { label: '全部', value: 'all' },
    ...tableTabs.value,
  ]
})
```

在 `matchesTab` 开头加入：

```typescript
if (isFilterPropertyMode.value && tab === 'event') {
  return isTrackingEventPropertyOption(item)
}
if (isFilterPropertyMode.value && tab === 'user') {
  return isEventUserPropertyOption(item)
}
```

将 `groupedOptions` 中的 rows 选择改为：

```typescript
const rows = isFilterPropertyMode.value
  ? tabRows
  : tabRows.length > 0 || tab === 'all' || tab.startsWith(TABLE_TAB_PREFIX)
    ? tabRows
    : keywordRows
```

这样当前属性标签没有匹配项时只显示该标签的空状态，不会把另一个标签中的字段混进来。

将 `groupedOptions` 中的分组 key 改为：

```typescript
const key = isFilterPropertyMode.value
  ? filterPropertyTabOptions.find((item) => item.value === tab)?.label || '筛选属性'
  : tableTabLabel(item.table || '字段', item.tableLabel || item.tableComment, optionTableReferenceLabel(item))
```

新增空状态计算：

```typescript
const propertyEmptyText = computed(() => (
  activeTab.value === 'event' ? '暂无事件属性' : '暂无用户属性'
))
```

将通用列表分支中的空状态替换为：

```vue
<div v-else-if="groupedOptions.length === 0" class="builder-field-picker-empty">
  {{ isFilterPropertyMode ? propertyEmptyText : '暂无数据' }}
</div>
```

现有 watcher 会在标签集合变化时选择第一个允许标签，因此指标筛选默认进入“事件属性”，全局筛选默认进入“用户属性”。

同时给监听 `props.mode` 和 `tabOptions` 的 watcher 增加立即执行选项：

```typescript
watch(
  () => [props.mode, tabOptions.value.map((item) => item.value).join('|')],
  () => {
    if (!tabOptions.value.some((item) => item.value === activeTab.value)) {
      activeTab.value = tabOptions.value[0]?.value || 'all'
    }
  },
  { immediate: true }
)
```

- [ ] **Step 5: 调整活动标签样式并运行测试**

将活动标签样式改为：

```less
.builder-field-picker-tabs button.active {
  border-color: #315cff;
  color: #1f2633;
  font-weight: 600;
}
```

Run：

```powershell
cd frontend
node src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs
node src/views/dashboard/common/BuilderFieldPicker.style.test.mjs
```

Expected：两条命令均 PASS。

- [ ] **Step 6: 提交选择器模式**

```powershell
git add frontend/src/views/dashboard/common/BuilderFieldPicker.vue frontend/src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs
git commit -m "实现筛选属性标签选择器"
```

### Task 3: 接入指标筛选、全局筛选和失效配置校验

**Files:**
- Modify: `frontend/src/views/dashboard/common/BuilderFilterTree.vue:1-180`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:1-5039`
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

**Interfaces:**
- Consumes: Task 1 分类函数和 Task 2 的 `mode="filter-property"`、`filterPropertyTabs`。
- Produces: `eventUserPropertyOptions`、严格的 `metricFilterFieldOptions(item)`、`builderFilterScopeIssues()`。

- [ ] **Step 1: 创建失败测试**

创建 `DashboardSqlEditor.filter-property-scope.test.mjs`：

```javascript
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const editor = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const tree = readFileSync(new URL('./BuilderFilterTree.vue', import.meta.url), 'utf8')

assert.match(editor, /const eventUserPropertyOptions = computed\(\(\) =>/, '编辑器需要独立的 event.userinfo 候选')
assert.match(editor, /isEventUserPropertyOption\(option, 'event'\)/, '用户属性必须严格限定 event 表')

const metricOptions = editor.match(/function metricFilterFieldOptions[\s\S]*?\n\}/)?.[0] || ''
assert.match(metricOptions, /trackingEventPropertyOptionsByEvent/, '指标筛选需要当前事件参数')
assert.match(metricOptions, /eventUserPropertyOptions\.value/, '指标筛选需要 event.userinfo 用户属性')
assert.match(metricOptions, /eventOption\.eventTable \|\| eventOption\.table\) !== 'event'/, '指标筛选事件属性必须严格限定 event 表')
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
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run：

```powershell
cd frontend
node src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
```

Expected：FAIL，首个错误为“编辑器需要独立的 event.userinfo 候选”。

- [ ] **Step 3: 让筛选树透传选择器模式**

将 `BuilderFilterTree.vue` 的本地 `FieldOption` 声明替换为：

```typescript
import type { FieldOption } from './builderFieldPickerOptions'
```

在 props 中加入：

```typescript
pickerMode?: 'property' | 'filter-property'
filterPropertyTabs?: Array<'event' | 'user'>
```

默认值加入：

```typescript
pickerMode: 'property',
filterPropertyTabs: () => [],
```

递归 `BuilderFilterTree` 加入：

```vue
:picker-mode="pickerMode"
:filter-property-tabs="filterPropertyTabs"
```

规则行中的 `BuilderFieldPicker` 改为：

```vue
<BuilderFieldPicker
  v-model="node.field"
  class="builder-field-select"
  :mode="pickerMode"
  :options="fieldOptions"
  :filter-property-tabs="filterPropertyTabs"
  :loading="schemaLoading"
  placeholder="字段"
/>
```

- [ ] **Step 4: 组装严格的用户属性和指标筛选候选**

在 `DashboardSqlEditor.vue` 的字段选项导入中加入 `isEventUserPropertyOption`。

在 `builderFieldOptions` 后加入：

```typescript
const eventUserPropertyOptions = computed(() =>
  builderFieldOptions.value.filter((option) => isEventUserPropertyOption(option, 'event'))
)
```

将 `metricFilterFieldOptions` 替换为：

```typescript
function metricFilterFieldOptions(item: SqlBuilderMetricItem) {
  const eventOption = fieldOptionByValue(item.field)
  if (
    eventOption?.kind !== 'tracking-event' ||
    !eventOption.eventName ||
    (eventOption.eventTable || eventOption.table) !== 'event'
  ) {
    return []
  }
  const options = [
    ...(trackingEventPropertyOptionsByEvent.value.get(eventOption.eventName) || []),
    ...eventUserPropertyOptions.value,
  ]
  return Array.from(new Map(options.map((option) => [option.value, option])).values())
}
```

保留 `metricMeasureFieldOptions` 对 `eventDetailFieldOptions` 的使用，因为本需求只收紧筛选字段，不改变求和、平均值等计算字段候选。

- [ ] **Step 5: 接入指标和全局筛选标签**

普通指标和公式原子指标的 `BuilderFilterTree` 均加入：

```vue
picker-mode="filter-property"
:filter-property-tabs="['event', 'user']"
```

全局筛选的 `BuilderFilterTree` 改为：

```vue
<BuilderFilterTree
  :nodes="sqlBuilder.globalFilters"
  :logic="sqlBuilder.globalFilterLogic"
  :field-options="eventUserPropertyOptions"
  :operator-options="builderFilterOperatorOptions"
  :schema-loading="schemaLoading"
  picker-mode="filter-property"
  :filter-property-tabs="['user']"
  :show-toolbar="false"
  empty-text="暂无全局筛选"
  @update:logic="sqlBuilder.globalFilterLogic = $event"
/>
```

- [ ] **Step 6: 增加失效字段失败关闭校验**

在 `builderEventScopeIssues` 后加入：

```typescript
function appendFilterRangeIssues(
  filters: SqlBuilderFilter[],
  allowedOptions: SchemaFieldOption[],
  prefix: string,
  issues: string[]
) {
  const allowedValues = new Set(
    allowedOptions.flatMap((option) => [option.value, option.field]).filter(Boolean)
  )
  filterFieldValues(filters).forEach((field, index) => {
    if (!allowedValues.has(field)) {
      issues.push(`${prefix}[${index}].field：字段 ${field} 不属于当前筛选范围。`)
    }
  })
}

function builderFilterScopeIssues() {
  if (eventFieldScope.value.status !== 'active') {
    return []
  }
  const issues: string[] = []
  sqlBuilder.metricItems.forEach((item, index) => {
    appendFilterRangeIssues(item.filters || [], metricFilterFieldOptions(item), `metric[${index}].filter`, issues)
  })
  sqlBuilder.calculatedMetrics.forEach((item, formulaIndex) => {
    item.tokens.forEach((token, tokenIndex) => {
      if (token.type !== 'atomicMetric') return
      appendFilterRangeIssues(
        (token.metric.filters || []) as SqlBuilderFilter[],
        metricFilterFieldOptions(token.metric as SqlBuilderMetricItem),
        `formula[${formulaIndex}].token[${tokenIndex}].filter`,
        issues
      )
    })
  })
  appendFilterRangeIssues(sqlBuilder.globalFilters, eventUserPropertyOptions.value, 'global_filter', issues)
  return unique(issues)
}

function builderBlockingScopeIssues() {
  return unique([...builderEventScopeIssues(), ...builderFilterScopeIssues()])
}
```

将 `collectLocalBuilderConfigIssues` 和 `generateBuilderAiSql` 中读取 `builderEventScopeIssues()` 的位置改为 `builderBlockingScopeIssues()`。现有提示面板和阻断流程保持不变，从而让旧配置保留原值并显示明确错误。

- [ ] **Step 7: 运行前端聚焦测试**

Run：

```powershell
cd frontend
node src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
node src/views/dashboard/common/BuilderFilterTree.events.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

Expected：四条命令均 PASS。

- [ ] **Step 8: 提交前端接入**

```powershell
git add frontend/src/views/dashboard/common/BuilderFilterTree.vue frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
git commit -m "接入指标和全局筛选属性范围"
```

### Task 4: 补齐后端 JSON 校验和 SQL 生成约束

**Files:**
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py:1105-1125,1328-1337`
- Modify: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Consumes: 前端序列化的筛选字段对象 `table/sourceField/jsonPath/expression`。
- Produces: 全局 JSON 筛选字段映射完整性错误，以及明确禁止将 `event.userinfo` 改写到 `user` 表的 SQL 提示词。

- [ ] **Step 1: 写入失败测试**

在 `test_dashboard_ai_sql_generator.py` 加入：

```python
def test_global_json_filter_requires_complete_mapping() -> None:
    normalized = {
        "time": {},
        "metrics": [],
        "formula_metrics": [],
        "groups": [],
        "filters": {
            "logic": "and",
            "rules": [
                {
                    "field": {
                        "table": "event",
                        "field": "userinfo.country",
                        "sourceField": "userinfo",
                        "jsonPath": "$.country",
                        "isJsonSubfield": True,
                    },
                    "operator": "eq",
                    "value": "US",
                }
            ],
        },
    }

    issues = ai_sql_generator._configured_field_permission_issues(
        normalized,
        allowed_tables=["event"],
        allowed_fields_by_table={"event": {"userinfo"}},
    )

    assert any("全局筛选1 的 JSON 字段映射不完整" in item for item in issues)
    assert any("expression" in item for item in issues)


def test_dashboard_prompt_keeps_user_properties_on_event_userinfo() -> None:
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            title="按国家统计活跃",
            chart_type="table",
            context={
                "time": {"field": {"table": "event", "field": "dt"}, "grain": "day", "range": "30d"},
                "metrics": [{"field": {"kind": "tracking-event", "table": "event", "field": "event", "eventName": "UserActive"}, "aggregation": "count"}],
                "groups": [],
                "filters": {
                    "logic": "and",
                    "rules": [{
                        "field": {
                            "table": "event",
                            "field": "userinfo.country",
                            "sourceField": "userinfo",
                            "jsonPath": "$.country",
                            "expression": "JSON_UNQUOTE(JSON_EXTRACT(`event`.`userinfo`, '$.country'))",
                        },
                        "operator": "eq",
                        "value": "US",
                    }],
                },
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "全局筛选只允许使用 context.filters 中提供的 event.userinfo JSON 子字段" in prompt
    assert "不得把用户属性改为 user 表" in prompt
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_ai_sql_generator.py -k "global_json_filter or keeps_user_properties" -q
```

Expected：2 failed；第一个测试没有返回 JSON 映射错误，第二个测试缺少提示词文本。

- [ ] **Step 3: 增加全局 JSON 字段映射校验**

在 `_configured_field_permission_issues` 的全局筛选循环中加入：

```python
for index, field in enumerate(_iter_filter_rule_fields(normalized_config.get("filters"))):
    label = f"全局筛选{index + 1}"
    issues.extend(_json_subfield_mapping_issues(field, label))
    issues.extend(_field_table_permission_issues(field, label, allowed_tables))
    issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))
```

这一步只补齐结构化 JSON 映射校验，不从字段名推断或修复配置。

- [ ] **Step 4: 增加明确的筛选属性 SQL 约束**

在 `_dashboard_config_prompt` 的筛选规则段加入：

```python
"筛选属性范围：指标内筛选可使用当前事件的 tracking-property 事件属性，或字段对象明确提供的 event.userinfo JSON 用户属性。",
"全局筛选只允许使用 context.filters 中提供的 event.userinfo JSON 子字段；必须使用字段对象的 expression，不得把用户属性改为 user 表或其他表的同名字段。",
```

保留现有“不得自行改写 JSON 宿主列或路径”规则，使事件属性和用户属性都使用配置表达式。

- [ ] **Step 5: 运行后端聚焦测试**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_ai_sql_generator.py -k "global_json_filter or keeps_user_properties or tracking_event or json_subfield" -q
```

Expected：选中的测试全部 PASS。

- [ ] **Step 6: 提交后端约束**

```powershell
git add backend/apps/dashboard/crud/ai_sql_generator.py backend/tests/test_dashboard_ai_sql_generator.py
git commit -m "强化筛选属性SQL生成约束"
```

### Task 5: 完成回归验证和交付检查

**Files:**
- Verify only: 本计划涉及的前端、后端和测试文件。

**Interfaces:**
- Consumes: Task 1-4 的完整实现。
- Produces: 可交付的测试证据和干净的变更检查结果。

- [ ] **Step 1: 运行全部相关前端测试**

Run：

```powershell
cd frontend
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
node src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs
node src/views/dashboard/common/BuilderFieldPicker.style.test.mjs
node src/views/dashboard/common/BuilderFilterTree.events.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

Expected：七条命令全部 PASS，且无未处理异常堆栈。

- [ ] **Step 2: 运行前端类型与构建检查**

Run：

```powershell
cd frontend
npm run build
```

Expected：退出码 0；`vue-tsc -b` 和 Vite build 均成功。

- [ ] **Step 3: 运行后端聚焦回归**

Run：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_ai_sql_generator.py -q
```

Expected：该测试文件全部 PASS。

- [ ] **Step 4: 检查最终差异**

Run：

```powershell
git diff --check
git status --short
git log -5 --oneline
```

Expected：`git diff --check` 无输出；状态中没有意外文件；最近提交包含本计划的三个中文实现提交和此前设计/计划文档提交。

- [ ] **Step 5: 执行界面手工验收**

在本地四服务环境打开任一绑定埋点配置的 `event` 数据源图表编辑器，逐项验证：

```text
1. 指标筛选顶部显示“事件属性 / 用户属性”，活动标签为深色文字和蓝色底部线。
2. 事件属性只显示当前指标事件的参数，切换指标事件后旧参数显示范围错误且不会自动替换。
3. 用户属性只显示 event.userinfo JSON 叶子字段，不出现 user 表、personal 字段或 uid/dt/event。
4. 全局筛选顶部只显示“用户属性”，不出现事件属性占位。
5. 指标筛选和全局筛选选择同一个用户属性后，SQL 请求均保留 sourceField/jsonPath/expression。
6. 生成 SQL 引用 event.userinfo，不引用 user 表。
```

Expected：六项全部符合；任一项不符合时保留现场配置和控制台错误，不提交额外修补，先增加能复现问题的失败测试。
