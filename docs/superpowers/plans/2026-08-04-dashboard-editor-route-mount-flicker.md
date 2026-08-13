# 看板编辑页路由挂载闪烁修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除进入 `/canvas` 时旧画布先挂载、随后卸载并在资源返回后再次挂载造成的闪烁。

**Architecture:** 保留现有路由、Pinia 画布状态和图表原子渲染实现，只收紧 `frontend/src/views/dashboard/editor/index.vue` 的资源就绪门。编辑页初始关闭就绪门，匹配的未保存创建态草稿可以同步复用，其他路径在第一次异步等待前关闭旧 UI，且只有当前加载版本能一次性放行工具栏和画布。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vue Router、Node.js `node:test`/`assert`、Vite

## Global Constraints

- 首次进入 `/canvas` 时，目标资源就绪前不得挂载残留的工具栏或画布。
- 目标资源加载完成后，`DashboardEditor` 只挂载一次。
- 匹配的未保存创建态草稿继续复用，不引入额外卸载。
- 过期请求不能重新放行画布。
- 加载期间只保留固定编辑页背景，不增加加载圆环或二次遮罩。
- 不修改图表数据、SQL、字段映射、Data Skills、模板保存结构、数据源权限或图表原子绘制实现。
- 不增加平台模板专属跨路由缓存、页面截图、keep-alive 或兼容回退。

---

### Task 1: 固化编辑资源就绪门的失败回归

**Files:**
- Create: `frontend/src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs`
- Read: `frontend/src/views/dashboard/editor/index.vue`

**Interfaces:**
- Consumes: `index.vue` 中的 `dataInitState`、`loadCanvasFromRoute()` 和根模板。
- Produces: 一个无需浏览器即可验证挂载门顺序的 Node 回归测试。

- [ ] **Step 1: 写入当前实现必然失败的生命周期测试**

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const loadCanvas =
  source.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(
  source,
  /const dataInitState = ref\(false\)/,
  '编辑页首次渲染前必须关闭资源就绪门，不能挂载残留画布'
)
assert.ok(loadCanvas, '需要保留统一的路由画布加载入口')

const draftReturnIndex = loadCanvas.indexOf('canvasStateReady = true')
const closeGateIndex = loadCanvas.indexOf('dataInitState.value = false')
const firstAwaitIndex = loadCanvas.indexOf('await ')
assert.ok(draftReturnIndex >= 0, '匹配的未保存创建态草稿需要保留快速返回')
assert.ok(
  closeGateIndex > draftReturnIndex,
  '草稿快速返回必须发生在关闭已就绪画布之前，避免草稿路径额外卸载'
)
assert.ok(
  closeGateIndex >= 0 && closeGateIndex < firstAwaitIndex,
  '非草稿路径必须在第一次异步等待前关闭旧画布'
)

const draftBranch =
  loadCanvas.match(
    /if \(\s*sourceKey &&[\s\S]*?dashboardStore\.hasUnsavedCanvasChanges\s*\) \{([\s\S]*?)\r?\n\s*\}/
  )?.[1] || ''
