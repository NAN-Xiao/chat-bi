# 看板图表类型快捷切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在普通看板图表卡片和“从问答记录添加图表”抽屉中提供一致的图表类型快捷切换，并按看板编辑权限决定持久化或仅本地生效。

**Architecture:** 用独立纯函数统一计算安全兼容类型和持久化权限；`SQView` 只负责更新 `chart.type` 与重绘，`SQComponentWrapper` 负责普通看板工具栏和类型变更事件，`SQPreviewShow` 作为完整看板状态所有者串行保存 `canvas_view_info`。保存队列按看板集中协调，避免多个卡片并发提交完整 JSON 时互相覆盖。

**Tech Stack:** Vue 3 `<script setup>`、TypeScript 5.7、Element Plus Secondary、Pinia、Node.js `assert` 测试、Vite 6。

## Global Constraints

- 不修改数据库表、后端数据模型或迁移脚本；继续使用 `chart.type` 和现有 `update_canvas`。
- `chart.sourceType` 必须保留首次生成类型，不能因切换或添加到看板而删除。
- 只允许 `column`、`bar`、`line`、`area` 互换；表格使用独立按钮，不自动替换坐标轴或字段。
- 有编辑权限时持久化；只读用户和模板预览仅本地切换，不显示“未保存”提示。
- 保存失败恢复最后一次已保存类型并明确提示；保存成功不弹提示。
- 所有提交消息使用中文。

---

### Task 1: 统一图表类型兼容和权限规则

**Files:**
- Create: `frontend/src/views/dashboard/utils/dashboardChartTypeSwitch.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardChartTypeSwitch.test.mjs`

**Interfaces:**
- Consumes: `ChartTypes` from `frontend/src/views/chat/component/BaseChart.ts`。
- Produces: `resolveDashboardChartSwitchTypes(chart)`、`canSwitchDashboardChartToTable(chart)`、`shouldPersistDashboardChartType(context)`。

- [ ] **Step 1: 写失败测试**

创建动态转译 TypeScript 的 Node 测试，断言笛卡尔图表返回固定顺序、`table` 通过 `sourceType` 恢复类型组、指标卡无菜单，并覆盖可编辑、只读和模板权限：

```js
assert.deepEqual(resolveDashboardChartSwitchTypes({ type: 'line' }), [
  'column', 'bar', 'line', 'area',
])
assert.deepEqual(
  resolveDashboardChartSwitchTypes({ type: 'table', sourceType: 'line' }),
  ['column', 'bar', 'line', 'area']
)
assert.deepEqual(resolveDashboardChartSwitchTypes({ type: 'metric' }), [])
assert.equal(canSwitchDashboardChartToTable({ type: 'area' }), true)
assert.equal(
  shouldPersistDashboardChartType({
    dashboardId: 'dashboard-1',
    canEdit: true,
    readonlyTemplate: false,
    platformTemplate: false,
  }),
  true
)
assert.equal(
  shouldPersistDashboardChartType({
    dashboardId: 'dashboard-1',
    canEdit: false,
    readonlyTemplate: false,
    platformTemplate: false,
  }),
  false
)
assert.equal(
  shouldPersistDashboardChartType({
    dashboardId: 'dashboard-1',
    canEdit: true,
    readonlyTemplate: true,
    platformTemplate: false,
  }),
  false
)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/dashboard/utils/dashboardChartTypeSwitch.test.mjs`

Expected: FAIL，提示 `dashboardChartTypeSwitch.ts` 不存在。

- [ ] **Step 3: 实现最小纯函数**

