# ROI 看板与推荐看板界面能力统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ROI 看板直接复用普通推荐看板的图表包装器和 SQL 配置抽屉，只保留 ROI 独立数据源、独立存储与 API 边界。

**Architecture:** ROI 图表通过纯函数适配为普通看板 `viewInfo/configItem`，交给 `SQComponentWrapper` 渲染；新增和编辑直接渲染 `DashboardSqlEditor`，通过固定数据源属性禁止数据源漂移，并通过异步应用钩子保存到 ROI API。现有 ROI store、后端表和图表 CRUD API 保持不变，专用卡片、日期控件和专用抽屉表单被收敛为薄适配层或删除。

**Tech Stack:** Vue 3、TypeScript、Pinia、Element Plus Secondary、Node `assert`/esbuild、vue-tsc、Vite、现有 ROI REST API。

## Global Constraints

- ROI 只保留独立数据源逻辑，以及承载该逻辑所必需的独立存储和 API 边界。
- ROI 图表仍保存到现有 ROI 表，并通过现有 ROI API 创建、更新、删除和排序。
- ROI schema、SQL 预览、刷新和保存必须固定使用当前工作空间的 ROI 数据源配置。
- 不允许回退到普通看板数据源、当前普通看板上下文或名称相似的数据源。
- 图表卡片、工具栏、全屏、解读、导出、加载态和错误态直接复用普通推荐看板组件。
- 新增和编辑直接复用普通推荐看板 SQL 配置抽屉及其配置项、预览区和底部操作区。
- 不保留 ROI 专用日期选择器、专用宽度菜单、专用工具栏或专用抽屉表单。
- 不为历史缺失字段静默选择第一列、其他轴或相似字段。
- 不修改普通推荐看板现有数据源行为；新增属性必须有保持当前行为的默认值。
- 代码注释、测试说明和提交信息使用中文。

---

## 文件结构

- `frontend/src/views/dashboard/roi/roiDashboardViewAdapter.ts`：在 `RoiChart`、普通看板 `viewInfo/configItem` 和 ROI API payload 之间做无副作用转换。
- `frontend/src/views/dashboard/roi/roiDashboardViewAdapter.test.mjs`：验证字段完整性、独立数据源注入和保存时的数据源剥离。
- `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：增加固定 SQL 数据源和异步应用钩子，默认行为保持不变。
- `frontend/src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs`：验证固定数据源不能被普通上下文覆盖，以及异步保存失败时抽屉不关闭。
- `frontend/src/views/dashboard/roi/RoiSqlEditor.vue`：删除专用表单，变为 `DashboardSqlEditor` 的 ROI 保存适配器。
- `frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`：改为验证共享抽屉复用和 ROI API 保存边界。
- `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`：增加可选刷新执行器和更多菜单插槽，默认普通看板路径不变。
- `frontend/src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs`：验证外部刷新和附加菜单契约。
- `frontend/src/views/dashboard/roi/RoiChartCard.vue`：变为 `SQComponentWrapper` 的薄包装，只连接 ROI 命令。
- `frontend/src/views/dashboard/roi/RoiChartGrid.vue`：移除日期范围和宽度变更事件，保留独立存储所需的稳定排序。
- `frontend/src/views/dashboard/roi/roiChartGridBehavior.ts`：删除专用日期占位符行为，保留刷新结果与排序合并。
- `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs`：验证共享图表包装器、统一工具栏和专用控件移除。
- `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`：改用统一页面视觉，删除日期状态和宽度命令。
- `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`：验证页面只把 ROI 数据源注入共享组件。

---

### Task 1: ROI 与普通看板视图模型适配器

**Files:**
- Create: `frontend/src/views/dashboard/roi/roiDashboardViewAdapter.ts`
- Create: `frontend/src/views/dashboard/roi/roiDashboardViewAdapter.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/types.ts`

**Interfaces:**
- Consumes: `RoiChart`、`RoiConfig`、`RoiChartCreate`、`RoiChartUpdate`。
- Produces: `roiChartToDashboardViewInfo(chart, config)`、`createRoiDashboardViewInfo(config)`、`dashboardViewInfoToRoiPayload(viewInfo, options)`、`roiChartToComponentItem(chart)`、`roiChartsToCanvasViewInfo(charts, config)`。

- [ ] **Step 1: 写适配器失败测试**

测试固定数据源、普通轴结构、查询结果、持久化 payload 和输入不变性：

```javascript
const config = { datasource_id: 8, datasource_name: 'ROI DS', can_execute: true, can_edit: true }
const chart = {
  id: '901', title: '收入 ROI', sql: 'select dt, roi from t', chart_type: 'line',
  chart_config: {
    xAxis: [{ value: 'dt' }], yAxis: [{ value: 'roi' }], series: [],
    sourceConfig: { sql: { builder: { timeField: 'dt' }, datasource: 99 } },
  },
  layout_span: 'full', sort: 1, version: 3,
  query_result: { status: 'success', fields: ['dt', 'roi'], data: [{ dt: '2026-07-22', roi: 1.2 }], message: '' },
}

