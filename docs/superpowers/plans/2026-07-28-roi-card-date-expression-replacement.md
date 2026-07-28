# ROI 图表卡片日期表达式入口替换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅为已显式启用日期表达式的 4 张 ROI 图表卡片替换双月日期面板，并在应用后刷新当前图表。

**Architecture:** 复用现有 `DashboardDateExpressionPicker.vue` 和表达式模型。新增纯函数构造卡片临时执行 Pivot，清除旧 `custom` 覆盖；`sq-view/index.vue` 只维护当前会话状态，刷新成功后提交表达式，失败时保留上一次成功值。普通图表继续走原双月日期面板。

**Tech Stack:** Vue 3、TypeScript、Element Plus、Node `assert` 契约测试、现有 Dashboard SQL Preview API。

## Global Constraints

- 仅当 `sourceConfig.sql.builder.dateExpressionPickerEnabled === true` 时替换卡片入口。
- 不按看板名称、资源 ID、图表标题或业务字段在运行时代码中判断 ROI。
- 卡片应用不写回 `viewInfo.pivot.date_expression`，不改变 SQL 编辑抽屉的持久化默认值。
- 普通看板保留现有双月日期范围面板。
- 不增加看板全局日期筛选，不删除旧日期控件。

---

### Task 1: 增加卡片表达式 Pivot 适配纯函数

**Files:**
- Modify: `frontend/src/views/dashboard/common/dashboardDateExpression.ts`
- Modify: `frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs`

**Interfaces:**
- Consumes: `DashboardDateExpression`、已有 Pivot 对象。
- Produces: `buildDashboardDateExpressionPivot(pivot, expression): Record<string, unknown>`。

- [ ] **Step 1: 写失败测试**

在 `dashboardDateExpression.test.mjs` 增加：

```js
const override = buildDashboardDateExpressionPivot(
  {
    enabled: false,
    time_field: 'dt',
    date_parameter_type: 'yyyymmdd_number',
    range: 'custom',
    custom_start: '2026-07-01',
    custom_end: '2026-07-27',
  },
  { version: 1, mode: 'preset', preset: 'today' }
)
assert.deepEqual(override.date_expression, { version: 1, mode: 'preset', preset: 'today' })
assert.equal(override.range, 'source')
assert.equal(override.custom_start, '')
assert.equal(override.custom_end, '')
assert.equal(override.time_field, 'dt')
assert.equal(override.date_parameter_type, 'yyyymmdd_number')
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend && node src/views/dashboard/common/dashboardDateExpression.test.mjs`

Expected: FAIL，提示未导出 `buildDashboardDateExpressionPivot`。

- [ ] **Step 3: 实现最小纯函数**

在 `dashboardDateExpression.ts` 增加：

```ts
export function buildDashboardDateExpressionPivot(
  pivot: Record<string, unknown> | null | undefined,
  expression: DashboardDateExpression
): Record<string, unknown> {
  return {
    ...(pivot && typeof pivot === 'object' ? pivot : {}),
    range: 'source',
    custom_start: '',
    custom_end: '',
    date_expression: cloneDashboardDateExpression(expression),
  }
}
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `cd frontend && node src/views/dashboard/common/dashboardDateExpression.test.mjs`

Expected: `dashboard date expression tests passed`。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/views/dashboard/common/dashboardDateExpression.ts frontend/src/views/dashboard/common/dashboardDateExpression.test.mjs
git commit -m "功能：增加卡片日期表达式执行适配"
```

---

### Task 2: 替换显式启用图表的卡片日期入口

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs`

**Interfaces:**
- Consumes: `DashboardDateExpressionPicker`、`normalizeDashboardDateExpression`、`cloneDashboardDateExpression`、`buildDashboardDateExpressionPivot`。
- Produces: `dateExpressionPickerEnabled`、`showDashboardDateExpression`、`applyDashboardDateExpression(value)` 卡片执行链。

- [ ] **Step 1: 写失败的卡片接线测试**

更新 `index.date-filter.test.mjs`，要求源码包含：

```js
assert.match(source, /import DashboardDateExpressionPicker/)
assert.match(source, /const dateExpressionPickerEnabled = computed/)
assert.match(source, /sourceConfig\?\.sql\?\.builder\?\.dateExpressionPickerEnabled\s*===\s*true/)
assert.match(source, /<DashboardDateExpressionPicker/)
assert.match(source, /v-if="showDashboardDateExpression"/)
assert.match(source, /v-else-if="showDashboardDateFilter\s*&&\s*!dateExpressionPickerEnabled"/)
assert.match(source, /async function applyDashboardDateExpression/)
assert.match(source, /buildDashboardDateExpressionPivot/)
assert.match(source, /pivotOverride:[\s\S]*buildDashboardDateExpressionPivot/)
```

删除 `DashboardSqlEditor.date-expression.test.mjs` 中禁止卡片引用表达式组件的旧断言，改为确认卡片按配置开关接入，且不包含 ROI ID/名称分支。

- [ ] **Step 2: 运行测试并确认失败**

Run:

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
```

