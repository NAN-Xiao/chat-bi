# 字段权限保存数组契约修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复权限规则保存时把字段权限数组转换成字符串的回归，并保持后端严格数组校验。

**Architecture:** 在现有 `permissionFieldEntries.ts` 中增加一个纯载荷转换函数，统一生成 `column`、`row`、`table` 三类权限的结构化请求。权限页面只调用该函数，后端验证和持久化逻辑保持不变。

**Tech Stack:** Vue 3、TypeScript 5.7、Node.js assert、FastAPI、pytest

## Global Constraints

- 后端继续严格要求字段权限为数组，不兼容旧字符串格式。
- 不修改 SQL 权限判定、历史结果重检、行权限注入和数据库存储格式。
- 不根据字段名称推断权限，不增加静默兼容回退。
- 保留工作区中与本任务无关的现有改动。

---

### Task 1: 结构化权限保存载荷

**Files:**
- Modify: `frontend/src/views/system/permission/permissionFieldEntries.ts`
- Modify: `frontend/src/views/system/permission/index.vue:580-604`
- Test: `frontend/scripts/check-permission-json-subfields.mjs`

**Interfaces:**
- Consumes: 权限页面中的规则明细数组，每项包含 `type`、`permissions`、`expression_tree` 及原有元数据。
- Produces: `permissionRulesToSaveEntries(entries)`，返回可直接提交给 `/ds_permission/save` 的结构化规则明细数组。

- [ ] **Step 1: 编写失败测试**

在 `frontend/scripts/check-permission-json-subfields.mjs` 中导入 `permissionRulesToSaveEntries`，增加以下断言：

```javascript
const sourceEntries = [{
  id: 34,
  type: 'column',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: {},
}, {
  id: 35,
  type: 'row',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: { logic: 'and', items: [] },
}, {
  id: 36,
  type: 'table',
  permissions: [{ field_id: 101, field_name: 'uid', field_comment: '', enable: true }],
  expression_tree: { stale: true },
}]

const saveEntries = permissionRulesToSaveEntries(sourceEntries)
assert.equal(Array.isArray(saveEntries[0].permissions), true)
assert.deepEqual(saveEntries[0].permissions, sourceEntries[0].permissions)
assert.deepEqual(saveEntries[0].expression_tree, {})
assert.deepEqual(saveEntries[1].permissions, [])
assert.deepEqual(saveEntries[1].expression_tree, sourceEntries[1].expression_tree)
assert.deepEqual(saveEntries[2].permissions, [])
assert.deepEqual(saveEntries[2].expression_tree, {})
assert.deepEqual(saveEntries.map((entry) => entry.permission_list), [[], [], []])
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `npm run test:permission-json-fields`（工作目录：`frontend`）

Expected: FAIL，因为 `permissionRulesToSaveEntries` 尚未导出或不是函数。

- [ ] **Step 3: 实现最小载荷转换函数**

在 `frontend/src/views/system/permission/permissionFieldEntries.ts` 增加：

```typescript
export interface PermissionRuleSaveEntry {
  type?: string
  permissions?: PermissionFieldEntry[]
  permission_list?: unknown[]
  expression_tree?: Record<string, unknown>
  [key: string]: unknown
}

export const permissionRulesToSaveEntries = <T extends PermissionRuleSaveEntry>(
  entries: T[]
): T[] =>
  entries.map((entry) => ({
    ...entry,
    permissions: entry.type === 'column' ? entry.permissions || [] : [],
    permission_list: [],
    expression_tree: entry.type === 'row' ? entry.expression_tree || {} : {},
  }))
```

在 `frontend/src/views/system/permission/index.vue` 导入该函数，并把现有 `permissions.map` 与 `JSON.stringify` 转换替换为：

```typescript
const permissionsObj = permissionRulesToSaveEntries(permissions)
```

- [ ] **Step 4: 运行前端专项测试并确认通过**

Run: `npm run test:permission-json-fields`（工作目录：`frontend`）

Expected: PASS，进程退出码为 0。

- [ ] **Step 5: 运行后端权限专项测试**

Run: `.\backend\.venv\Scripts\python.exe -m pytest tests/test_datasource_permission_roles.py -q`

Expected: PASS，JSON 子字段保存、物理字段身份校验和 SQL 权限范围测试全部通过。

- [ ] **Step 6: 构建前端**

Run: `npm run build`（工作目录：`frontend`）

Expected: `vue-tsc` 与 Vite 构建均成功，进程退出码为 0。

- [ ] **Step 7: 本地页面与权限行为复测**

1. 使用工作空间管理员编辑规则“禁止查看金额相关字段”。
2. 将 `event.personal.money` 设置为不可见并保存。
3. 确认不再出现“字段权限配置必须是列表”。
4. 使用 `dongjinchao_t1` 请求 ARPU，确认返回权限拒绝。
5. 打开 `record_id=495`，确认历史金额结果不再返回。

- [ ] **Step 8: 提交实现**

```powershell
git add -- frontend/src/views/system/permission/permissionFieldEntries.ts frontend/src/views/system/permission/index.vue frontend/scripts/check-permission-json-subfields.mjs docs/superpowers/plans/2026-07-13-permission-save-array-contract.md
git commit -m "修复：保持字段权限保存数组契约"
```