const viewInfo = roiChartToDashboardViewInfo(chart, config)
assert.equal(viewInfo.datasource, 8)
assert.equal(viewInfo.sourceConfig.sql.datasource, 8)
assert.deepEqual(viewInfo.chart.xAxis, [{ value: 'dt' }])
assert.deepEqual(viewInfo.data.data, chart.query_result.data)

const payload = dashboardViewInfoToRoiPayload(viewInfo, { version: 3, layoutSpan: 'full' })
assert.equal(payload.title, '收入 ROI')
assert.equal(payload.chart_type, 'line')
assert.equal(payload.version, 3)
assert.equal(JSON.stringify(payload.chart_config).includes('"datasource":8'), false)
assert.equal(chart.chart_config.sourceConfig.sql.datasource, 99, '转换不得修改原图表')
```

同时断言新建视图固定为 SQL 来源，不包含外部 MCP 来源；历史配置缺少轴时保持空数组，不自动选列。

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/dashboard/roi/roiDashboardViewAdapter.test.mjs`

Workdir: `frontend`

Expected: FAIL，提示 `roiDashboardViewAdapter.ts` 不存在。

- [ ] **Step 3: 实现纯函数适配器**

定义最小公共类型和转换入口：

```typescript
export interface RoiDashboardViewInfo extends Record<string, any> {
  id: string
  datasource: number
  sql: string
  chart: Record<string, any>
  data: { fields: string[]; data: Array<Record<string, unknown>> }
  sourceConfig: Record<string, any>
}

export function roiChartToDashboardViewInfo(
  chart: RoiChart,
  config: RoiConfig
): RoiDashboardViewInfo

export function createRoiDashboardViewInfo(config: RoiConfig): RoiDashboardViewInfo

export function dashboardViewInfoToRoiPayload(
  viewInfo: RoiDashboardViewInfo,
  options: { version?: number; layoutSpan: RoiLayoutSpan }
): RoiChartCreate | RoiChartUpdate
```

转换时兼容已有 `x/y` 与普通 `xAxis/yAxis`，输出统一使用普通看板轴结构。复制 `sourceConfig` 后删除其中所有 datasource、tenant 和外部 MCP 认证字段，再由读取转换按当前 ROI 配置重新注入 `datasource_id`。不得修改输入对象。

- [ ] **Step 4: 运行适配器测试**

Run: `node src/views/dashboard/roi/roiDashboardViewAdapter.test.mjs`

Workdir: `frontend`

Expected: PASS，输出 `ROI dashboard view adapter tests passed`。

- [ ] **Step 5: 提交适配器**

```powershell
git add frontend/src/views/dashboard/roi/roiDashboardViewAdapter.ts frontend/src/views/dashboard/roi/roiDashboardViewAdapter.test.mjs frontend/src/views/dashboard/roi/types.ts
git commit -m "重构：增加 ROI 普通看板视图适配器"
```

---

### Task 2: 普通 SQL 抽屉支持固定数据源和异步保存

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`
- Create: `frontend/src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs`

**Interfaces:**
- Consumes: 当前 `modelValue`、`viewInfo`、`dashboardInfo` 和 `canEditSql` props。
- Produces: 可选 props `fixedDatasourceId?: number | string | null`、`allowExternalSources?: boolean`、`applyExecutor?: (viewInfo: any) => Promise<boolean>`；默认值分别为 `null`、`true`、`undefined`。

- [ ] **Step 1: 写固定数据源失败测试**

源码契约和可独立打包的行为测试必须覆盖：

```javascript
assert.match(source, /fixedDatasourceId\?: number \| string \| null/)
assert.match(source, /allowExternalSources\?: boolean/)
assert.match(source, /applyExecutor\?: \(viewInfo: any\) => Promise<boolean>/)
assert.match(source, /const effectiveDatasourceId = computed/)
assert.match(source, /props\.fixedDatasourceId \?\? props\.viewInfo\?\.datasource/)
assert.match(source, /if \(!props\.allowExternalSources\)[\s\S]*sourceTypes[\s\S]*\['sql'\]/)
assert.match(source, /const applied = await props\.applyExecutor\(props\.viewInfo\)/)
assert.match(source, /if \(!applied\) return/)
```

同时断言所有 SQL schema 和预览请求使用 `effectiveDatasourceId`，而不是在固定模式下重新读取普通看板 datasource；普通模式仍保留 `dashboardApi.preview_sql`。

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs`

