# 图表生成器默认时间范围 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建或缺少已保存时间字段的图表默认选择业务日期/分区日期，并保持按天、过去 30 天。

**Architecture:** 将通用时间字段优先级放入现有 `builderFieldPickerOptions.ts`，由纯函数根据字段角色和展示元数据排序；`DashboardSqlEditor.vue` 只负责在当前时间字段为空时调用该函数。已有保存配置继续走原回填路径，不增加兼容回退。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert`

## Global Constraints

- 不按数据源名称、表名或具体物理字段名硬编码。
- 不覆盖已保存的 `timeField`。
- `timeGrain = 'day'` 和 `timeRange = '30d'` 保持不变。
- 无业务日期或分区日期时继续优先事件日期。

---

### Task 1: 通用默认时间字段优先级

**Files:**
- Modify: `frontend/src/views/dashboard/common/builderFieldPickerOptions.ts`
- Modify: `frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`

**Interfaces:**
- Consumes: `FieldOption[]`，包含字段标签、显示名、注释、物理字段值和可选 `fieldRole`。
- Produces: `preferredBuilderTimeField(options: FieldOption[]): string`，返回优先候选的 `value`，无候选时返回空字符串。

- [x] **Step 1: Write the failing test**

在 `builderFieldPickerOptions.test.mjs` 增加真实函数断言：

```js
assert.equal(
  options.preferredBuilderTimeField([
    { label: '事件日期', value: 'event.event_date', table: 'event', field: 'event_date' },
    { label: '业务日期（分区字段）', value: 'event.dt', table: 'event', field: 'dt', fieldRole: 'partition_date' },
  ]),
  'event.dt'
)

assert.equal(
  options.preferredBuilderTimeField([
    { label: '创建时间', value: 'event.created_at', table: 'event', field: 'created_at' },
    { label: '事件日期', value: 'event.event_date', table: 'event', field: 'event_date' },
  ]),
  'event.event_date'
)
```

- [x] **Step 2: Run test to verify it fails**

Run: `node frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs`

Expected: FAIL，提示 `preferredBuilderTimeField is not a function`。

- [x] **Step 3: Write minimal implementation**

在 `FieldOption` 增加 `fieldRole?: string`，并实现：

```ts
export function preferredBuilderTimeField(options: FieldOption[]) {
  return options
    .map((option, index) => ({ option, index, priority: builderTimeFieldPriority(option) }))
    .sort((left, right) => left.priority - right.priority || left.index - right.index)[0]?.option.value || ''
}
```

优先级依次为分区/业务日期、事件日期、事件时间、普通日期、普通时间、其他字段。编辑器映射 `field_role`/`fieldRole`，删除组件内重复排序函数并调用导入函数。

- [x] **Step 4: Run focused tests to verify they pass**

Run:

```powershell
node frontend/src/views/dashboard/common/builderFieldPickerOptions.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

Expected: 两个命令均退出码 0。

- [x] **Step 5: Run build and diff checks**

Run:

```powershell
npm --prefix frontend run build
git diff --check
```

Expected: 构建成功且 `git diff --check` 无输出。
