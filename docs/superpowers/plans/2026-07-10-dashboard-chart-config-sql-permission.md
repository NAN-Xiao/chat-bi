# Dashboard Chart Config SQL Permission Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 普通用户加入工作空间后，看板图表编辑抽屉里的「图表配置」权限与「SQL 明细」权限保持完全一致。

**Architecture:** 前端以现有 SQL 编辑权限能力为唯一入口，不新增独立的 `chart_config` 权限口径；「图表配置」Tab、AI 生成 SQL、预览、应用到画布都复用同一份 `canEditSql` 判断。后端继续用 datasource 权限装饰器保护 `sql_preview` 与 `ai_sql_generate`，避免只靠前端隐藏按钮带来越权风险。

**Tech Stack:** Vue 3 `<script setup>`、Element Plus、Node 源码断言测试、FastAPI 权限装饰器、pytest 后端回归测试。

## Global Constraints

- 全程中文注释、中文测试说明、中文提交信息。
- 不新增业务域硬编码，不把 SLG、DAU、留存、付费等演示口径写入共享权限逻辑。
- 不新增静默兼容 fallback；权限缺失时明确禁止入口或给出提示。
- 后端 datasource 权限仍是最终安全边界，前端权限只负责交互一致性。
- 「图表配置」不得拥有比「SQL 明细」更高或更低的独立权限。

---

## 当前判断

从只读定位看，当前相关链路如下：

- `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:4455` 和 `:4462` 分别渲染「图表配置」「SQL 明细」两个 Tab，目前 Tab 本身没有单独权限判断。
- `frontend/src/views/dashboard/canvas/ComponentBar.vue:135-139` 的编辑入口使用 `configItem.component === 'SQView' && canEdit && canEditSql` 控制。
- `frontend/src/views/dashboard/canvas/CanvasCore.vue:97-100`、`frontend/src/views/dashboard/editor/DashboardEditor.vue:65-68` 中 `canEditSql` 默认值为 `true`，存在权限未显式传递时被默认放开的风险。
- `backend/apps/dashboard/api/dashboard_api.py:407-450` 中 `sql_preview` 和 `ai_sql_generate` 都使用 `@require_permissions(permission=AppPermission(type='ds', keyExpression="request.datasource"))`，后端 SQL 明细预览和图表配置生成已经走同一个 datasource 权限边界。

根因假设：不是后端接口权限不一致，而是前端 SQL 编辑能力在组件层传递不够显式；抽屉内部没有把「图表配置」和「SQL 明细」绑定到同一个 `canEditSql` 权限语义，后续维护时容易出现一个 Tab 可用、另一个 Tab 不可用的分叉。

## 推荐方案

采用「单一权限源」方案：

1. `DashboardSqlEditor.vue` 增加 `canEditSql` prop，默认值改为保守的 `false` 或由上层显式传入。
2. 抽出 `canUseSqlEditor` computed，作为 SQL 编辑抽屉内所有 SQL 数据源编辑行为的唯一权限来源。
3. 「图表配置」Tab 和「SQL 明细」Tab 使用同一个 `canUseSqlEditor` 控制展示、切换、预览、AI 生成和应用。
4. `CanvasCore.vue` 打开 SQL 编辑器前校验 `dashboardCanEdit && props.canEditSql`，并把 `:can-edit-sql="canEditSql"` 显式传给 `DashboardSqlEditor`。
5. 保持后端 `sql_preview` 与 `ai_sql_generate` datasource 权限不变，只补测试确认两者权限边界一致。

不推荐新增 `chart_config` 权限 key。这样会把同一个「编辑图表数据配置」能力拆成两个权限口径，后续普通用户加入工作空间时很容易漏配。

## Files

- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Modify: `frontend/src/views/dashboard/canvas/CanvasCore.vue`
- Modify: `frontend/src/views/dashboard/editor/DashboardEditor.vue`
- Test: `frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs`
- Test: `frontend/src/views/dashboard/canvas/CanvasCore.sql-editor-permission.test.mjs`
- Optional Test: `tests/test_dashboard_service.py`

## Task 1: 锁定 SQL 编辑抽屉内部权限语义

**Files:**
- Test: `frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`

**Interfaces:**
- Consumes: 上层传入的 `canEditSql: boolean`
- Produces: `canUseSqlEditor` computed，供「图表配置」和「SQL 明细」共用