assert.match(
  draftBranch,
  /dataInitState\.value = true[\s\S]*?canvasStateReady = true[\s\S]*?return/,
  '草稿快速返回需要显式恢复资源就绪门'
)
assert.match(
  loadCanvas,
  /finally \{\s*if \(loadVersion === routeLoadVersion\) \{\s*dataInitState\.value = true\s*canvasStateReady = true/,
  '只有当前加载版本可以在 finally 中放行画布'
)
assert.match(
  source,
  /<template v-if="dataInitState">\s*<Toolbar[\s\S]*?<DashboardEditor/,
  '工具栏和画布必须由同一个资源就绪门控制'
)
assert.doesNotMatch(
  source,
  /<DashboardEditor\s+v-if="dataInitState"/,
  '资源就绪门应控制完整编辑 UI，不能只控制画布子树'
)

console.log('Dashboard editor route mount lifecycle tests passed')
```

- [ ] **Step 2: 运行测试并确认 RED**

Run from `frontend`:

```powershell
node --test src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs
```

Expected: FAIL，首个失败信息为“编辑页首次渲染前必须关闭资源就绪门，不能挂载残留画布”，因为当前实现仍是 `ref(true)`。

---

### Task 2: 让工具栏和画布只在当前资源就绪后挂载

**Files:**
- Modify: `frontend/src/views/dashboard/editor/index.vue:58`
- Modify: `frontend/src/views/dashboard/editor/index.vue:710-790`
- Modify: `frontend/src/views/dashboard/editor/index.vue:1028-1048`
- Test: `frontend/src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs`

**Interfaces:**
- Consumes: 现有 `routeLoadVersion`、`canvasStateReady`、`canUseCanvasDraft()`、`dashboardStore.canvasEditingSourceKey` 和 `dashboardStore.hasUnsavedCanvasChanges`。
- Produces: `dataInitState` 作为完整编辑 UI 的唯一资源就绪门；不新增导出接口。

- [ ] **Step 1: 默认关闭编辑资源就绪门**

将初始化改为：

```ts
const dataInitState = ref(false)
```

- [ ] **Step 2: 重排 `loadCanvasFromRoute()`，草稿先判断，其他路径先关门再等待**

用以下完整函数替换现有实现：

```ts
const loadCanvasFromRoute = async () => {
  const loadVersion = ++routeLoadVersion
  persistCanvasDraft()
  cancelDashboardChartRefresh()
  permissionDeniedCharts.reset()
  chartRefreshRetryCount = 0
  canvasStateReady = false
  syncRouteState()

  const sourceKey =
    state.platformTemplateId
      ? getPlatformTemplateCanvasSourceKey(state.platformTemplateId)
      : state.opt === 'create'
      ? getCreateCanvasSourceKey(state.datasource, state.routerPid)
      : getDashboardCanvasSourceKey(state.resourceId)
  if (sourceKey && !canUseCanvasDraft(sourceKey)) {
    clearDashboardCanvasDraft(sourceKey)
  }
  if (
    sourceKey &&
    canUseCanvasDraft(sourceKey) &&
    dashboardStore.canvasEditingSourceKey === sourceKey &&
    dashboardStore.hasUnsavedCanvasChanges
  ) {
    dataInitState.value = true
    canvasStateReady = true
    return
  }

  dataInitState.value = false
  try {
    if (!state.platformTemplateId) {
      await datasourceContext.loadDatasources()
      if (loadVersion !== routeLoadVersion) return
    }
    if (state.platformTemplateId && sourceKey) {
      const templateId = state.platformTemplateId
      const result = await loadPlatformTemplateResource(templateId)
      if (loadVersion !== routeLoadVersion) return
      await applyLoadedCanvasResource(templateId, result, sourceKey)
      dashboardStore.updateDashboardInfo({
        canEdit: true,
        canShare: false,
      })
      dashboardStore.markCanvasSaved()
    } else if (state.opt === 'create') {
      const createSourceKey = getCreateCanvasSourceKey(state.datasource, state.routerPid)
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
        dashboardStore.updateDashboardInfo({
          dataState: 'prepare',
          name: t('dashboard.new_dashboard'),
          pid: state.routerPid,
          datasource: state.datasource,
          canEdit: true,
          canShare: true,
        })
        dashboardStore.setCanvasEditingSourceKey(createSourceKey)
      })
      const restored = await restoreCanvasDraft(createSourceKey)
      if (!restored) {
        dashboardStore.markCanvasSaved()
      }
    } else if (state.resourceId && sourceKey) {
      const resourceId = state.resourceId
      const result = await loadCanvasResource(resourceId)
      if (loadVersion !== routeLoadVersion) return
      await applyLoadedCanvasResource(resourceId, result)
      dashboardStore.markCanvasSaved()
      scheduleEditorChartRefresh(loadVersion)
    } else {
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
      })
    }
  } finally {
    if (loadVersion === routeLoadVersion) {
      dataInitState.value = true
      canvasStateReady = true
    }
  }
}
```

- [ ] **Step 3: 让同一个条件控制完整编辑 UI**

将 `.editor-main` 内容改为：

```vue
<div class="editor-main" :aria-busy="!dataInitState">
  <template v-if="dataInitState">
    <Toolbar
      :base-params="baseParams"
      :find-position-x="findPositionX"
      @add-components="addComponents"
    ></Toolbar>
    <DashboardEditor
      ref="dashboardEditorInnerRef"
      :dashboard-info="dashboardInfo"
      :canvas-component-data="componentData"
      :canvas-view-info="canvasViewInfo"
      :can-edit-sql="dashboardInfo.canEdit !== false"
      :platform-template="Boolean(state.platformTemplateId)"
    >
    </DashboardEditor>
  </template>
