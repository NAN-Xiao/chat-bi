# 仪表盘筛选全部标签与用户属性元数据 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让指标筛选显示“全部 / 事件属性 / 用户属性”，并通过现有权限受控字段接口展示已配置的 `event.userinfo` 用户属性。

**Architecture:** `DashboardSqlEditor` 保留现有执行数据源元数据读取，并针对有效默认事件表调用现有 `fieldList` 接口，将服务端合并、编译并过滤权限后的字段替换进该表。`BuilderFieldPicker` 增加 `all` 属性标签，在全部标签下按事件属性、用户属性顺序分组；全局筛选继续只传入用户属性标签。

**Tech Stack:** Vue 3 + TypeScript、Element Plus、Node 内置测试、FastAPI/pytest 现有后端测试。

## Global Constraints

- 所有筛选候选只来自当前工作空间授权的 `event` 表。
- 用户属性只允许 `event.userinfo` 已配置 JSON 叶子字段，不读取 `user` 表，不扫描运行时 JSON 样本。
- 不静默替换失效字段，继续显示“字段不属于当前筛选范围”并阻止 SQL 生成。
- 不新增数据库表、字段或后端元数据接口；复用现有 `/datasource/fieldList/{table_id}`。
- 全局筛选保持只有“用户属性”，不增加“全部”或“事件属性”。

---