```ts
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'

export type DashboardChartTypeConfig = {
  type?: ChartTypes
  sourceType?: ChartTypes
}

export type DashboardChartTypePersistenceContext = {
  dashboardId?: string | number | null
  canEdit?: boolean
  readonlyTemplate?: boolean
  platformTemplate?: boolean
}

const CARTESIAN_SWITCH_TYPES: readonly ChartTypes[] = ['column', 'bar', 'line', 'area']
const CARTESIAN_SWITCH_TYPE_SET = new Set<ChartTypes>(CARTESIAN_SWITCH_TYPES)

export function resolveDashboardChartSwitchTypes(
  chart?: DashboardChartTypeConfig | null
): ChartTypes[] {
  const sourceType = chart?.sourceType || chart?.type
  return sourceType && CARTESIAN_SWITCH_TYPE_SET.has(sourceType)
    ? [...CARTESIAN_SWITCH_TYPES]
    : []
}

export function canSwitchDashboardChartToTable(
  chart?: DashboardChartTypeConfig | null
): boolean {
  return resolveDashboardChartSwitchTypes(chart).length > 0
}

export function shouldPersistDashboardChartType(
  context: DashboardChartTypePersistenceContext
): boolean {
  return Boolean(
    context.dashboardId &&
      context.canEdit === true &&
      !context.readonlyTemplate &&
      !context.platformTemplate
  )
}
```

测试转译时把 `import type` 擦除，不需要解析 `@` 别名。

- [ ] **Step 4: 运行测试并确认通过**

Run: `cd frontend; node src/views/dashboard/utils/dashboardChartTypeSwitch.test.mjs`

Expected: PASS，退出码 0。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/views/dashboard/utils/dashboardChartTypeSwitch.ts frontend/src/views/dashboard/utils/dashboardChartTypeSwitch.test.mjs
git commit -m "功能：统一看板图表类型切换规则"
```

---

### Task 2: 建立看板级串行保存协调器

**Files:**
- Create: `frontend/src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs`

**Interfaces:**
- Consumes: `ChartTypeChange { chartId, previousType, nextType }` and callbacks supplied by `SQPreviewShow.vue`。
- Produces: `createDashboardChartTypeSaveCoordinator(options)` returning `enqueue(change)`, `flush()`, and `reset()`。

- [ ] **Step 1: 写失败测试**

测试用可控 Promise 模拟首个请求未完成时再次切换，验证保存严格串行且最终值为最后选择；再模拟失败，验证仅在没有更新选择时回滚：

```js
const currentTypes = new Map([['chart-1', 'line']])
const snapshots = []
let releaseFirst
let saveCount = 0
const coordinator = createDashboardChartTypeSaveCoordinator({
  getCurrentType: (id) => currentTypes.get(id),
  restoreType: (id, type) => currentTypes.set(id, type),
  save: async () => {
    snapshots.push(currentTypes.get('chart-1'))
    saveCount += 1
    if (saveCount === 1) await new Promise((resolve) => { releaseFirst = resolve })
  },
  onError: () => assert.fail('成功路径不应报错'),
})

currentTypes.set('chart-1', 'bar')
void coordinator.enqueue({ chartId: 'chart-1', previousType: 'line', nextType: 'bar' })
currentTypes.set('chart-1', 'area')
void coordinator.enqueue({ chartId: 'chart-1', previousType: 'bar', nextType: 'area' })
releaseFirst()
await coordinator.flush()
assert.deepEqual(snapshots, ['bar', 'area'])
```

失败用例让 `save()` reject，期望 `restoreType('chart-1', 'line')` 被调用一次，`onError` 被调用一次。再增加 reset 用例：请求未完成时调用 `reset()`，旧请求后续失败不能恢复或提示到新看板状态。

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs`

Expected: FAIL，提示协调器模块不存在。

- [ ] **Step 3: 实现最小协调器**