Workdir: `frontend`

Expected: FAIL，提示固定数据源属性不存在。

- [ ] **Step 3: 实现固定数据源模式**

增加默认保持兼容的 props：

```typescript
fixedDatasourceId?: number | string | null
allowExternalSources?: boolean
applyExecutor?: (viewInfo: any) => Promise<boolean>
```

```typescript
const effectiveDatasourceId = computed(
  () => props.fixedDatasourceId ?? props.viewInfo?.datasource ?? null
)
```

固定模式打开时把 `viewInfo.datasource` 和 `sourceConfig.sql.datasource` 写为
`effectiveDatasourceId`。`allowExternalSources=false` 时来源恒为 `['sql']`，隐藏 MCP 来源入口和
SQL 来源关闭控件，但保留其余普通图表配置、SQL、透视、洞察、预测和预览能力。

- [ ] **Step 4: 实现异步应用门禁**

把 `applyChange()` 改为异步，并新增独立 `applying` 状态：

```typescript
async function applyChange() {
  if (!props.viewInfo || applying.value || !validateBeforeApply()) return
  const written = writeEditorStateToViewInfo({ emit: false, close: false, notify: false })
  if (!written) return
  applying.value = true
  try {
    if (props.applyExecutor && !(await props.applyExecutor(props.viewInfo))) return
    emits('applied', props.viewInfo)
    visible.value = false
    ElMessage.success(t('dashboard.sql_editor_applied'))
  } finally {
    applying.value = false
  }
}
```

底部应用按钮使用 `:loading="applying"`；异步保存返回 `false` 或抛错时保持抽屉打开，且不得发出 `applied`。没有 `applyExecutor` 时行为与当前普通看板一致。

- [ ] **Step 5: 运行抽屉定向测试**

Run: `node src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs`

Run: `node src/views/dashboard/common/DashboardSqlEditor.preview-persistence.test.mjs`

Run: `node src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs`

Workdir: `frontend`

Expected: PASS；固定数据源门禁和现有预览行为均通过。

- [ ] **Step 6: 提交共享抽屉能力**

```powershell
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs
git commit -m "重构：SQL 抽屉支持固定数据源保存"
```

---

### Task 3: ROI 编辑器直接复用普通 SQL 抽屉

**Files:**
- Modify: `frontend/src/views/dashboard/roi/RoiSqlEditor.vue`
- Modify: `frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/roiChartConfig.ts`
- Modify: `frontend/src/views/dashboard/roi/roiChartConfig.test.mjs`
- Delete: `frontend/src/views/dashboard/roi/roiChartPreviewRunner.ts`

**Interfaces:**
- Consumes: Task 1 的视图适配器、Task 2 的固定数据源和 `applyExecutor`。
- Produces: `RoiSqlEditor` 保持现有 `modelValue/dashboardId/chart/canEdit` props 与 `saved/cancelled` 事件，内部不再包含任何专用表单。

- [ ] **Step 1: 改写 ROI 编辑器失败测试**

断言：

```javascript
assert.match(source, /import DashboardSqlEditor from '@\/views\/dashboard\/common\/DashboardSqlEditor\.vue'/)
assert.match(source, /:fixed-datasource-id="config\?\.datasource_id"/)
assert.match(source, /:allow-external-sources="false"/)
assert.match(source, /:apply-executor="persistRoiChart"/)
assert.doesNotMatch(source, /<el-drawer|<el-tabs|<el-form|<el-date-picker/)
assert.doesNotMatch(source, /chartTypes|insightComparisonOptions|roi-sql-editor__/)
```