### Task 1: 用现有 fieldList 补齐默认事件表字段

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:7-8,2700-2780`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

**Interfaces:**
- Consumes: `datasourceApi.fieldList(tableId, { excludeContainerFields: false })`。
- Produces: `schemaTables` 中默认事件表的字段包含服务端返回的 `source_field`、`json_path`、`expression`、`is_json_subfield`。

- [ ] **Step 1: Write the failing test**

在 `DashboardSqlEditor.filter-property-scope.test.mjs` 增加断言：编辑器导入 `datasourceApi`，读取默认事件表 ID，并调用 `fieldList`，且合并结果保留 `source_field` 与 `json_path`。

```js
assert.match(editor, /import \{ datasourceApi \} from '@\/api\/datasource'/, '看板需要复用数据源字段接口')
assert.match(editor, /datasourceApi\.fieldList\(/, '默认事件表需要加载权限受控字典字段')
assert.match(editor, /source_field|sourceField/, '字段合并需要保留 JSON 宿主字段')
assert.match(editor, /json_path|jsonPath/, '字段合并需要保留 JSON 路径')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

Expected: FAIL because the editor does not import or call `datasourceApi.fieldList` yet.

- [ ] **Step 3: Write minimal implementation**

在 `DashboardSqlEditor.vue` 引入 `datasourceApi`。在 `loadSchemaTables` 的 metadata loader 中，在取得 `trackingConfigResult` 与物理 metadata 后定位默认事件表；对该表调用一次 `fieldList`，成功时将返回列表转换为当前 `schemaTables` 需要的字段结构并替换该表字段，失败时保留物理字段并让现有空态/权限逻辑继续生效。不得将其他表的字段或 `user` 表字段合并到事件表。

```ts
const defaultEventTable = String(
  trackingConfigResult?.default_event_table || trackingConfigResult?.defaultEventTable || '',
).trim()
const enrichedTables = await Promise.all(normalizedTables.map(async (table) => {
  const tableName = schemaTableName(table)
  if (!defaultEventTable || tableName !== defaultEventTable || !table?.id) return table
  try {
    const fields = await datasourceApi.fieldList(table.id, { excludeContainerFields: false })
    return { ...table, fields: Array.isArray(fields) ? fields : table.fields || [] }
  } catch {
    return table
  }
}))
```

使用 `fieldList` 原始字段对象的 snake_case 属性，`schemaFieldOptions` 已同时支持 snake_case/camelCase；不在前端重新编译 JSON 表达式。

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
git commit -m "修复看板用户属性元数据加载"
```

### Task 2: 增加指标筛选“全部”标签及固定分组顺序

**Files:**
- Modify: `frontend/src/views/dashboard/common/BuilderFieldPicker.vue:14-225`
- Modify: `frontend/src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs`

**Interfaces:**
- Consumes: `filterPropertyTabs` 中的 `'all' | 'event' | 'user'`。
- Produces: 全部标签按事件属性分组、用户属性分组顺序返回；单标签行为保持不变。

- [ ] **Step 1: Write the failing test**

在 `BuilderFieldPicker.filter-property.test.mjs` 增加断言，要求类型支持 `all`，标签顺序为“全部 / 事件属性 / 用户属性”，并存在全部标签下的事件、用户分组顺序处理。

```js
assert.match(source, /type FilterPropertyTab = 'all' \| 'event' \| 'user'/, '筛选标签需要支持全部')
assert.match(source, /label: '全部', value: 'all'/, '指标筛选需要全部标签')
assert.match(source, /event.*user|user.*event/s, '全部标签需要同时处理事件和用户属性')
assert.match(source, /事件属性.*用户属性/s, '全部标签分组顺序需要事件属性在前')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs`

Expected: FAIL because当前类型和标签列表只有 `event`、`user`。

- [ ] **Step 3: Write minimal implementation**

将 `FilterPropertyTab` 扩展为 `'all' | 'event' | 'user'`，为筛选模式单独声明“全部 / 事件属性 / 用户属性”标签。`matchesTab` 在 `all` 时允许事件或用户属性；`groupedOptions` 在全部标签下先筛选事件属性再筛选用户属性，各自生成分组，过滤空分组；单独标签仍只生成对应分组。`propertyEmptyText` 为全部标签返回“暂无筛选属性”。

```ts
type FilterPropertyTab = 'all' | 'event' | 'user'

const filterPropertyTabOptions = [
  { label: '全部', value: 'all' },
  { label: '事件属性', value: 'event' },
  { label: '用户属性', value: 'user' },
] as const
```

模板调用方由 Task 3 将指标筛选的 `filter-property-tabs` 改为 `['all', 'event', 'user']`；全局仍传 `['user']`。

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/dashboard/common/BuilderFieldPicker.vue frontend/src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs
git commit -m "新增指标筛选全部标签"
```

### Task 3: 接入标签调用方并验证端到端边界

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:4780-4800,4945-4965`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

**Interfaces:**
- Consumes: Task 2 的 `FilterPropertyTab`。
- Produces: 指标筛选三个标签、全局筛选单用户标签，且两个用户属性候选源一致。

- [ ] **Step 1: Write the failing test**

将现有指标筛选标签静态断言由 `['event', 'user']` 改为要求 `['all', 'event', 'user']`，同时保留全局 `['user']` 断言。

```js
assert.match(editor, /:filter-property-tabs="\['all', 'event', 'user'\]"/, '指标筛选需要全部、事件、用户三个标签')
assert.match(editor, /:filter-property-tabs="\['user'\]"/, '全局筛选仍只能显示用户属性')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

Expected: FAIL because指标筛选当前只传入 `['event', 'user']`。

- [ ] **Step 3: Write minimal implementation**

仅修改指标筛选和公式指标内筛选的 `filter-property-tabs` 绑定为 `['all', 'event', 'user']`；全局筛选保持 `['user']`。不得扩大 `eventUserPropertyOptions` 的筛选条件。

- [ ] **Step 4: Run focused verification**

Run: `node --test src/views/dashboard/common/builderFieldPickerOptions.test.mjs src/views/dashboard/common/BuilderFieldPicker.filter-property.test.mjs src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs`

Expected: 3 test files pass。

- [ ] **Step 5: Run build and backend regression**

Run: `npm run build` from `frontend`, and `D:\AIWork3\chat-bi\backend\.venv\Scripts\python.exe -m pytest tests\test_dashboard_ai_sql_generator.py -q` from `backend`.

Expected: TypeScript/Vite build succeeds; backend dashboard SQL generator tests pass without new failures。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.filter-property-scope.test.mjs
git commit -m "接入筛选全部标签与字典字段"
```

### Task 4: 页面验收与分支收尾

**Files:**
- No source changes expected.

- [ ] **Step 1: Reload the local dashboard editor**

Use the existing local page at `http://127.0.0.1:5174/` and reopen a chart SQL editor bound to the configured `event` table.

- [ ] **Step 2: Verify visible behavior**

Confirm metric filter shows `全部 / 事件属性 / 用户属性`; “全部” renders event groups before user groups; configured `event.userinfo` fields such as `应用版本` and `国家` are visible; global filter shows only `用户属性` and the same user fields.

- [ ] **Step 3: Verify repository state**

Run `git diff --check` and `git status --short`; ensure no uncommitted generated files remain.

- [ ] **Step 4: Preserve the user-facing browser tab**

Finalize the existing browser tab with `status: "deliverable"` so the user can continue testing the local page.