```ts
export type DashboardChartTypeChange = {
  chartId: string
  previousType: string
  nextType: string
}

type CoordinatorOptions = {
  save: () => Promise<void>
  getCurrentType: (chartId: string) => string | undefined
  restoreType: (chartId: string, chartType: string) => void
  onError: (error: unknown) => void
}

export function createDashboardChartTypeSaveCoordinator(options: CoordinatorOptions) {
  const persistedTypes = new Map<string, string>()
  const pendingTypes = new Map<string, string>()
  let draining: Promise<void> | null = null
  let generation = 0

  async function drain() {
    while (pendingTypes.size > 0) {
      const batch = new Map(pendingTypes)
      const batchGeneration = generation
      pendingTypes.clear()
      try {
        await options.save()
        if (batchGeneration !== generation) continue
        batch.forEach((type, chartId) => persistedTypes.set(chartId, type))
      } catch (error) {
        if (batchGeneration !== generation) continue
        batch.forEach((failedType, chartId) => {
          const persistedType = persistedTypes.get(chartId)
          if (
            persistedType &&
            !pendingTypes.has(chartId) &&
            options.getCurrentType(chartId) === failedType
          ) {
            options.restoreType(chartId, persistedType)
          }
        })
        options.onError(error)
      }
    }
  }

  function enqueue(change: DashboardChartTypeChange) {
    if (!persistedTypes.has(change.chartId)) {
      persistedTypes.set(change.chartId, change.previousType)
    }
    pendingTypes.set(change.chartId, change.nextType)
    if (!draining) {
      draining = drain().finally(() => {
        draining = null
      })
    }
    return draining
  }

  return {
    enqueue,
    flush: () => draining || Promise.resolve(),
    reset: () => {
      generation += 1
      persistedTypes.clear()
      pendingTypes.clear()
    },
  }
}
```

- [ ] **Step 4: 运行协调器测试**

Run: `cd frontend; node src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs`

Expected: PASS，保存快照严格为 `bar`、`area`，失败路径恢复 `line`。

- [ ] **Step 5: 提交**

```powershell
git add frontend/src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.ts frontend/src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs
git commit -m "功能：串行保存看板图表类型"
```

---

### Task 3: 让 SQView 复用规则并支持外部切换与回滚重绘

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Modify: `frontend/src/views/dashboard/editor/index.vue`
- Create: `frontend/src/views/dashboard/components/sq-view/index.chart-type-switch.test.mjs`

**Interfaces:**
- Consumes: `resolveDashboardChartSwitchTypes(viewInfo.chart)` from Task 1。
- Produces: exposed `changeChartType(nextType: ChartTypes): void` on `SQView` component instance。

- [ ] **Step 1: 写失败契约测试**

读取 Vue 源码并断言：

```js
assert.match(sqViewSource, /resolveDashboardChartSwitchTypes/)
assert.match(sqViewSource, /function changeChartType\(nextType: ChartTypes\)/)
assert.match(sqViewSource, /defineExpose\(\{[\s\S]*changeChartType/)
assert.match(sqViewSource, /sourceType[\s\S]*previousType/)
assert.match(sqViewSource, /scheduleRenderChart\(\)/)
assert.doesNotMatch(editorSource, /delete target\.chart\.sourceType/)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/dashboard/components/sq-view/index.chart-type-switch.test.mjs`

Expected: FAIL，尚未导入共享规则且未暴露 `changeChartType`。

- [ ] **Step 3: 替换抽屉类型列表并保留来源类型**

在 `sq-view/index.vue` 中把当前 `switch (sourceType)` 替换为共享类型数组与本地图标映射：

```ts
const chartTypeIconMap: Partial<Record<ChartTypes, any>> = {
  column: ICON_COLUMN,
  bar: ICON_BAR,
  line: ICON_LINE,
  area: ICON_LINE,
}

const chartTypeList = computed(() =>
  resolveDashboardChartSwitchTypes(props.viewInfo.chart).map((value) => ({
    value,
    name: t(`chat.chart_type.${value}`),
    icon: chartTypeIconMap[value],
  }))
)
```

实现并暴露外部切换方法：