通过 esbuild 测试 `persistRoiChart` 的依赖注入版本：新建调用 `createChart`，编辑调用
`updateChart` 并携带当前版本；API 失败返回 `false`，不触发 `saved`。

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: FAIL，当前文件仍包含专用 `el-drawer` 和专用配置表单。

- [ ] **Step 3: 将 ROI 编辑器收敛为适配器**

`RoiSqlEditor.vue` 只负责：

```vue
<DashboardSqlEditor
  v-model="visible"
  :view-info="draftViewInfo"
  :dashboard-info="dashboardInfo"
  :can-edit-sql="canEdit"
  :fixed-datasource-id="config?.datasource_id"
  :allow-external-sources="false"
  :apply-executor="persistRoiChart"
  @applied="handleApplied"
/>
```

打开时用 Task 1 适配器创建深拷贝草稿。`persistRoiChart(viewInfo)` 转换 payload 后调用现有
`roiDashboardApi.createChart/updateChart`；成功保存返回 `true` 并暂存响应，失败显示现有
`409` 或通用错误后返回 `false`。`handleApplied()` 只在 API 成功后发出 `saved`。

- [ ] **Step 4: 删除专用配置与预览状态**

从 `roiChartConfig.ts` 删除已经由普通抽屉承担的表单 hydration、专用映射校验和请求门禁，
仅保留仍被 API 错误展示使用的 `getRoiChartSaveErrorMessage()`。删除
`roiChartPreviewRunner.ts` 及对应专用测试引用。Panel 不再维护专用预览生命周期。

- [ ] **Step 5: 运行 ROI 抽屉测试**

Run: `node src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs`

Run: `node src/views/dashboard/roi/roiChartConfig.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: PASS；ROI 源码中没有第二套抽屉，保存仍只调用 ROI API。

- [ ] **Step 6: 提交 ROI 抽屉复用**

```powershell
git add frontend/src/views/dashboard/roi/RoiSqlEditor.vue frontend/src/views/dashboard/roi/RoiSqlEditor.isolation.test.mjs frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs frontend/src/views/dashboard/roi/roiChartConfig.ts frontend/src/views/dashboard/roi/roiChartConfig.test.mjs frontend/src/views/dashboard/roi/roiChartPreviewRunner.ts
git commit -m "重构：ROI 图表复用普通配置抽屉"
```

---

### Task 4: 普通图表包装器支持 ROI 外部命令

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Create: `frontend/src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.refresh-state.test.mjs`

**Interfaces:**
- Consumes: 当前 `configItem/canvasViewInfo/dashboardInfo/showPosition` props。
- Produces: 可选 `refreshExecutor?: () => Promise<void>`、`refreshing?: boolean` props；`more-actions` 插槽。未传入时继续执行普通看板原刷新逻辑。

- [ ] **Step 1: 写外部命令失败测试**

断言共享包装器提供：

```javascript
assert.match(source, /refreshExecutor\?: \(\) => Promise<void>/)
assert.match(source, /refreshing\?: boolean/)
assert.match(source, /if \(props\.refreshExecutor\)[\s\S]*await props\.refreshExecutor\(\)/)
assert.match(source, /<slot name="more-actions"/)
assert.match(source, /:loading="refreshing"/)
```

同时断言现有 `dashboardApi.preview_sql`、混合数据刷新、全屏、解读、导出和移动逻辑仍存在。

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs`

Workdir: `frontend`

Expected: FAIL，当前包装器没有外部刷新执行器和更多菜单插槽。

- [ ] **Step 3: 实现兼容扩展**

在 `refreshChartData()` 最前面增加受控路径：

```typescript
if (props.refreshExecutor) {
  if (props.refreshing) return
  await props.refreshExecutor()
  return
}
```

刷新按钮绑定统一的 loading/disabled 状态。在导出、移动菜单项之后加入：

```vue
<slot name="more-actions" :view-info="currentViewInfo" />
```

没有插槽和执行器时，生成 DOM 和行为与当前普通看板保持一致。

- [ ] **Step 4: 运行包装器回归测试**

Run: `node src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs`

Run: `node src/views/dashboard/preview/SQComponentWrapper.refresh-state.test.mjs`

Run: `node src/views/dashboard/preview/SQComponentWrapper.fullscreen-actions.test.mjs`

Workdir: `frontend`

Expected: PASS；普通刷新和 ROI 受控刷新两条路径均被覆盖。

- [ ] **Step 5: 提交共享图表扩展**

