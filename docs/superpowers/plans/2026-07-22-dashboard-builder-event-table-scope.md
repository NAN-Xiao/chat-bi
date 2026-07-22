# Dashboard Builder Event Table Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让图表 SQL 配置器事件模式的五类候选、确定性校验和 Agent Schema 只使用当前工作空间 `default_event_table` 指定表，并明确处理缺失配置、旧跨表配置和 JSON 路径错误。

**Architecture:** 前端在独立元数据辅助模块中解析事件范围状态，并由 `DashboardSqlEditor` 将过滤后的候选集合传给共享选择器。后端从系统库工作空间埋点配置读取默认事件表，在构建 `BusinessSqlContext` 时通过 `table_list` 收窄权威 Schema；现有 JSON 结构化校验继续作为 SQL 生成后的确定性保障。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert`、FastAPI、SQLModel、pytest、LangGraph。

## Global Constraints

- 不在共享代码中硬编码修仙空间、数据源 ID 或默认表名 `event`。
- `BuilderFieldPicker` 保持通用，只展示调用方传入的 `options`。
- 配置缺失、失效或无权限时不得回退到第一张表、同名字段或全部字段。
- 已保存无效配置保留原值并阻止重新生成/应用，不在加载时静默删除或替换。
- 前端候选、后端确定性校验和 Agent Schema 必须使用相同工作空间、数据源和权限边界。
- 保留当前工作区已有的时间字段与其他未提交改动，只提交本计划明确涉及的文件。

---

### Task 1: 事件范围元数据与纯函数

**Files:**
- Modify: `frontend/src/views/dashboard/common/dashboardBuilderMetadata.ts`
- Modify: `frontend/src/views/dashboard/common/dashboardBuilderMetadata.test.mjs`

**Interfaces:**
- Produces: `resolveDashboardBuilderEventScope(input): DashboardBuilderEventScope`
- Produces: `getEventScopedFields<T extends Pick<FieldOption, 'table'>>(fields, scope): T[]`
- Changes: `buildTrackingEventCatalogFromConfig(config)` 在默认事件表或事件名字段缺失时返回 `null`，不再生成猜测目录。

- [ ] **Step 1: 写失败测试，覆盖配置驱动与无回退**

```js
assert.equal(buildTrackingEventCatalogFromConfig({ enabled: true, event_name_mappings: [] }), null)
assert.deepEqual(
  getEventScopedFields(
    [{ table: 'event', value: 'event.uid' }, { table: 'user', value: 'user.uid' }],
    { mode: 'event', defaultEventTable: 'event', status: 'active', message: '' }
  ).map((item) => item.value),
  ['event.uid']
)
assert.equal(resolveDashboardBuilderEventScope({
  config: { id: 1, enabled: true, datasource_id: 6, default_event_table: 'event' },
  datasourceId: 6,
  tableNames: ['event', 'user'],
}).status, 'active')
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend; node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs`

Expected: FAIL，提示导出函数不存在或缺失配置仍返回 `event` 目录。

- [ ] **Step 3: 实现事件范围类型和纯函数**

```ts
export type DashboardBuilderEventScope = {
  mode: 'general' | 'event'
  status: 'general' | 'active' | 'missing-default-table' | 'datasource-mismatch' | 'table-unavailable'
  defaultEventTable: string
  message: string
}

export function getEventScopedFields<T extends Pick<FieldOption, 'table'>>(
  fields: T[],
  scope: DashboardBuilderEventScope
): T[] {
  if (scope.mode !== 'event' || scope.status !== 'active') return scope.mode === 'general' ? [...fields] : []
  return fields.filter((field) => field.table === scope.defaultEventTable)
}
```

`resolveDashboardBuilderEventScope` 必须区分未配置/未启用的普通模式与已启用但配置无效的事件模式，并返回文档规定的明确中文消息。

- [ ] **Step 4: 移除事件目录默认字符串回退**

```ts
const eventTable = firstPlainText(config.default_event_table, config.defaultEventTable)
const eventNameField = firstPlainText(config.default_event_name_field, config.defaultEventNameField)
if (!eventTable || !eventNameField) return null
```

- [ ] **Step 5: 运行元数据测试**

Run: `cd frontend; node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs`

Expected: PASS，输出 `dashboard builder metadata tests passed`。

### Task 2: DashboardSqlEditor 候选范围和旧配置处理

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs`