```ts
function changeChartType(nextType: ChartTypes) {
  const previousType = chartType.value
  if (!props.viewInfo.chart.sourceType && previousType !== 'table') {
    props.viewInfo.chart.sourceType = previousType
  }
  chartType.value = nextType
  props.viewInfo.chart.type = nextType
  scheduleRenderChart()
}
```

现有 `onTypeChange` 和 `changeTable` 都调用 `changeChartType`。监听外部 `chart.type` 变化时设置 `currentChartType` 并调用 `scheduleRenderChart()`，保证保存失败回滚能重绘。把 `changeChartType` 加入 `defineExpose`。

- [ ] **Step 4: 转存时保留 sourceType**

从 `frontend/src/views/dashboard/editor/index.vue` 删除：

```ts
delete target.chart.sourceType
```

不得新增其他字段回退或类型猜测。

- [ ] **Step 5: 运行测试和类型检查**

Run: `cd frontend; node src/views/dashboard/components/sq-view/index.chart-type-switch.test.mjs`

Expected: PASS。

Run: `cd frontend; npx vue-tsc -b --pretty false`

Expected: PASS，无 TypeScript 错误。

- [ ] **Step 6: 提交**

```powershell
git add frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.chart-type-switch.test.mjs frontend/src/views/dashboard/editor/index.vue
git commit -m "功能：支持看板图表即时类型切换"
```

---

### Task 4: 在普通看板卡片工具栏增加切换入口