Expected: FAIL，缺少卡片表达式组件和应用处理器。

- [ ] **Step 3: 增加卡片表达式状态**

在 `sq-view/index.vue` 中导入组件和纯函数，并增加：

```ts
const dateExpressionPickerEnabled = computed(
  () => props.viewInfo?.sourceConfig?.sql?.builder?.dateExpressionPickerEnabled === true
)
const configuredDashboardDateExpression = computed(() =>
  normalizeDashboardDateExpression(props.viewInfo?.pivot?.date_expression)
)
const dashboardDateExpression = ref(
  configuredDashboardDateExpression.value
    ? cloneDashboardDateExpression(configuredDashboardDateExpression.value)
    : null
)
const dashboardDateExpressionApplying = ref(false)
const showDashboardDateExpression = computed(
  () => showDashboardDateFilter.value
    && dateExpressionPickerEnabled.value
    && dashboardDateExpression.value !== null
)
```

监听 `props.viewInfo` 和持久化表达式变化，在非应用状态下重新初始化会话状态，不写回 `viewInfo.pivot`。

- [ ] **Step 4: 增加成功提交、失败回滚的应用处理器**

```ts
async function applyDashboardDateExpression(value: DashboardDateExpression) {
  if (dashboardDateExpressionApplying.value) return
  dashboardDateExpressionApplying.value = true
  const next = cloneDashboardDateExpression(value)
  try {
    const succeeded = await refreshData({
      forceRefresh: true,
      blocking: true,
      pivotOverride: buildDashboardDateExpressionPivot(getPivotPayload(), next),
    })
    if (succeeded) dashboardDateExpression.value = next
  } finally {
    dashboardDateExpressionApplying.value = false
  }
}
```

- [ ] **Step 5: 替换模板入口并保留旧控件隔离**

在卡片日期工具栏位置先渲染：

```vue
<div v-if="showDashboardDateExpression" class="date-filter-toolbar date-expression-toolbar">
  <DashboardDateExpressionPicker
    :model-value="dashboardDateExpression"
    timezone="Asia/Shanghai"
    :disabled="dashboardDateExpressionApplying"
    @apply="applyDashboardDateExpression"
  />
</div>
```

原双月日期工具栏改为：

```vue
<div v-else-if="showDashboardDateFilter && !dateExpressionPickerEnabled" class="date-filter-toolbar">
```

表达式工具栏复用现有 `242px` 响应式宽度，不复制弹层样式。

- [ ] **Step 6: 运行卡片与编辑器定向测试**

Run:

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
```

Expected: 三组测试全部通过。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs frontend/src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
git commit -m "功能：替换ROI卡片日期入口"
```

---

### Task 3: 回归、浏览器验收与本地重启

**Files:**
- Verify only: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Verify only: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Verify only: `backend/apps/dashboard/crud/dashboard_date_filter.py`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的最终实现。
- Produces: 可见验收证据、完整本地服务状态。

- [ ] **Step 1: 运行前端相关测试和生产构建**

Run:

```powershell
cd frontend
node src/views/dashboard/common/dashboardDateExpression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.date-expression.test.mjs
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/components/sq-view/index.refresh-policy.test.mjs
npm run build
```

Expected: 全部退出码 `0`，生产构建成功。

- [ ] **Step 2: 运行后端日期执行回归**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
backend\.venv\Scripts\python.exe -m pytest tests/test_dashboard_date_filter.py backend/tests/test_dashboard_permission_cache.py tests/test_dashboard_service.py -q
```

Expected: 全部通过。

- [ ] **Step 3: 浏览器验收**

重启本地完整栈，打开资源 `4f08e75945c3498486963e70f3c75688`：

- 4 张 ROI 图显示表达式入口，不再显示双月日期面板。
- 普通看板抽样仍显示旧双月日期面板。
- 选择“今日”后刷新成功，空数据仍为成功状态。
- 取消或关闭不刷新；失败请求保持上一次标签和数据。
- 窄卡片下入口、标题和操作按钮不重叠。

- [ ] **Step 4: 最终静态检查**

Run:

```powershell
git diff --check
git status --short
rg -n "4f08e75945c3498486963e70f3c75688|ROI看板" frontend/src/views/dashboard/components/sq-view/index.vue
```

Expected: 无空白错误、工作树仅包含计划内变更、运行时代码无 ROI 硬编码。

- [ ] **Step 5: 代码审查并修复发现**

按 P0-P3 检查状态提交、并发刷新、失败回滚、普通看板隔离、配置缺失和移动端布局；修复后重新执行 Step 1-4。