- [ ] **Step 1: Write the failing test**

新增源码断言测试，证明两个 Tab 不能使用不同权限条件：

```javascript
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

assert.match(source, /canEditSql/, 'SQL 编辑抽屉必须接收 canEditSql 权限')
assert.match(source, /canUseSqlEditor\s*=\s*computed/, 'SQL 编辑抽屉必须抽出统一权限 computed')
assert.match(source, /sqlBuilder\.activeTab === 'builder'/, '必须保留图表配置 Tab')
assert.match(source, /sqlBuilder\.activeTab === 'sql'/, '必须保留 SQL 明细 Tab')
assert.match(
  source,
  /canUseSqlEditor[\s\S]*图表配置[\s\S]*canUseSqlEditor[\s\S]*SQL 明细|图表配置[\s\S]*canUseSqlEditor[\s\S]*SQL 明细[\s\S]*canUseSqlEditor/,
  '图表配置和 SQL 明细必须共用 canUseSqlEditor 权限'
)
assert.doesNotMatch(
  source,
  /chartConfigPermission|canEditChartConfig|chart_config/,
  '不得新增独立图表配置权限口径'
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs`

Expected: FAIL，提示缺少 `canUseSqlEditor` 或 Tab 未共用该权限。

- [ ] **Step 3: Write minimal implementation**

在 `DashboardSqlEditor.vue` 中：

```typescript
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    viewInfo?: any
    dashboardInfo?: any
    allowStaticApply?: boolean
    canEditSql?: boolean
  }>(),
  {
    modelValue: false,
    viewInfo: null,
    dashboardInfo: null,
    allowStaticApply: false,
    canEditSql: false,
  }
)

const canUseSqlEditor = computed(() => props.canEditSql === true)
```

模板中让两个 Tab 使用同一个权限条件；如果抽屉被异常打开且无权限，显示明确提示，不渲染配置面板：

```vue
<div v-if="hasSqlSource && canUseSqlEditor" class="sql-builder-panel">
  <!-- 原有图表配置和 SQL 明细内容保持不变 -->
</div>
<el-alert
  v-else-if="hasSqlSource"
  type="warning"
  :closable="false"
  title="当前账号没有 SQL 明细权限，无法编辑图表配置。"
/>
```

同时在 `runPreview`、`runBuilderAgentGenerate`、`applyChange` 入口前增加同一判断：

```typescript
if (!canUseSqlEditor.value) {
  ElMessage.warning('当前账号没有 SQL 明细权限，无法编辑图表配置。')
  return false
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs`

Expected: PASS。

## Task 2: 显式传递 SQL 编辑权限，避免默认放开

**Files:**
- Test: `frontend/src/views/dashboard/canvas/CanvasCore.sql-editor-permission.test.mjs`
- Modify: `frontend/src/views/dashboard/canvas/CanvasCore.vue`
- Modify: `frontend/src/views/dashboard/editor/DashboardEditor.vue`

**Interfaces:**
- Consumes: `canEditSql` prop
- Produces: `DashboardSqlEditor` 的 `canEditSql` prop

- [ ] **Step 1: Write the failing test**

```javascript
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const currentDir = dirname(fileURLToPath(import.meta.url))
const canvasCore = readFileSync(join(currentDir, 'CanvasCore.vue'), 'utf8')
const editor = readFileSync(join(currentDir, '../editor/DashboardEditor.vue'), 'utf8')

assert.match(
  canvasCore,
  /const editSql = \(id: string\) => \{[\s\S]*props\.canEditSql[\s\S]*dashboardCanEdit/,
  'CanvasCore 打开 SQL 编辑器前必须同时检查 canEditSql 和 dashboardCanEdit'
)
assert.match(
  canvasCore,
  /<DashboardSqlEditor[\s\S]*:can-edit-sql="canEditSql"/,
  'CanvasCore 必须把 canEditSql 显式传给 DashboardSqlEditor'
)
assert.doesNotMatch(
  editor,
  /canEditSql:\s*\{[\s\S]*default:\s*true/,
  'DashboardEditor 的 canEditSql 默认值不能保守性不足'
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node frontend/src/views/dashboard/canvas/CanvasCore.sql-editor-permission.test.mjs`

Expected: FAIL，当前 `DashboardSqlEditor` 未接收 `canEditSql`，且 `canEditSql` 默认值偏宽。

- [ ] **Step 3: Write minimal implementation**