```powershell
git add frontend/src/views/dashboard/preview/SQComponentWrapper.vue frontend/src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs frontend/src/views/dashboard/preview/SQComponentWrapper.refresh-state.test.mjs
git commit -m "重构：图表包装器支持外部刷新命令"
```

---

### Task 5: ROI 卡片和页面切换到普通看板组件

**Files:**
- Modify: `frontend/src/views/dashboard/roi/RoiChartCard.vue`
- Modify: `frontend/src/views/dashboard/roi/RoiChartGrid.vue`
- Modify: `frontend/src/views/dashboard/roi/roiChartGridBehavior.ts`
- Modify: `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/types.ts`

**Interfaces:**
- Consumes: Task 1 的 `viewInfo/configItem` 转换和 Task 4 的受控包装器。
- Produces: ROI 卡片展示、工具栏、解读、刷新、全屏和导出均由 `SQComponentWrapper` 提供；ROI 只在更多菜单注入编辑和删除。

- [ ] **Step 1: 写共享卡片失败测试**

把旧专用控件断言替换为：

```javascript
assert.match(card, /import SQComponentWrapper from '@\/views\/dashboard\/preview\/SQComponentWrapper\.vue'/)
assert.match(card, /<SQComponentWrapper/)
assert.match(card, /:refresh-executor="refreshCurrentChart"/)
assert.match(card, /#more-actions/)
assert.match(card, /emit\('edit', chart\)/)
assert.match(card, /emit\('remove', chart\)/)
assert.doesNotMatch(card, /<el-date-picker|Grid|Rank|RefreshRight|roi-chart-card__actions/)
assert.doesNotMatch(grid, /date-range-change|span-change|chartDateRanges/)
assert.doesNotMatch(panel, /chartDateRanges|changeChartDateRange|changeChartSpan/)
```

还要断言 `RoiChartCard` 向包装器传入的 `dashboardInfo.datasource` 与 `viewInfo.datasource` 都等于
`config.datasource_id`，且不读取普通 dashboard store。

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/dashboard/roi/RoiChartGrid.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Workdir: `frontend`

Expected: FAIL，当前 ROI 卡片仍包含日期选择器、独立刷新按钮和宽度菜单。

- [ ] **Step 3: 改造 ROI 卡片**

`RoiChartCard` 使用 Task 1 生成的对象：

```vue
<SQComponentWrapper
  :config-item="componentItem"
  :canvas-view-info="canvasViewInfo"
  :dashboard-info="dashboardInfo"
  show-position="preview"
  :refresh-executor="refreshCurrentChart"
  :refreshing="refreshing"
>
  <template #more-actions>
    <el-dropdown-item v-if="actionEnabled" @click="emit('edit', chart)">编辑</el-dropdown-item>
    <el-dropdown-item v-if="actionEnabled" divided @click="emit('remove', chart)">删除</el-dropdown-item>
  </template>
</SQComponentWrapper>
```

卡片不得复制 `.wrapper-outer`、`.preview-chart-actions` 或抽屉样式，只允许设置承载组件所需的
`width/height/min-width/min-height`。

- [ ] **Step 4: 删除 ROI 专用日期和宽度交互**

从 Grid、Panel、types 和 `roiChartGridBehavior.ts` 删除 `RoiDateRange`、
`defaultRoiDateRange()`、`hasRoiDateRangePlaceholders()`、`date-range-change` 和 `span-change`。
刷新只发送当前图表 SQL/config 到 ROI 预览接口；历史 SQL 若仍包含未配置占位符，接口错误必须按
统一错误态显示，不自动填充日期。

排序继续使用已有 `sort/layout_span/version`，但页面不再提供 ROI 专用宽度菜单。现有
`layout_span` 只用于兼容历史网格占宽。

- [ ] **Step 5: 统一 ROI 页面视觉**

Panel 使用普通预览页面的背景变量、标题字号、16px 内容留白和卡片间距；删除数据源副标题。
“添加图表”保留为 ROI 管理入口，但使用普通看板主按钮规格。空状态、权限状态和加载状态沿用
普通页面颜色、字号和最小高度。

- [ ] **Step 6: 运行 ROI 页面回归测试**

Run: `node src/views/dashboard/roi/RoiChartGrid.test.mjs`

Run: `node src/views/dashboard/roi/RoiDashboardPanel.test.mjs`

Run: `node src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs`