**Interfaces:**
- Consumes: `resolveDashboardBuilderEventScope`、`getEventScopedFields`。
- Produces: `eventFieldScope`、`eventScopedSchemaFieldOptions`、`builderEventScopeIssues()`。

- [ ] **Step 1: 写失败的源码契约测试**

测试需断言：

```js
assert.match(source, /const eventFieldScope = computed/)
assert.match(source, /const eventScopedSchemaFieldOptions = computed/)
assert.match(source, /:field-options="builderFieldOptions"/)
assert.doesNotMatch(source, /const builderFieldOptions = computed\(\(\) => schemaFieldOptions\.value\.filter/)
assert.doesNotMatch(source, /const prunedInvalidSelections = pruneInvalidBuilderSelections\(\)/)
```

- [ ] **Step 2: 运行源码契约测试确认失败**

Run: `cd frontend; node src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs`

Expected: FAIL，提示尚未定义事件范围计算属性。

- [ ] **Step 3: 保存原始埋点配置并计算范围状态**

在 metadata 缓存结果中同时保留 `trackingConfig`，加载完成后赋给独立 `ref`；用当前数据源 ID 和 `schemaTables` 的物理表名计算 `eventFieldScope`。

- [ ] **Step 4: 将五类候选收敛到默认事件表**

```ts
const eventScopedSchemaFieldOptions = computed(() =>
  getEventScopedFields(schemaFieldOptions.value, eventFieldScope.value)
)
const builderFieldOptions = computed(() =>
  eventScopedSchemaFieldOptions.value.filter(isSelectableFieldOption)
)
```

时间字段从 `eventScopedSchemaFieldOptions` 计算；事件目录只在 `eventFieldScope.status === 'active'` 时启用，并额外过滤 `eventTable === defaultEventTable`。指标筛选继续使用当前事件参数和同一默认事件表公共字段。

- [ ] **Step 5: 保留旧配置并增加确定性本地错误**

删除加载完成后调用 `pruneInvalidBuilderSelections()` 并持久化清理结果的路径。新增 `builderEventScopeIssues()`，逐项检查时间、指标、指标筛选、全局筛选和分组字段；发现非默认表时返回带位置的错误，例如：

```text
group[0]：当前事件模式不允许使用表 user，仅允许 event。
```

无效范围或旧跨表配置必须在 `generateBuilderAiSql()` 发请求前阻断，且建议只能要求重新选择默认事件表字段，不能复述被阻断字段作为推荐项。

- [ ] **Step 6: 在配置器内展示事件范围错误状态**

事件配置无效时，在 Builder 面板顶部显示 `eventFieldScope.message`，五类候选为空，生成按钮不可继续；普通模式不显示该提示。

- [ ] **Step 7: 运行前端相关测试**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node src/views/dashboard/common/builderFieldPickerOptions.test.mjs
```

Expected: 全部 PASS，且现有时间字段未提交修改相关测试保持通过。

### Task 3: 后端权威事件 Schema 和默认值清理

**Files:**
- Modify: `backend/apps/system/crud/tracking_config.py`
- Modify: `backend/apps/dashboard/crud/ai_sql_generator.py`
- Modify: `backend/tests/test_tracking_event_catalog.py`
- Modify: `backend/tests/test_dashboard_ai_sql_generator.py`

**Interfaces:**
- Produces: `_dashboard_event_scope(config, datasource_id, allowed_tables=None)`。
- Changes: `_node_collect_context` 在事件模式下使用 `table_list=[default_event_table]` 构建 `BusinessSqlContext`。
- Changes: `_deterministic_validate_manual_config` 接收事件范围状态并在调用 LLM 前阻断无效配置。

- [ ] **Step 1: 写失败测试，证明后端不再回退**

```python
def test_build_tracking_event_catalog_does_not_guess_missing_defaults():
    catalog = build_tracking_event_catalog(TenantTrackingConfigDTO(tenant_id=2001))
    assert catalog.event_table == ""
    assert catalog.event_name_field == ""
    assert catalog.groups == []