**Files:**
- Modify: `frontend/src/views/chat/chat-block/ChartPopover.vue`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue`
- Create: `frontend/src/views/dashboard/preview/SQComponentWrapper.chart-type-switch.test.mjs`

**Interfaces:**
- Consumes: `resolveDashboardChartSwitchTypes` and `canSwitchDashboardChartToTable` from Task 1；`changeChartType` from Task 3。
- Produces: `chartTypeChanged` event carrying `{ chartId, previousType, nextType }` from wrapper through `SQPreview`。

- [ ] **Step 1: 写失败契约测试**

断言普通看板操作栏复用组件、表格按钮、事件载荷和透传：

```js
assert.match(wrapperSource, /import ChartPopover/)
assert.match(wrapperSource, /resolveDashboardChartSwitchTypes/)
assert.match(wrapperSource, /<ChartPopover[\s\S]*@type-change="changePreviewChartType"/)
assert.match(wrapperSource, /component\.value as any\)\?\.changeChartType\?\./)
assert.match(wrapperSource, /emit\('chartTypeChanged',[\s\S]*previousType[\s\S]*nextType/)
assert.match(previewSource, /@chart-type-changed="emit\('chartTypeChanged', \$event\)"/)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/dashboard/preview/SQComponentWrapper.chart-type-switch.test.mjs`

Expected: FAIL，普通看板工具栏尚无 `ChartPopover`。

- [ ] **Step 3: 给共享弹窗增加紧凑模式**

在 `ChartPopover.vue` 增加布尔 `compact` prop，引用元素追加 class：

```vue
<div
  class="chat-select_type"
  :class="{ active: chartType && chartType !== 'table', compact }"
>
```

紧凑样式使用固定尺寸，不能因图标或文本变化挤动工具栏：

```less
&.compact {
  width: 34px;
  height: 20px;
  padding: 0 3px;
  border-radius: 6px;
}
```

- [ ] **Step 4: 在 wrapper 中实现本地切换与事件**

构造当前选项和图标映射，仅对成功状态的普通单图卡片显示。切换方法先调用子组件，再发事件：

```ts
function changePreviewChartType(nextType: ChartTypes) {
  const previousType = currentChartType.value
  if (previousType === nextType) return
  ;(component.value as any)?.changeChartType?.(nextType)
  emit('chartTypeChanged', {
    chartId: String(props.configItem.id),
    previousType,
    nextType,
  })
}
```

把紧凑 `ChartPopover` 和独立表格按钮放在 `.preview-chart-actions` 最前方；表格按钮调用 `changePreviewChartType('table')`。失败图表、指标卡、非 `SQView` 和 tab 内无独立工具栏的图表不显示入口。

- [ ] **Step 5: 通过 SQPreview 透传事件**

```ts
const emit = defineEmits(['chartMoved', 'chartTypeChanged'])
```

```vue
@chart-type-changed="emit('chartTypeChanged', $event)"
```

- [ ] **Step 6: 运行契约测试与既有工具栏测试**

Run: `cd frontend; node src/views/dashboard/preview/SQComponentWrapper.chart-type-switch.test.mjs`

Expected: PASS。

Run: `cd frontend; node src/views/dashboard/preview/SQComponentWrapper.fullscreen-actions.test.mjs`

Expected: PASS，操作栏仍可命中。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/views/chat/chat-block/ChartPopover.vue frontend/src/views/dashboard/preview/SQComponentWrapper.vue frontend/src/views/dashboard/preview/SQPreview.vue frontend/src/views/dashboard/preview/SQComponentWrapper.chart-type-switch.test.mjs
git commit -m "功能：在看板卡片增加图表类型切换"
```

---

### Task 5: 按权限持久化并在失败时回滚

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`
- Modify: `frontend/src/i18n/zh-CN.json`
- Modify: `frontend/src/i18n/zh-TW.json`
- Modify: `frontend/src/i18n/en.json`
- Modify: `frontend/src/i18n/ko-KR.json`
- Create: `frontend/src/views/dashboard/preview/SQPreviewShow.chart-type-persistence.test.mjs`

**Interfaces:**
- Consumes: `DashboardChartTypeChange` and save coordinator from Task 2；`shouldPersistDashboardChartType` from Task 1；`chartTypeChanged` from Task 4。
- Produces: permission-aware `handleChartTypeChanged(change)` and complete `update_canvas` payload。

- [ ] **Step 1: 写失败契约测试**

断言父页面监听事件、权限判断、保存完整 JSON、错误回滚消息和状态重置：

```js
assert.match(source, /@chart-type-changed="handleChartTypeChanged"/)
assert.match(source, /shouldPersistDashboardChartType\(/)
assert.match(source, /createDashboardChartTypeSaveCoordinator\(/)
assert.match(source, /dashboardApi\.update_canvas\(\{[\s\S]*component_data:[\s\S]*canvas_style_data:[\s\S]*canvas_view_info:/)
assert.match(source, /chart_type_save_failed/)
assert.match(source, /chartTypeSaveCoordinator\.reset\(\)/)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/dashboard/preview/SQPreviewShow.chart-type-persistence.test.mjs`

Expected: FAIL，尚未监听类型变更事件。

- [ ] **Step 3: 创建集中保存方法和协调器**

保存函数必须在实际执行时读取最新状态：

```ts
async function saveDashboardChartTypes() {
  const info = state.dashboardInfo
  await dashboardApi.update_canvas({
    id: info.id,
    name: info.name,
    pid: info.pid || 'root',
    datasource: info.datasource,
    node_type: 'leaf',
    type: info.type || 'dashboard',
    opt: 'updateLeaf',
    component_data: JSON.stringify(state.canvasDataPreview || []),
    canvas_style_data: JSON.stringify(state.canvasStylePreview || {}),
    canvas_view_info: JSON.stringify(state.canvasViewInfoPreview || {}),
  })
}
```

创建协调器时，`getCurrentType` 和 `restoreType` 只读写目标图表的 `chart.type`；`onError` 使用 `ElMessage.error(t('dashboard.chart_type_save_failed'))`。

- [ ] **Step 4: 实现权限分支**

```ts
function handleChartTypeChanged(change: DashboardChartTypeChange) {
  if (
    !shouldPersistDashboardChartType({
      dashboardId: state.dashboardInfo?.id,
      canEdit: state.dashboardInfo?.canEdit,
      readonlyTemplate: false,
      platformTemplate: false,
    })
  ) {
    return
  }
  void chartTypeSaveCoordinator.enqueue(change)
}
```

`stateInit()`、切换看板和卸载时调用 `reset()`，防止上一个看板的已保存类型进入新看板。只读分支必须在 enqueue 前返回，因此不会触发 API。

- [ ] **Step 5: 增加四语种失败提示**

在 `dashboard` i18n 节点增加：

```json
"chart_type_save_failed": "图表类型保存失败，已恢复原设置"
```

其他语言使用对应含义：繁中“圖表類型儲存失敗，已還原原設定”、英文“Failed to save the chart type. The previous setting was restored.”、韩文“차트 유형을 저장하지 못해 이전 설정으로 복원했습니다.”。

- [ ] **Step 6: 运行持久化、协调器和类型检查**

Run: `cd frontend; node src/views/dashboard/preview/SQPreviewShow.chart-type-persistence.test.mjs`

Expected: PASS。

Run: `cd frontend; node src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs`

Expected: PASS。

Run: `cd frontend; npx vue-tsc -b --pretty false`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add frontend/src/views/dashboard/preview/SQPreviewShow.vue frontend/src/views/dashboard/preview/SQPreviewShow.chart-type-persistence.test.mjs frontend/src/i18n/zh-CN.json frontend/src/i18n/zh-TW.json frontend/src/i18n/en.json frontend/src/i18n/ko-KR.json
git commit -m "功能：按权限保存看板图表类型"
```

---

### Task 6: 完整回归与浏览器验收

**Files:**
- Verify only; fix only files already listed when a failure is attributable to this feature。

**Interfaces:**
- Consumes: all preceding tasks。
- Produces: verified feature on desktop and narrow viewport。

- [ ] **Step 1: 运行全部定向测试**

Run:

```powershell
cd frontend
node src/views/dashboard/utils/dashboardChartTypeSwitch.test.mjs
node src/views/dashboard/utils/dashboardChartTypeSaveCoordinator.test.mjs
node src/views/dashboard/components/sq-view/index.chart-type-switch.test.mjs
node src/views/dashboard/preview/SQComponentWrapper.chart-type-switch.test.mjs
node src/views/dashboard/preview/SQPreviewShow.chart-type-persistence.test.mjs
node src/views/dashboard/preview/SQComponentWrapper.fullscreen-actions.test.mjs
```

Expected: 所有命令退出码 0。

- [ ] **Step 2: 运行前端生产构建**

Run: `cd frontend; npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均成功，退出码 0。

- [ ] **Step 3: 核对本地服务并打开看板**

按仓库运行手册检查四个服务：

```powershell
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: frontend `5173`、API `8000`、MCP `8001` 和一个本地 Worker 均可用；若未运行，按同一手册启动完整本地栈与前端。

- [ ] **Step 4: 使用浏览器验证可编辑看板**

打开普通看板，悬停截图所示趋势图卡片，验证：菜单位置不遮挡标题与其他按钮；四种类型和表格可即时切换；切换不重新请求 SQL；刷新页面后编辑用户保留最终类型；全屏显示当前类型。

- [ ] **Step 5: 使用浏览器验证只读行为和抽屉回归**

以只读看板上下文验证菜单仍可使用但刷新恢复服务端类型，网络请求中没有 `update_canvas`；打开“从问答记录添加图表”抽屉，验证同一菜单可切换，确认添加保留类型，取消不写入看板。

- [ ] **Step 6: 检查改动范围并提交修正**

Run: `git diff --check`

Expected: 无空白错误。

如浏览器或构建验证产生必要修正，仅暂存本功能文件并提交：

```powershell
git add frontend/src/views/dashboard frontend/src/views/chat/chat-block/ChartPopover.vue frontend/src/i18n
git commit -m "修复：完善看板图表类型切换验收"
```