Workdir: `frontend`

Expected: PASS；源码只保留一个图表包装器和一个配置抽屉实现。

- [ ] **Step 7: 提交页面统一**

```powershell
git add frontend/src/views/dashboard/roi/RoiChartCard.vue frontend/src/views/dashboard/roi/RoiChartGrid.vue frontend/src/views/dashboard/roi/roiChartGridBehavior.ts frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs frontend/src/views/dashboard/roi/types.ts
git commit -m "功能：统一 ROI 与推荐看板图表界面"
```

---

### Task 6: 完整回归和浏览器验收

**Files:**
- Modify only if verification exposes defects in files listed by Tasks 1-5.

**Interfaces:**
- Consumes: 共享抽屉、共享包装器、ROI 适配器和现有 ROI API。
- Produces: 测试、构建、运行态和视觉验收证据。

- [ ] **Step 1: 运行 ROI 全部前端测试**

Run:

```powershell
Get-ChildItem src -Recurse -Filter '*roi*.test.mjs' | ForEach-Object {
  node $_.FullName
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Workdir: `frontend`

Expected: exit code 0，所有 ROI 测试通过。

- [ ] **Step 2: 运行共享组件定向回归**

Run:

```powershell
node src/views/dashboard/common/DashboardSqlEditor.fixed-datasource.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.preview-persistence.test.mjs
node src/views/dashboard/common/DashboardSqlEditor.preview-fields.test.mjs
node src/views/dashboard/preview/SQComponentWrapper.external-actions.test.mjs
node src/views/dashboard/preview/SQComponentWrapper.refresh-state.test.mjs
node src/views/dashboard/preview/SQComponentWrapper.fullscreen-actions.test.mjs
```

Workdir: `frontend`

Expected: 每个命令 exit code 0，无失败断言。

- [ ] **Step 3: 运行类型检查和生产构建**

Run: `npm run build`

Workdir: `frontend`

Expected: `vue-tsc -b` 和 Vite build 均成功，exit code 0。

- [ ] **Step 4: 启动或重启本地四服务**

按 `starting-chat-bi-local` Skill 执行本地重启，覆盖前端 `5173`、API `8000`、MCP `8001`
和一个使用同一 `local-*` 队列的 Worker，并核对：

```text
LLM_REQUEST_TIMEOUT=120
LLM_TASK_MAX_WAIT_SECONDS=900
LLM_MAX_RETRIES=1
```

Expected: 前端 HTTP 200；API 登录方法 200 或 401；三个端口监听；Worker 使用隔离队列。

- [ ] **Step 5: 浏览器桌面验收**

使用 `browser:control-in-app-browser` 对同一工作空间的普通推荐看板和 ROI 看板截图对比：

- 页面背景、标题、留白、卡片边框、圆角、阴影和间距一致；
- ROI 工具栏显示解读、刷新、全屏、更多，悬停和禁用态一致；
- 更多菜单包含普通导出能力和 ROI 编辑/删除命令；
- 新增/编辑打开与普通看板相同的 720px 抽屉；
- 抽屉的标签、表单、预览和底部按钮无第二套 ROI 样式；
- 页面无重叠、截断、横向溢出或空白画布。

- [ ] **Step 6: 浏览器窄屏验收**

在宽度 `390px` 的视口重复检查卡片工具栏、全屏入口和抽屉。Expected: 工具栏不覆盖标题，
抽屉宽度不超过视口，内容和底部按钮可滚动访问。

- [ ] **Step 7: 验证独立数据源与 API 边界**

在浏览器网络面板执行一次 ROI 新增、预览、刷新和编辑：

- 图表创建/更新/刷新请求使用 `/dashboard/roi/...`；
- schema 和普通 SQL 预览请求的 datasource 等于 ROI 配置的 `datasource_id`；
- 请求中不存在当前普通看板 datasource ID；
- 切换普通看板后返回 ROI，ROI 执行数据源不变。

- [ ] **Step 8: 检查最终差异**

Run: `git diff --check`

Run: `git status --short`

Expected: 无空白错误；不包含日志、运行时文件或任务无关的用户修改。

- [ ] **Step 9: 提交验证阶段修复（仅在产生修复时）**

```powershell
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/preview/SQComponentWrapper.vue frontend/src/views/dashboard/roi
git commit -m "修复：完善 ROI 界面统一回归问题"
```

若验证未产生新改动，不创建空提交。