```

- [ ] **Step 2: 写失败测试，证明事件范围只允许默认表**

测试 `_dashboard_event_scope`：有效配置返回 `table_list == ["event_log"]`；默认表缺失、数据源不一致、默认表未进入后端允许集合时分别返回明确阻断问题。

- [ ] **Step 3: 运行后端定向测试确认失败**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_event_catalog.py backend/tests/test_dashboard_ai_sql_generator.py -q`

Expected: FAIL，原因是目录仍回退、事件范围函数不存在。

- [ ] **Step 4: 移除后端事件目录回退**

```python
event_table = _plain_text(config.default_event_table)
event_name_field = _plain_text(config.default_event_name_field)
if not event_table or not event_name_field:
    return TenantTrackingEventCatalogDTO(
        tenant_id=config.tenant_id,
        datasource_id=config.datasource_id,
        event_table=event_table,
        event_name_field=event_name_field,
        groups=[],
    )
```

- [ ] **Step 5: 从服务端工作空间配置构造 Agent Schema**

`_node_collect_context` 先调用 `get_tracking_config(session, tenant_id, datasource_id)`。当配置记录存在、启用且默认事件表非空时，将 `[default_event_table]` 作为 `BusinessSqlContextService.build(..., table_list=...)` 参数；再检查构建结果是否真的包含该表。

前端传入内容只能进一步描述当前选择，不能扩大服务端默认事件表范围。

- [ ] **Step 6: 合并事件范围确定性错误**

在 `_node_deterministic_validate` 中把服务端事件范围问题合并进 `validation_result.issues`。存在范围问题时直接走失败分支，不调用 SQL 生成或建议模型。

- [ ] **Step 7: 运行后端定向测试**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_event_catalog.py backend/tests/test_dashboard_ai_sql_generator.py -q`

Expected: PASS，零失败。

### Task 4: JSON 精确错误、Agent 建议边界和整体回归

**Files:**
- Modify: `backend/tests/test_dashboard_ai_sql_generator.py`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs`

**Interfaces:**
- Consumes: 现有 `_json_subfield_requirements`、`_json_subfield_sql_issues`、`extract_sql_json_field_pairs`。
- Verifies: 确定性失败不会进入 Agent 建议阶段，成功事件模式只暴露默认事件表 Schema。

- [ ] **Step 1: 增加 JSON 精确错误回归测试**

构造 `label="全局筛选[0]"`、`source_field="currentinfo"`、`json_path="$._eventTime"`，断言缺失 SQL 返回：

```text
全局筛选[0]：JSON 字段 currentinfo + $._eventTime 未出现在生成 SQL 中。
```

并保留 MySQL、PostgreSQL、ClickHouse 已有正确路径通过测试。

- [ ] **Step 2: 增加 Agent 范围回归测试**

模拟工作空间默认事件表为 `event`、权威 Schema 同时存在 `event` 与 `user`，断言传给 `BusinessSqlContextService.build` 的 `table_list` 只有 `event`，最终 `allowed_tables` 也只有 `event`。

- [ ] **Step 3: 运行完整相关测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_tracking_event_catalog.py backend/tests/test_dashboard_ai_sql_generator.py backend/tests/test_datasource_builder_schema_permission_source.py -q
cd frontend
node src/views/dashboard/common/dashboardBuilderMetadata.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.event-filter-advice.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.formula-event-metric.test.mjs
npm run build
```

Expected: pytest 与 Node 测试零失败，Vite 构建成功。

- [ ] **Step 4: 检查硬编码、差异和提交范围**

Run:

```powershell
rg -n "default_event_table.*or \"event\"|default_event_table.*\|\| 'event'" backend frontend/src/views/dashboard/common
git diff --check
git status --short
```

Expected: 本需求运行路径不存在默认事件表字符串回退；`git diff --check` 通过；无关日志和用户已有改动未被暂存。
