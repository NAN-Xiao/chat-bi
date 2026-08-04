# 看板 SQL 编辑器时间范围布局实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 SQL 图表的“时间范围”移到图表配置卡片外，只保留日期范围选择器，并在编辑器全流程固定使用 `dt / day / yyyymmdd_number`。

**Architecture:** 保持 `DashboardSqlEditor.vue` 现有状态和持久化结构，增加三个显式常量作为该编辑器的时间契约。模板只移动日期表达式入口，不改 `DashboardDateExpressionPicker`；初始化、重置、历史恢复、AI SQL 载荷和保存统一读取固定值，日期表达式仍按现有结构恢复和校验。

**Tech Stack:** Vue 3 `<script setup>`、TypeScript、Element Plus、Node.js `assert` 契约测试、Vite/`vue-tsc`。

## Global Constraints

- 展示名称必须保持“时间范围”，不得改成“事件范围”。
- 时间范围必须位于“图表配置 / SQL 明细”卡片外，并与执行数据源、图表标题和图表类型同级。
- 公共时间范围只显示 `DashboardDateExpressionPicker`，不得显示时间字段、时间粒度或日期参数类型下拉框。
- SQL 编辑器时间契约固定为 `timeField = "dt"`、`timeGrain = "day"`、`dateParameterType = "yyyymmdd_number"`。
- 不得在 `dt` 缺失时静默选择其他字段。
- 必须保留当前工作区未提交的 `metricDateExpressionEnabled` 兼容逻辑，不覆盖无关修改。
- 不修改 MCP-only 编辑流程，不增加数据源名称、ID 或业务领域分支。

## File Structure

- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs`：锁定公共布局、固定时间契约和旧配置规范化行为。
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：定义固定契约、统一状态读写并移动模板控件。
- Verify: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`：确保日期表达式和指标卡兼容逻辑保持有效。
- Verify: `frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs`：确保 builder 轻量持久化结构不回归。
- Verify: `frontend/src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs`：确保预览失效检测不回归。

---

### Task 1: 固定时间契约并移动公共控件

**Files:**
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Test: `frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs`

**Interfaces:**
- Consumes: `DashboardDateExpressionPicker`、`sqlBuilder.timeExpression`、`builderConfigForSave()`、`restoreSqlBuilderState(value)`、`dashboardDateFilterConfigForWrite()`。
- Produces: `SQL_EDITOR_TIME_FIELD: "dt"`、`SQL_EDITOR_TIME_GRAIN: "day"`、`SQL_EDITOR_DATE_PARAMETER_TYPE: "yyyymmdd_number"`，以及卡片外唯一的“时间范围”表单项。

- [ ] **Step 1: 写布局和固定值的失败测试**

创建 `DashboardSqlEditor.time-range-layout.test.mjs`，使用现有源码契约测试风格：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8',
)

assert.match(source, /const SQL_EDITOR_TIME_FIELD = 'dt'/)
assert.match(source, /const SQL_EDITOR_TIME_GRAIN = 'day'/)
assert.match(source, /const SQL_EDITOR_DATE_PARAMETER_TYPE = 'yyyymmdd_number'/)

const panelStart = source.indexOf('<div v-if="hasSqlSource && canUseSqlEditor" class="sql-builder-panel">')
const publicTimeRange = source.indexOf('<el-form-item v-if="hasSqlSource" label="时间范围">')
const executionDatasource = source.indexOf('<el-form-item v-if="hasSqlSource" label="执行数据源">')
assert.ok(panelStart >= 0, '需要保留 SQL 图表配置卡片')
assert.ok(publicTimeRange > panelStart, '时间范围必须位于 SQL 图表配置卡片之后')
assert.ok(executionDatasource > publicTimeRange, '时间范围必须与执行数据源同级并排在其前面')

const publicTimeRangeSource = source.slice(publicTimeRange, executionDatasource)
assert.match(publicTimeRangeSource, /<DashboardDateExpressionPicker/)
assert.doesNotMatch(publicTimeRangeSource, /BuilderFieldPicker|builderTimeGrainOptions|builderTimeRangeOptions/)

const builderPaneStart = source.indexOf('<div v-if="sqlBuilder.activeTab === \'builder\'"')
const sqlPaneStart = source.indexOf('<div v-else class="sql-builder-sql-pane">', builderPaneStart)
const builderPaneSource = source.slice(builderPaneStart, sqlPaneStart)
assert.doesNotMatch(builderPaneSource, /<span>时间范围<\/span>/)