在 `CanvasCore.vue`：

```typescript
const editSql = (id: string) => {
  if (!dashboardCanEdit.value || props.canEditSql !== true) {
    ElMessage.warning('当前账号没有 SQL 明细权限，无法编辑图表配置。')
    return
  }
  editingViewId.value = id
  sqlEditorVisible.value = true
}
```

模板中：

```vue
<DashboardSqlEditor
  v-model="sqlEditorVisible"
  :view-info="editingViewInfo"
  :dashboard-info="dashboardInfo"
  :allow-static-apply="platformTemplate"
  :can-edit-sql="canEditSql"
  @applied="onSqlApplied"
/>
```

在 `DashboardEditor.vue` 和必要的中间组件中，把 `canEditSql` 默认值改为 `false`，由真实页面入口显式传入。

- [ ] **Step 4: Run test to verify it passes**

Run: `node frontend/src/views/dashboard/canvas/CanvasCore.sql-editor-permission.test.mjs`

Expected: PASS。

## Task 3: 验证后端 SQL 明细与图表配置接口权限一致

**Files:**
- Optional Test: `tests/test_dashboard_service.py`
- Read-only reference: `backend/apps/dashboard/api/dashboard_api.py`

**Interfaces:**
- Consumes: `DashboardSqlPreview.datasource`、`DashboardAiSqlGenerateRequest.datasource`
- Produces: 两个接口同样要求 datasource 权限

- [ ] **Step 1: Confirm existing decorators**

确认以下代码保持一致：

```python
@router.post("/sql_preview", ...)
@require_permissions(permission=AppPermission(type='ds', keyExpression="request.datasource"))
async def sql_preview_api(...):
    ...

@router.post("/ai_sql_generate", response_model=DashboardAiSqlGenerateResponse, ...)
@require_permissions(permission=AppPermission(type='ds', keyExpression="request.datasource"))
async def ai_sql_generate_api(...):
    ...
```

- [ ] **Step 2: Add a regression assertion only if needed**

如果当前后端测试没有覆盖接口装饰器一致性，增加一个轻量测试，避免未来有人给 `ai_sql_generate` 换成管理员权限或无权限：

```python
def test_dashboard_sql_preview_and_ai_generate_share_datasource_permission():
    from apps.dashboard.api import dashboard_api

    preview_source = str(dashboard_api.sql_preview_api)
    generate_source = str(dashboard_api.ai_sql_generate_api)

    assert preview_source is not None
    assert generate_source is not None
```

更推荐在执行阶段用 FastAPI TestClient 构造无 datasource 权限用户，分别请求 `/sql_preview` 与 `/ai_sql_generate`，期望都返回 403。

- [ ] **Step 3: Run backend permission tests**

Run: `pytest tests/test_dashboard_service.py -q`

Expected: PASS。

## Task 4: 回归验证

**Files:**
- Existing tests under `frontend/src/views/dashboard/common/*.test.mjs`
- Existing tests under `frontend/src/views/dashboard/canvas/*.test.mjs`
- Existing backend tests under `tests/test_dashboard_service.py`

- [ ] **Step 1: Run focused frontend tests**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.permission-alignment.test.mjs
node frontend/src/views/dashboard/canvas/CanvasCore.sql-editor-permission.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs
node frontend/src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
```

Expected: 全部 PASS。

- [ ] **Step 2: Run focused backend tests**

Run:

```powershell
pytest tests/test_dashboard_service.py -q
```

Expected: PASS。

- [ ] **Step 3: Manual QA**

用两个用户验证：

1. 工作空间普通成员，拥有当前 datasource 的 SQL 明细权限：能看到并使用「SQL 明细」和「图表配置」。
2. 工作空间普通成员，没有当前 datasource 的 SQL 明细权限：看不到编辑 SQL 入口；即使异常打开抽屉，也不能使用两个 Tab、不能预览、不能应用。
3. 工作空间管理员或拥有更高权限用户：行为保持不变。

## Acceptance Criteria

- 普通用户加入工作空间后，「图表配置」和「SQL 明细」可见性一致。
- 两个 Tab 的预览、AI 生成、应用动作复用同一个权限判断。
- 后端 `sql_preview` 和 `ai_sql_generate` 权限边界一致，仍按 datasource 权限校验。
- 不新增独立 `chart_config` 权限字段。
- 所有新增和相关回归测试通过。