</div>
```

加载期间 `.editor-main` 仍占满 `100%` 宽高并保持现有背景，不添加 spinner、提示文字或遮罩。

- [ ] **Step 4: 运行新测试并确认 GREEN**

Run from `frontend`:

```powershell
node --test src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs
```

Expected: PASS，输出 `Dashboard editor route mount lifecycle tests passed`。

- [ ] **Step 5: 运行相邻生命周期回归**

Run from `frontend`:

```powershell
node --test src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs src/views/dashboard/editor/index.permission-refresh.test.mjs src/views/dashboard/editor/DashboardEditor.resize-lifecycle.test.mjs src/views/dashboard/components/sq-view/index.state-machine.test.mjs src/views/chat/component/ChartComponent.atomic-render.test.mjs
```

Expected: 5 个测试文件全部 PASS，无失败或未处理异常。

- [ ] **Step 6: 提交单一生产变更单元**

```powershell
git add -- frontend/src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs frontend/src/views/dashboard/editor/index.vue docs/superpowers/plans/2026-08-04-dashboard-editor-route-mount-flicker.md
git diff --cached --check
git commit -m "修复看板编辑页首次双重挂载闪烁"
```

Expected: 提交只包含本计划、生命周期测试和编辑页文件，不包含工作区上下文或数据脚本等其他修改。

---

### Task 3: 构建和真实管理员页面回归

**Files:**
- Verify: `frontend/src/views/dashboard/editor/index.vue`
- Verify: `frontend/src/views/dashboard/editor/index.route-mount-lifecycle.test.mjs`

**Interfaces:**
- Consumes: Task 2 完成的单一资源就绪门。
- Produces: 编译证据和平台模板“点击编辑”真实页面验证结果。

- [ ] **Step 1: 运行前端构建**

Run from `frontend`:

```powershell
npm run build
```

Expected: `vue-tsc -b && vite build` 退出码为 `0`。

- [ ] **Step 2: 检查最终差异和工作区边界**

Run from repository root:

```powershell
git diff --check HEAD^ HEAD
git show --stat --oneline HEAD
git status --short
```

Expected: 本次提交只有计划、测试和 `editor/index.vue`；其他用户改动仍保持未提交且内容未变。

- [ ] **Step 3: 在平台管理员页面验证目标交互**

打开：

```text
http://127.0.0.1:5173/#/system/dashboard-template?templateId=72cfa00e7dff489ab004c58747ca1570
```

依次执行：等待模板预览稳定、点击右上角“编辑”、观察 `/canvas?platformTemplateId=72cfa00e7dff489ab004c58747ca1570` 首次出现后的 DOM 和图表状态。

Expected:

- 编辑器工具栏和画布同时出现。
- `DashboardEditor` 首次出现后不再消失或重建。
- 不短暂显示上一个 Pinia 画布、旧标题或空网格。
- 图表首帧仍由既有卡片遮罩和 `render-ready` 握手接管。
- 浏览器控制台没有新增 Vue、ResizeObserver 或图表渲染错误。

- [ ] **Step 4: 报告验证限制**

若可用浏览器没有平台管理员登录态，不得用普通工作空间页面冒充通过；明确报告自动化测试和构建结果，并将真实管理员点击验证列为唯一剩余人工检查。