const resetSource = source.match(/function resetSqlBuilderState\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(resetSource, /sqlBuilder\.timeField = SQL_EDITOR_TIME_FIELD/)
assert.match(resetSource, /sqlBuilder\.timeGrain = SQL_EDITOR_TIME_GRAIN/)
assert.match(resetSource, /form\.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE/)

assert.match(source, /function fixedSqlEditorTimeFieldIssue\(\)/)
assert.match(source, /当前执行数据源缺少固定时间字段 dt/)
assert.match(source, /fixedSqlEditorTimeFieldIssue\(\)/)

const restoreSource = source.match(/function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(restoreSource, /sqlBuilder\.timeField = SQL_EDITOR_TIME_FIELD/)
assert.match(restoreSource, /sqlBuilder\.timeGrain = SQL_EDITOR_TIME_GRAIN/)
assert.doesNotMatch(restoreSource, /value\.timeField|value\.timeGrain/)

const saveSource = source.match(/function builderConfigForSave\(\) \{([\s\S]*?)\n\}/)?.[1] || ''
assert.match(saveSource, /timeField: SQL_EDITOR_TIME_FIELD/)
assert.match(saveSource, /timeGrain: SQL_EDITOR_TIME_GRAIN/)

assert.doesNotMatch(source, /v-for="item in pivotDateParameterTypeOptions"/)
console.log('dashboard SQL editor time range layout contract passed')
```

- [ ] **Step 2: 运行新测试并确认按预期失败**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs
```

Expected: FAIL，首个失败信息指向缺少 `SQL_EDITOR_TIME_FIELD`，证明测试覆盖尚未实现的固定契约。

- [ ] **Step 3: 增加固定契约并统一状态生命周期**

在 `DashboardSqlEditor.vue` 的日期参数类型定义附近增加：

```ts
const SQL_EDITOR_TIME_FIELD = 'dt'
const SQL_EDITOR_TIME_GRAIN = 'day'
const SQL_EDITOR_DATE_PARAMETER_TYPE: DashboardDateParameterType = 'yyyymmdd_number'
```

将 `sqlBuilder` 初始值、`resetSqlBuilderState()`、`restoreSqlBuilderState()` 和 `builderConfigForSave()` 改为使用这些常量：

```ts
timeField: SQL_EDITOR_TIME_FIELD,
timeGrain: SQL_EDITOR_TIME_GRAIN,
timeRange: 'expression',
```

```ts
sqlBuilder.timeField = SQL_EDITOR_TIME_FIELD
sqlBuilder.timeGrain = SQL_EDITOR_TIME_GRAIN
sqlBuilder.timeRange = 'expression'
form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
```

```ts
function restoreSqlBuilderState(value: any) {
  sqlBuilder.timeField = SQL_EDITOR_TIME_FIELD
  sqlBuilder.timeGrain = SQL_EDITOR_TIME_GRAIN
  form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
  if (!value || typeof value !== 'object') return
  sqlBuilder.dateExpressionPickerEnabled = true
  sqlBuilder.metricDateExpressionEnabled = value.metricDateExpressionEnabled === true
  const timeExpression = normalizeDashboardDateExpression(value.timeExpression)
  sqlBuilder.timeExpression = timeExpression || defaultDashboardDateExpression()
  sqlBuilder.timeRange = 'expression'
  sqlBuilder.timeCustomRange = []
  sqlBuilder.groups = Array.isArray(value.groups)
    ? value.groups.filter((item: any) => typeof item === 'string')
    : []
  sqlBuilder.globalFilters = restoreBuilderFilters(value.globalFilters)
  sqlBuilder.globalFilterLogic = builderLogic(value.globalFilterLogic)
  sqlBuilder.approximate = value.approximate === true
  restoreBuilderAgentAdvice(value.agentAdvice)
}
```

```ts
return {
  timeField: SQL_EDITOR_TIME_FIELD,
  timeGrain: SQL_EDITOR_TIME_GRAIN,
  timeRange: 'expression',
  timeCustomRange: [],
  dateExpressionPickerEnabled: usesDashboardDateParameters,
  metricDateExpressionEnabled: sqlBuilder.metricDateExpressionEnabled === true,
  timeExpression: usesDashboardDateParameters && sqlBuilder.timeExpression
    ? cloneDashboardDateExpression(sqlBuilder.timeExpression)
    : null,
  groups: [...sqlBuilder.groups],
  globalFilters: compactBuilderFilters(sqlBuilder.globalFilters),
  globalFilterLogic: builderLogic(sqlBuilder.globalFilterLogic),
  approximate: sqlBuilder.approximate === true,
  agentAdvice: builderAgentAdviceForSave(),
}
```

`syncDashboardDateParameterUsage()`、`initPivotConfig()` 和 `initEditor()` 不再把日期参数类型清空或从历史配置覆盖为其他类型；它们都显式保持：

```ts
form.pivotDateParameterType = SQL_EDITOR_DATE_PARAMETER_TYPE
```

AI SQL 载荷和日期筛选配置继续走现有函数，但日期类型直接使用固定常量：

```ts
dateParameterType: shouldUseDashboardDateParameters()
  ? SQL_EDITOR_DATE_PARAMETER_TYPE
  : '',
```

```ts
return buildDashboardDateFilterConfig(
  form.sql,
  SQL_EDITOR_DATE_PARAMETER_TYPE,
  expression,
)
```

在 SQL Builder 的阻断校验中增加固定字段存在性检查，不做字段替换：

```ts
function fixedSqlEditorTimeFieldIssue() {
  if (schemaLoading.value || schemaFieldOptions.value.length === 0) return ''
  const hasFixedField = schemaFieldOptions.value.some((option) => (
    option.field === SQL_EDITOR_TIME_FIELD || option.value === SQL_EDITOR_TIME_FIELD
  ))
  return hasFixedField ? '' : '当前执行数据源缺少固定时间字段 dt。'
}
```

`builderBlockingScopeIssues()` 在原有事件范围和筛选范围错误之外合并这个错误；`generateBuilderAiSql()` 使用同一个阻断入口显示本地建议并停止生成。

- [ ] **Step 4: 移动时间范围模板并删除三个下拉入口**

从 `sql-builder-builder-pane` 删除整个 `builder-time-section`，包括 `BuilderFieldPicker`、粒度下拉、旧时间范围下拉和旧自定义日期控件。

在 MCP 区域结束之后、执行数据源之前增加公共表单项，使它和执行数据源、图表标题连续排列：

```vue
<el-form-item v-if="hasSqlSource" label="时间范围">
  <DashboardDateExpressionPicker
    :model-value="sqlBuilder.timeExpression"
    variant="roi"
    timezone="Asia/Shanghai"
    :disabled="loading || builderLoading || !dateExpressionEnabled"
    @apply="applyDateExpression"
  />
</el-form-item>
```

删除透视配置中的日期参数类型 `<el-form-item>`。删除不再使用的 `builderTimeRangeOptions`、`pivotDateParameterTypeOptions` 和仅服务于旧三列时间区域的样式；保留 `builderTimeGrainOptions` 仅当其他建议文案仍需其标签映射。

- [ ] **Step 5: 运行新测试并确认通过**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs
```

Expected: 输出 `dashboard SQL editor time range layout contract passed`。

- [ ] **Step 6: 运行紧邻回归测试**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
```

Expected: 四个测试均输出各自的 `passed` 消息。若旧断言仍要求卡片内日期控件或可选日期类型，只更新与已确认新交互直接冲突的断言，不弱化日期表达式恢复、指标卡兼容、预览签名和事件范围校验。

- [ ] **Step 7: 提交本任务文件**

仅在用户要求提交实现时执行：

```powershell
git add -- frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs frontend/src/views/dashboard/common/DashboardSqlEditor.builder-persistence.test.mjs frontend/src/views/dashboard/common/DashboardSqlEditor.preview-signature.test.mjs frontend/src/views/dashboard/common/DashboardSqlEditor.event-table-scope.test.mjs
git commit -m "调整看板 SQL 编辑器时间范围配置"
```

Expected: 提交只包含本功能实际修改的文件；不得暂存工作区其他用户改动。

### Task 2: 完整前端验证与视觉验收

**Files:**
- Verify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Verify: `frontend/src/views/dashboard/common/DashboardSqlEditor*.test.mjs`

**Interfaces:**
- Consumes: Task 1 的固定时间契约和公共“时间范围”表单项。
- Produces: 可构建、无模板类型错误且在桌面抽屉中布局正确的编辑器。

- [ ] **Step 1: 运行全部 DashboardSqlEditor 契约测试**

Run:

```powershell
Get-ChildItem frontend/src/views/dashboard/common -Filter 'DashboardSqlEditor*.test.mjs' | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { throw "测试失败: $($_.Name)" } }
```

Expected: 所有测试退出码为 `0`，每个文件输出 `passed`。

- [ ] **Step 2: 运行前端类型检查和生产构建**

Run:

```powershell
npm run build
```

Working directory: `frontend`

Expected: `vue-tsc -b` 和 `vite build` 均成功，退出码为 `0`。

- [ ] **Step 3: 启动或复用本地前端并做视觉验收**

先检查 `5173`，仅在未监听时从 `frontend` 启动 `npm run dev`。打开编辑图表抽屉并分别选择“图表配置”和“SQL 明细”，验证：

```text
时间范围位于白色页签卡片下方；
两个页签下都显示同一个日期范围入口；
时间字段、按天/按周/按月和日期格式下拉均不可见；
时间范围、执行数据源、图表标题之间无重叠或横向溢出。
```

在至少 `1440x900` 桌面视口和 `720px` 宽抽屉边界下截图检查。

- [ ] **Step 4: 检查最终差异**

Run:

```powershell
git diff --check
git diff -- frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.time-range-layout.test.mjs
git status --short
```

Expected: `git diff --check` 无输出；差异只包含本功能修改，工作区其他既有改动保持不变。
