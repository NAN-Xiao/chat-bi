# Tab 卡片内容单向自适应实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅为 Tab 内的 `SQView` 增加由 Card 根 `border-box` 驱动的单向内容自适应，使摘要布局稳定更新且不回写 Card 网格、不重建 Vue 图表组件。

**Architecture:** 沿 Tab 编辑与预览组件链显式传播 `DashboardLayoutSurface`，并在 `SQView` 中只为 `tab` surface 启用独立协调器。协调器以整数规范帧、图表结构、摘要配置和固定工具栏 variant 生成连续签名，通过纯状态转换调用现有 `resolveInsightDisplay`；Card 内部 DOM 和图表容器尺寸不再成为布局策略输入。

**Tech Stack:** Vue 3 `<script setup>`、TypeScript 5.7、原生 `ResizeObserver`、Node.js `.test.mjs` 契约测试、Vite 6、现有应用内浏览器测试能力。

## Global Constraints

- 新逻辑只在 `dashboardLayoutSurface='tab'` 生效；`main` 保持当前发布行为，`showPosition='multiplexing'` 继续使用现有非看板行为。
- Tab Card 外框、`sizeX`、`sizeY`、网格坐标和父级布局只能由 Tab 编辑器或预览器生产，`SQView` 不得写入。
- Tab 唯一几何观察源是 Card 根节点的 `border-box`；不得读取或观察 `.chart-show-area`、工具栏、图表 canvas/SVG 的实时尺寸来决定布局。
- 工具栏 variant 固定为 `none | pivot | date | combined`，reserve 固定为 `0 | 30 | 36 | 36` 像素；combined 在 Tab 内保持单行并裁剪溢出。
- 每个连续布局签名最多执行一次 `resolveInsightDisplay`；`A -> B -> A` 必须执行三次合法转换，不能使用生命周期 Map 缓存。
- 普通数据值、请求 ID、刷新时间、loading 状态不进入布局签名；有新数据时允许同一 `ChartComponent` 执行正常数据渲染。
- `ChartComponent` 的 Vue `key` 只由稳定图表身份决定；frame、layout、density、摘要配置和版本号不得进入 key。
- 测量或转换失败时保留上一稳定 frame/display/key，不使用 `nextTick`、`setTimeout` 或等价任务自重试。
- 摘要明确关闭时，`SQView` 不挂载 `ChartInsightHeader`。
- 不新增 Playwright、Vitest、jsdom 或业务域依赖；不添加数据源、字段、图表问题、看板 ID 特例。
- 设计依据：`docs/superpowers/specs/2026-08-04-tab-card-content-adaptive-layout-design.md`。

## File Map

- Create `frontend/src/views/dashboard/utils/dashboardLayoutSurface.ts`: 共享 `main | tab` surface 类型和默认值。
- Create `frontend/src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs`: 验证两条 Tab 链与主画布默认值的显式传播契约。
- Modify `frontend/src/views/dashboard/components/sq-tab/index.vue`: 两个 Tab 子画布入口显式传入 `tab`。
- Modify `frontend/src/views/dashboard/preview/SQPreview.vue`: 接收 surface 并传给每个预览 wrapper。
- Modify `frontend/src/views/dashboard/preview/SQComponentWrapper.vue`: 只给动态 `SQView` 传 surface，避免属性落到其他组件根 DOM。
- Modify `frontend/src/views/dashboard/editor/DashboardEditor.vue`: 接收 surface 并传给 `CanvasCore`。
- Modify `frontend/src/views/dashboard/canvas/CanvasCore.vue`: 只给动态 `SQView` 传 surface。
- Modify `frontend/src/views/chat/component/chartInsight.ts`: 导出与 resolver 使用同一判定的纯数据结构签名。
- Create `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.ts`: 工具栏 variant/reserve、连续签名和显式布局状态转换。
- Create `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs`: 覆盖签名去重、合法回切、失败保留和结构边界。
- Modify `frontend/src/views/dashboard/components/sq-view/index.vue`: 接入 Tab 协调器、root-only 观察、固定 reserve CSS 和摘要挂载边界。
- Modify `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`: 反转旧工具栏观察契约并验证单向链。
- Modify `frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs`: 使用固定 reserve 验证规范帧与策略稳定性。

---

### Task 1: 显式传播 Tab 布局 surface

**Files:**
- Create: `frontend/src/views/dashboard/utils/dashboardLayoutSurface.ts`
- Create: `frontend/src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-tab/index.vue:280`
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue:8,55,218`
- Modify: `frontend/src/views/dashboard/preview/SQComponentWrapper.vue:1,64,211`
- Modify: `frontend/src/views/dashboard/editor/DashboardEditor.vue:2,20,200`
- Modify: `frontend/src/views/dashboard/canvas/CanvasCore.vue:1,24,1699`

**Interfaces:**
- Produces: `DashboardLayoutSurface = 'main' | 'tab'` and `DEFAULT_DASHBOARD_LAYOUT_SURFACE = 'main'`.
- Consumes: existing `inTab` only for styling/grid behavior; it must not be used to infer the new surface inside `SQView`.
- Produces for Task 3: every dynamic `SQView` receives `dashboardLayoutSurface`, while `SQTab`, `SQText` and `SQEmpty` do not receive it.

- [ ] **Step 1: Write the failing propagation contract test**

Create `frontend/src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs` with:

```js
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const utilsDir = dirname(fileURLToPath(import.meta.url))
const dashboardDir = join(utilsDir, '..')
const surfacePath = join(utilsDir, 'dashboardLayoutSurface.ts')
const read = (path) => readFileSync(path, 'utf8')

assert.equal(existsSync(surfacePath), true, '需要共享 DashboardLayoutSurface 类型')
const surfaceSource = read(surfacePath)
const tabSource = read(join(dashboardDir, 'components', 'sq-tab', 'index.vue'))
const previewSource = read(join(dashboardDir, 'preview', 'SQPreview.vue'))
const wrapperSource = read(join(dashboardDir, 'preview', 'SQComponentWrapper.vue'))
const editorSource = read(join(dashboardDir, 'editor', 'DashboardEditor.vue'))
const canvasSource = read(join(dashboardDir, 'canvas', 'CanvasCore.vue'))

assert.match(surfaceSource, /export type DashboardLayoutSurface = 'main' \| 'tab'/)
assert.match(surfaceSource, /DEFAULT_DASHBOARD_LAYOUT_SURFACE[^=]*= 'main'/)
assert.match(tabSource, /<SQPreview[\s\S]*dashboard-layout-surface="tab"[\s\S]*in-tab/)
assert.match(tabSource, /<DashboardEditor[\s\S]*dashboard-layout-surface="tab"[\s\S]*in-tab/)
assert.match(previewSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(previewSource, /<SQComponentWrapper[\s\S]*:dashboard-layout-surface="dashboardLayoutSurface"/)
assert.match(wrapperSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(
  wrapperSource,
  /configItem\?\.component === 'SQView'[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)
assert.match(editorSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(editorSource, /<CanvasCore[\s\S]*:dashboard-layout-surface="dashboardLayoutSurface"/)
assert.match(canvasSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(
  canvasSource,
  /item\.component === 'SQView'[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)
assert.doesNotMatch(wrapperSource, /frameless\s*\?\s*['"]tab['"]/)
const canvasLayoutProps = canvasSource.match(
  /function componentLayoutProps\(item: CanvasItem\) \{([\s\S]*?)\r?\n\}/
)
assert.ok(canvasLayoutProps, 'CanvasCore 需要仅面向 SQView 的 surface props helper')
assert.doesNotMatch(canvasLayoutProps[1], /canvasId|inTab|classList|closest/)

console.log('dashboard layout surface contract tests passed')
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
Set-Location 'D:\AIWork3\chat-bi\.worktrees\codex-tab-card-content-adaptive\frontend'
node src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs
```

Expected: FAIL at `需要共享 DashboardLayoutSurface 类型` because the shared type does not exist.

- [ ] **Step 3: Add the shared type**

Create `frontend/src/views/dashboard/utils/dashboardLayoutSurface.ts`:

```ts
export type DashboardLayoutSurface = 'main' | 'tab'

export const DEFAULT_DASHBOARD_LAYOUT_SURFACE: DashboardLayoutSurface = 'main'
```

- [ ] **Step 4: Add typed props and explicit forwarding**

Use this prop shape in `SQPreview.vue`, `SQComponentWrapper.vue`, `DashboardEditor.vue`, and `CanvasCore.vue`, importing `type PropType` from Vue and the shared type/default:

```ts
dashboardLayoutSurface: {
  type: String as PropType<DashboardLayoutSurface>,
  default: DEFAULT_DASHBOARD_LAYOUT_SURFACE,
},
```

In `SQTab` add the literal prop to both child canvas entrances while retaining `in-tab`:

```vue
<SQPreview
  dashboard-layout-surface="tab"
  in-tab
/>

<DashboardEditor
  dashboard-layout-surface="tab"
  in-tab
/>
```

In `SQPreview` forward the typed prop:

```vue
<SQComponentWrapper
  :dashboard-layout-surface="dashboardLayoutSurface"
/>
```

In `DashboardEditor` forward it to `CanvasCore`:

```vue
<CanvasCore
  :dashboard-layout-surface="dashboardLayoutSurface"
/>
```

Replace `SQComponentWrapper.componentExtraProps` with a branch that only targets `SQView`:

```ts
const componentExtraProps = computed(() => {
  if (props.configItem?.component !== 'SQView') return {}
  return {
    showLabel: chartShowLabel.value,
    dashboardLayoutSurface: props.dashboardLayoutSurface,
  }
})
```

Add this helper to `CanvasCore` and bind it on the dynamic component:

```ts
function componentLayoutProps(item: CanvasItem) {
  if (item.component !== 'SQView') return {}
  return { dashboardLayoutSurface: props.dashboardLayoutSurface }
}
```

```vue
<component
  :is="findComponent(item.component)"
  v-bind="componentLayoutProps(item)"
/>
```

- [ ] **Step 5: Run the contract test and type build**

Run:

```powershell
node src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs
npm run build
```

Expected: the contract prints `dashboard layout surface contract tests passed`; the Vite build exits `0` without unknown-prop or TypeScript errors.

- [ ] **Step 6: Commit Task 1**

```powershell
git add -- frontend/src/views/dashboard/utils/dashboardLayoutSurface.ts frontend/src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs frontend/src/views/dashboard/components/sq-tab/index.vue frontend/src/views/dashboard/preview/SQPreview.vue frontend/src/views/dashboard/preview/SQComponentWrapper.vue frontend/src/views/dashboard/editor/DashboardEditor.vue frontend/src/views/dashboard/canvas/CanvasCore.vue
git commit -m "新增：贯通 Tab 卡片布局上下文"
```

---

### Task 2: 实现纯 Tab 布局协调器

**Files:**
- Modify: `frontend/src/views/chat/component/chartInsight.ts:320-364`
- Create: `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.ts`
- Create: `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs`

**Interfaces:**
- Produces: `TabInsightControlsVariant`, `resolveTabInsightControlsVariant`, `resolveTabInsightControlsReserve`.
- Produces: `createTabInsightLayoutState()` and `transitionTabInsightLayout(state, input, resolver?)`.
- Produces: `buildInsightDataStructureKey(...)` from `chartInsight.ts`, sharing the exact six-series and trend-granularity rules used by `resolveInsightDisplay`.
- Consumes: `InsightFrameSize`, `ChartAxis`, `ChartData`, `ChartTypes`, `InsightDisplayStrategy`, and the current `resolveInsightDisplay` resolver.

- [ ] **Step 1: Write the failing coordinator test**

Create `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs`:

```js
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const moduleUrl = new URL('./tabInsightLayout.ts', import.meta.url)
assert.equal(existsSync(fileURLToPath(moduleUrl)), true, '需要独立的 Tab 布局协调器')

const {
  createTabInsightLayoutState,
  resolveTabInsightControlsReserve,
  resolveTabInsightControlsVariant,
  transitionTabInsightLayout,
} = await import(moduleUrl.href)

assert.equal(resolveTabInsightControlsVariant({ pivot: false, date: false }), 'none')
assert.equal(resolveTabInsightControlsVariant({ pivot: true, date: false }), 'pivot')
assert.equal(resolveTabInsightControlsVariant({ pivot: false, date: true }), 'date')
assert.equal(resolveTabInsightControlsVariant({ pivot: true, date: true }), 'combined')
assert.deepEqual(
  ['none', 'pivot', 'date', 'combined'].map(resolveTabInsightControlsReserve),
  [0, 30, 36, 36]
)

const baseInput = {
  frame: { width: 620, height: 420 },
  viewId: 'chart-1',
  chartType: 'line',
  data: [
    { date: '2026-08-01', value: 10 },
    { date: '2026-08-02', value: 12 },
  ],
  x: [{ value: 'date' }],
  y: [{ value: 'value' }],
  series: [],
  insight: { enabled: true },
  controlsVariant: 'none',
}

let result = transitionTabInsightLayout(createTabInsightLayoutState(), baseInput)
assert.equal(result.processed, true)
assert.ok(result.display)

const stableState = result.state
let repeatedResolverCalls = 0
result = transitionTabInsightLayout(stableState, {
  ...baseInput,
  data: [
    { date: '2026-08-01', value: 99 },
    { date: '2026-08-02', value: 101 },
  ],
}, () => {
  repeatedResolverCalls += 1
  return stableState.display
})
assert.equal(result.processed, false, '同结构数据刷新不能重新执行布局转换')
assert.equal(result.state, stableState)
assert.equal(repeatedResolverCalls, 0)

const frameB = { ...baseInput, frame: { width: 619, height: 420 } }
const toB = transitionTabInsightLayout(stableState, frameB)
const backToA = transitionTabInsightLayout(toB.state, baseInput)
assert.equal(toB.processed, true)
assert.equal(backToA.processed, true, 'A -> B -> A 必须按连续签名重新计算')

const fiveGroups = {
  ...baseInput,
  frame: { width: 800, height: 420 },
  series: [{ value: 'group' }],
  data: ['A', 'B', 'C', 'D', 'E'].map((group) => ({ date: '2026-08-01', value: 1, group })),
}
const sixGroups = {
  ...fiveGroups,
  data: ['A', 'B', 'C', 'D', 'E', 'F'].map((group) => ({ date: '2026-08-01', value: 1, group })),
}
const fiveResult = transitionTabInsightLayout(createTabInsightLayoutState(), fiveGroups)
const sixResult = transitionTabInsightLayout(fiveResult.state, sixGroups)
assert.equal(sixResult.processed, true, 'series 从 5 组到 6 组必须产生一次结构转换')
assert.notEqual(sixResult.display?.layout, fiveResult.display?.layout)

const summaryOff = transitionTabInsightLayout(stableState, {
  ...baseInput,
  insight: { enabled: false },
})
assert.equal(summaryOff.processed, true)
assert.equal(summaryOff.display?.show, false)
assert.equal(summaryOff.display?.maxStats, 0)

for (const chartType of [
  'line',
  'area',
  'column',
  'bar',
  'pie',
  'funnel',
  'table',
  'metric',
  'sankey',
  'treemap',
]) {
  const chartResult = transitionTabInsightLayout(createTabInsightLayoutState(), {
    ...baseInput,
    chartType,
  })
  assert.equal(chartResult.processed, true, `${chartType} 应产生稳定策略`)
  assert.ok(chartResult.display)
}

const invalidFrame = transitionTabInsightLayout(stableState, {
  ...baseInput,
  frame: null,
})
assert.equal(invalidFrame.processed, false)
assert.equal(invalidFrame.state, stableState)
assert.equal(invalidFrame.display, stableState.display)
const nonPositiveFrame = transitionTabInsightLayout(stableState, {
  ...baseInput,
  frame: { width: 0, height: 420 },
})
assert.equal(nonPositiveFrame.processed, false)
assert.equal(nonPositiveFrame.state, stableState)

let failingCalls = 0
const failingResolver = () => {
  failingCalls += 1
  throw new Error('resolver failed')
}
const failed = transitionTabInsightLayout(stableState, frameB, failingResolver)
const failedAgain = transitionTabInsightLayout(failed.state, frameB, failingResolver)
assert.equal(failed.processed, false)
assert.equal(failed.state.display, stableState.display)
assert.equal(failedAgain.processed, false)
assert.equal(failingCalls, 1, '同一失败签名不得自动重试')

console.log('tab insight layout tests passed')
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
node src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
```

Expected: FAIL at `需要独立的 Tab 布局协调器`.

- [ ] **Step 3: Share the resolver's data-structure boundary**

In `chartInsight.ts`, extract the existing six-series check and export a signature builder. Reuse `hasManySeriesGroups` from `resolveInsightLayout` so the signature and resolver cannot drift:

```ts
function hasManySeriesGroups(
  data: Array<ChartData> | undefined,
  seriesAxis: ChartAxis | undefined
) {
  if (!seriesAxis) return false
  const groups = new Set(
    (Array.isArray(data) ? data : [])
      .map((row) => row?.[seriesAxis.value])
      .filter((value) => !isBlankValue(value))
      .map(String)
  )
  return groups.size >= 6
}

export function buildInsightDataStructureKey(params: {
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  dashboard?: boolean
}) {
  const rows = Array.isArray(params.data) ? params.data : []
  const seriesAxis = params.series?.[0]
  const trendGranularityRelevant =
    params.dashboard === true &&
    ['line', 'area'].includes(params.chartType) &&
    axisValues(params.y).length === 1 &&
    axisValues(params.series).length === 0
  return JSON.stringify([
    rows.length > 0,
    seriesAxis ? hasManySeriesGroups(rows, seriesAxis) : null,
    trendGranularityRelevant ? detectTrendAxisGranularity(rows, params.x?.[0]) : null,
  ])
}
```

Replace the local `Set` in `resolveInsightLayout` with:

```ts
if (hasManySeriesGroups(params.data, params.series?.[0])) {
  return 'side'
}
```

- [ ] **Step 4: Implement the coordinator and exact reserve mapping**

Create `tabInsightLayout.ts` with these public types and transition semantics:

```ts
import type { ChartAxis, ChartData, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  buildInsightDataStructureKey,
  buildInsightLayoutStateKey,
  resolveInsightDisplay,
  type InsightDensity,
  type InsightDisplayStrategy,
  type InsightLayout,
  type TrendAggregateMetric,
  type TrendComparisonMetric,
} from '../../../chat/component/chartInsight.ts'
import type { InsightFrameSize } from './insightFrame.ts'

export type TabInsightControlsVariant = 'none' | 'pivot' | 'date' | 'combined'

export interface TabInsightConfig {
  enabled?: boolean
  comparison?: {
    enabled?: boolean
    metrics?: TrendComparisonMetric[]
  }
  aggregate?: {
    enabled?: boolean
    metrics?: TrendAggregateMetric[]
  }
}

export interface TabInsightLayoutInput {
  frame: InsightFrameSize | null
  viewId?: string | number | null
  chartType: ChartTypes
  data?: Array<ChartData>
  x?: Array<ChartAxis>
  y?: Array<ChartAxis>
  series?: Array<ChartAxis>
  insight?: TabInsightConfig
  controlsVariant: TabInsightControlsVariant
}

export interface TabInsightLayoutState {
  lastAttemptedSignature: string | null
  lastProcessedSignature: string | null
  layoutStateKey: string | null
  previousLayout: InsightLayout | undefined
  previousDensity: InsightDensity | undefined
  display: InsightDisplayStrategy | null
}

export interface TabInsightLayoutTransition {
  state: TabInsightLayoutState
  display: InsightDisplayStrategy | null
  processed: boolean
  error?: unknown
}

export type TabInsightDisplayResolver = typeof resolveInsightDisplay

const CONTROLS_RESERVE: Record<TabInsightControlsVariant, number> = {
  none: 0,
  pivot: 30,
  date: 36,
  combined: 36,
}

export function resolveTabInsightControlsVariant(input: {
  pivot: boolean
  date: boolean
}): TabInsightControlsVariant {
  if (input.pivot && input.date) return 'combined'
  if (input.pivot) return 'pivot'
  if (input.date) return 'date'
  return 'none'
}

export function resolveTabInsightControlsReserve(variant: TabInsightControlsVariant) {
  return CONTROLS_RESERVE[variant]
}

export function createTabInsightLayoutState(): TabInsightLayoutState {
  return {
    lastAttemptedSignature: null,
    lastProcessedSignature: null,
    layoutStateKey: null,
    previousLayout: undefined,
    previousDensity: undefined,
    display: null,
  }
}

function normalizeInsightConfig(insight: TabInsightConfig | undefined) {
  return [
    insight?.enabled !== false,
    insight?.comparison?.enabled !== false,
    insight?.comparison?.metrics || null,
    insight?.aggregate?.enabled !== false,
    insight?.aggregate?.metrics || null,
  ]
}

function buildTabInsightLayoutSignature(input: TabInsightLayoutInput) {
  if (
    !input.frame ||
    !Number.isFinite(input.frame.width) ||
    !Number.isFinite(input.frame.height) ||
    input.frame.width <= 0 ||
    input.frame.height <= 0
  ) {
    return null
  }
  return JSON.stringify([
    input.frame.width,
    input.frame.height,
    buildInsightLayoutStateKey({
      viewId: input.viewId,
      chartType: input.chartType,
      x: input.x,
      y: input.y,
      series: input.series,
      dashboard: true,
    }),
    normalizeInsightConfig(input.insight),
    input.controlsVariant,
    buildInsightDataStructureKey({
      chartType: input.chartType,
      data: input.data,
      x: input.x,
      y: input.y,
      series: input.series,
      dashboard: true,
    }),
  ])
}

export function transitionTabInsightLayout(
  state: TabInsightLayoutState,
  input: TabInsightLayoutInput,
  resolver: TabInsightDisplayResolver = resolveInsightDisplay
): TabInsightLayoutTransition {
  const signature = buildTabInsightLayoutSignature(input)
  if (!signature || signature === state.lastAttemptedSignature) {
    return { state, display: state.display, processed: false }
  }

  const layoutStateKey = buildInsightLayoutStateKey({
    viewId: input.viewId,
    chartType: input.chartType,
    x: input.x,
    y: input.y,
    series: input.series,
    dashboard: true,
  })
  const resetHistory = layoutStateKey !== state.layoutStateKey
  const attemptedState = { ...state, lastAttemptedSignature: signature }

  try {
    const resolved = resolver({
      chartType: input.chartType,
      data: input.data,
      x: input.x,
      y: input.y,
      series: input.series,
      width: input.frame!.width,
      height: input.frame!.height,
      dashboard: true,
      previousLayout: resetHistory ? undefined : state.previousLayout,
      previousDensity: resetHistory ? undefined : state.previousDensity,
    })
    const display =
      input.insight?.enabled === false
        ? { ...resolved, show: false, maxStats: 0 }
        : resolved
    const nextState: TabInsightLayoutState = {
      lastAttemptedSignature: signature,
      lastProcessedSignature: signature,
      layoutStateKey,
      previousLayout: display.layout,
      previousDensity: display.density,
      display,
    }
    return { state: nextState, display, processed: true }
  } catch (error) {
    return { state: attemptedState, display: state.display, processed: false, error }
  }
}
```

- [ ] **Step 5: Run focused resolver and coordinator tests**

Run:

```powershell
node src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
```

Expected: all three commands exit `0`; the new test prints `tab insight layout tests passed` and existing density boundaries remain unchanged.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- frontend/src/views/chat/component/chartInsight.ts frontend/src/views/dashboard/components/sq-view/tabInsightLayout.ts frontend/src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
git commit -m "新增：实现 Tab 摘要单次布局协调器"
```

---

### Task 3: 在 SQView 接入 root-only 单向布局

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:42-168,2084-2301,2400-2420,2445-2450,2482-2490,2737-2805,2850-3245`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs`

**Interfaces:**
- Consumes: `DashboardLayoutSurface` from Task 1.
- Consumes: `createTabInsightLayoutState`, `transitionTabInsightLayout`, `resolveTabInsightControlsVariant`, and `resolveTabInsightControlsReserve` from Task 2.
- Preserves: existing main-surface `insightDisplay` behavior and current `ChartComponent` key expression.
- Produces: Tab observer watches only `containerRef` with `{ box: 'border-box' }`; fixed controls reserve is used by both canonical frame math and Tab CSS.

- [ ] **Step 1: Reverse the old structural contract so it fails on current code**

Update `index.responsive-layout.test.mjs` to require the Tab-specific branch. Retain existing flex and density assertions, replace the toolbar-observer expectations, and add these assertions:

```js
assert.match(source, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(
  source,
  /const isTabDashboardSurface = computed\([\s\S]*dashboardLayoutSurface === 'tab'/
)
assert.match(source, /resolveTabInsightControlsVariant/)
assert.match(source, /const tabInsightControlsReserve = computed\([\s\S]*resolveTabInsightControlsReserve/)
assert.match(source, /const tabInsightControlsStyle = computed\([\s\S]*--tab-insight-controls-reserve/)
assert.match(source, /transitionTabInsightLayout/)
assert.match(source, /const tabInsightDisplay = shallowRef/)
assert.match(
  source,
  /const controlsBlock = isTabDashboardSurface\.value\s*\? tabInsightControlsReserve\.value\s*:\s*dashboardFilterControlsRef\.value\s*\? elementBlockContribution\(dashboardFilterControlsRef\.value\)\s*:\s*null/
)
assert.match(source, /resizeObserver\.observe\(containerRef\.value, \{ box: 'border-box' \}\)/)
assert.match(
  source,
  /if \(!isTabDashboardSurface\.value && dashboardFilterControlsRef\.value\)[\s\S]*resizeObserver\.observe\(dashboardFilterControlsRef\.value/
)
assert.doesNotMatch(source, /resizeObserver\.observe\(chartShowAreaRef\.value/)
assert.doesNotMatch(
  source,
  /watch\(\s*tabInsightControlsVariant[\s\S]{0,220}nextTick|watch\(\s*tabInsightControlsVariant[\s\S]{0,220}setTimeout/
)
assert.match(source, /const insightEnabled = computed\([\s\S]*enabled !== false/)
assert.match(source, /canShowInsightHeader[\s\S]*insightEnabled\.value/)
assert.match(source, /const chartComponentKey = computed\(\s*\(\) => props\.outerId \|\| props\.viewInfo\?\.id \|\| 'chart'/)
assert.doesNotMatch(source, /chartComponentKey[\s\S]{0,160}(?:frameSize|insightDensity|effectiveInsightLayout|renderVersion)/)
assert.doesNotMatch(source, /(?:sizeX|sizeY)\s*=/)
assert.match(style, /&\.dashboard-layout-surface-tab[\s\S]*--tab-insight-controls-reserve:\s*0px/)
assert.match(source, /:style="tabInsightControlsStyle"/)
assert.match(
  style,
  /dashboard-layout-surface-tab[\s\S]*dashboard-filter-controls--combined[\s\S]*flex-wrap:\s*nowrap/
)
```

Update `insightFrame.stability.test.mjs` to import `resolveTabInsightControlsReserve` and assert the exact fixed inputs:

```js
import { resolveTabInsightControlsReserve } from './tabInsightLayout.ts'

assert.deepEqual(
  ['none', 'pivot', 'date', 'combined'].map((variant) =>
    resolveCanonicalInsightFrame(
      geometryForFrame(520, 400, resolveTabInsightControlsReserve(variant))
    )
  ),
  [
    { width: 520, height: 400 },
    { width: 520, height: 400 },
    { width: 520, height: 400 },
    { width: 520, height: 400 },
  ]
)
```

- [ ] **Step 2: Run the structural tests and verify RED**

Run:

```powershell
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
```

Expected: `index.responsive-layout.test.mjs` FAILS because `SQView` has no surface prop/coordinator and still observes `dashboardFilterControlsRef`; the frame test passes because Task 2 already provides the fixed-reserve function.

- [ ] **Step 3: Add the surface prop and Tab-only reactive state**

In `index.vue`, import `shallowRef`, `type PropType`, the surface type/default, Task 2 helpers, and `InsightDisplayStrategy`:

```ts
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch, type PropType } from 'vue'
import {
  DEFAULT_DASHBOARD_LAYOUT_SURFACE,
  type DashboardLayoutSurface,
} from '@/views/dashboard/utils/dashboardLayoutSurface.ts'
import {
  createTabInsightLayoutState,
  resolveTabInsightControlsReserve,
  resolveTabInsightControlsVariant,
  transitionTabInsightLayout,
} from './tabInsightLayout.ts'
import {
  buildInsightLayoutStateKey,
  buildInsightColumns,
  detectTrendAxisGranularity,
  resolveInsightDisplay,
  type InsightDensity,
  type InsightDisplayStrategy,
  type InsightLayout,
} from '@/views/chat/component/chartInsight.ts'
```

Add this prop:

```ts
dashboardLayoutSurface: {
  type: String as PropType<DashboardLayoutSurface>,
  default: DEFAULT_DASHBOARD_LAYOUT_SURFACE,
},
```

Immediately after the existing `chartType` computed, replace the current `isDashboardSurface` declaration and add all of these declarations; do not create a duplicate `isDashboardSurface`:

```ts
const isDashboardSurface = computed(() => props.showPosition !== 'multiplexing')
const isTabDashboardSurface = computed(
  () => isDashboardSurface.value && props.dashboardLayoutSurface === 'tab'
)
const tabInsightControlsVariant = computed(() =>
  resolveTabInsightControlsVariant({
    pivot: pivotEnabled.value,
    date:
      showDashboardDateExpression.value ||
      (showDashboardDateFilter.value && !dateExpressionPickerEnabled.value),
  })
)
const tabInsightControlsReserve = computed(() =>
  resolveTabInsightControlsReserve(tabInsightControlsVariant.value)
)
const tabInsightControlsStyle = computed(() =>
  isTabDashboardSurface.value
    ? { '--tab-insight-controls-reserve': `${tabInsightControlsReserve.value}px` }
    : undefined
)
const tabInsightLayoutState = shallowRef(createTabInsightLayoutState())
const tabInsightDisplay = shallowRef<InsightDisplayStrategy | null>(null)
const reportedTabLayoutErrors = new Set<string>()
```

Replace the current `insightDisplay` computed with this main-only copy, preserving the release behavior only for `main`:

```ts
const mainInsightDisplay = computed(() => {
  const layoutStateKey = buildInsightLayoutStateKey({
    viewId: props.viewInfo?.id,
    chartType: chartType.value,
    x: renderXAxis.value,
    y: renderYAxis.value,
    series: renderSeries.value,
    dashboard: isDashboardSurface.value,
  })
  if (layoutStateKey !== previousInsightLayoutKey) {
    previousInsightLayoutKey = layoutStateKey
    previousInsightLayout = undefined
    previousInsightDensity = undefined
  }
  const measuredFrame = frameSize.value
  const display = resolveInsightDisplay({
    chartType: chartType.value,
    data: displayData.value,
    x: renderXAxis.value,
    y: renderYAxis.value,
    series: renderSeries.value,
    width: measuredFrame?.width,
    height: measuredFrame?.height,
    dashboard: isDashboardSurface.value,
    previousLayout: previousInsightLayout,
    previousDensity: previousInsightDensity,
  })
  if (measuredFrame || !isDashboardSurface.value) {
    previousInsightLayout = display.layout
    previousInsightDensity = display.density
  }
  return display
})
```

Add the pure Tab input and watcher:

```ts
const tabInsightLayoutInput = computed(() => ({
  frame: frameSize.value,
  viewId: props.viewInfo?.id,
  chartType: chartType.value,
  data: displayData.value,
  x: renderXAxis.value,
  y: renderYAxis.value,
  series: renderSeries.value,
  insight: props.viewInfo.chart?.insight,
  controlsVariant: tabInsightControlsVariant.value,
}))

watch(
  tabInsightLayoutInput,
  (input) => {
    if (!isTabDashboardSurface.value) return
    const transition = transitionTabInsightLayout(tabInsightLayoutState.value, input)
    tabInsightLayoutState.value = transition.state
    if (transition.error) {
      const reason = transition.error instanceof Error ? transition.error.message : String(transition.error)
      if (!reportedTabLayoutErrors.has(reason)) {
        reportedTabLayoutErrors.add(reason)
        console.error(`[SQView] tab insight layout failed: ${reason}`)
      }
      return
    }
    if (transition.processed && transition.display) {
      tabInsightDisplay.value = transition.display
    }
  },
  { immediate: true }
)

const unmeasuredTabInsightDisplay: InsightDisplayStrategy = {
  show: false,
  layout: 'top',
  density: 'compact',
  maxStats: 0,
  featuredSide: false,
}

const insightDisplay = computed(() =>
  isTabDashboardSurface.value
    ? tabInsightDisplay.value || unmeasuredTabInsightDisplay
    : mainInsightDisplay.value
)
```

Add the SQView-level summary switch and use it in `canShowInsightHeader`:

```ts
const insightEnabled = computed(() => props.viewInfo.chart?.insight?.enabled !== false)

const canShowInsightHeader = computed(() => {
  if (!insightEnabled.value || !showInsightHeader.value) return false
  if (isDashboardSurface.value && !frameSize.value) return false
  return insightDisplay.value.show
})
```

- [ ] **Step 4: Split canonical measurement by surface without child feedback**

Keep `elementBlockContribution` for main only. Replace `measureCanonicalFrame` with the complete branch below so Tab never reads the controls element:

```ts
function measureCanonicalFrame() {
  const container = containerRef.value
  if (!container) return false

  const style = window.getComputedStyle(container)
  const compactPaddingInline = requiredCssPixel(
    style,
    INSIGHT_FRAME_CSS_PROPERTIES.compactPaddingInline
  )
  const compactPaddingBlock = requiredCssPixel(
    style,
    INSIGHT_FRAME_CSS_PROPERTIES.compactPaddingBlock
  )
  const compactHeaderHeight = requiredCssPixel(
    style,
    INSIGHT_FRAME_CSS_PROPERTIES.compactHeaderHeight
  )
  const compactHeaderGap = requiredCssPixel(
    style,
    INSIGHT_FRAME_CSS_PROPERTIES.compactHeaderGap
  )
  const borderInlineStart = parseCssPixel(style.borderInlineStartWidth)
  const borderInlineEnd = parseCssPixel(style.borderInlineEndWidth)
  const borderBlockStart = parseCssPixel(style.borderBlockStartWidth)
  const borderBlockEnd = parseCssPixel(style.borderBlockEndWidth)
  const controlsBlock = isTabDashboardSurface.value
    ? tabInsightControlsReserve.value
    : dashboardFilterControlsRef.value
      ? elementBlockContribution(dashboardFilterControlsRef.value)
      : null
  const requiredValues = [
    compactPaddingInline,
    compactPaddingBlock,
    compactHeaderHeight,
    compactHeaderGap,
    borderInlineStart,
    borderInlineEnd,
    borderBlockStart,
    borderBlockEnd,
    controlsBlock,
  ]
  if (requiredValues.some((value) => value === null)) {
    reportFrameMeasurementError('incomplete canonical geometry')
    return false
  }

  const rect = container.getBoundingClientRect()
  const nextSize = resolveCanonicalInsightFrame({
    borderBox: { width: rect.width, height: rect.height },
    borderInline: borderInlineStart! + borderInlineEnd!,
    borderBlock: borderBlockStart! + borderBlockEnd!,
    compactPaddingInline: compactPaddingInline!,
    compactPaddingBlock: compactPaddingBlock!,
    compactHeaderHeight: compactHeaderHeight!,
    compactHeaderGap: compactHeaderGap!,
    controlsBlock: controlsBlock!,
  })
  if (!nextSize) {
    reportFrameMeasurementError('non-positive canonical frame')
    return false
  }
  if (sameInsightFrame(nextSize, frameSize.value)) return false
  frameSize.value = nextSize
  return true
}
```

This function returns `false` before assigning `frameSize` for every invalid input and preserves the existing integer `sameInsightFrame` guard.

Replace the structure watcher with separate main and Tab triggers:

```ts
const mainInsightFrameStructureKey = computed(() =>
  JSON.stringify([
    showDashboardDateExpression.value,
    showDashboardDateFilter.value && !dateExpressionPickerEnabled.value,
    pivotEnabled.value,
    locale.value,
  ])
)

watch(
  mainInsightFrameStructureKey,
  () => {
    if (!isTabDashboardSurface.value) nextTick(measureCanonicalFrame)
  },
  { flush: 'post' }
)

watch(
  tabInsightControlsVariant,
  () => {
    if (isTabDashboardSurface.value) measureCanonicalFrame()
  },
  { flush: 'post' }
)
```

Extract observer setup so the Tab path starts synchronously on mount and never observes controls:

```ts
function startInsightFrameObserver() {
  measureCanonicalFrame()
  resizeObserver = new ResizeObserver((entries) => {
    const ownsEntry = entries.some(
      (entry) =>
        entry.target === containerRef.value ||
        (!isTabDashboardSurface.value && entry.target === dashboardFilterControlsRef.value)
    )
    if (ownsEntry) measureCanonicalFrame()
  })
  if (containerRef.value) {
    resizeObserver.observe(containerRef.value, { box: 'border-box' })
  }
  if (!isTabDashboardSurface.value && dashboardFilterControlsRef.value) {
    resizeObserver.observe(dashboardFilterControlsRef.value, { box: 'border-box' })
  }
}

onMounted(() => {
  props.viewInfo.chart.sourceType = props.viewInfo.chart.sourceType ?? props.viewInfo.chart.type
  if (isTabDashboardSurface.value) {
    startInsightFrameObserver()
    return
  }
  nextTick(startInsightFrameObserver)
})
```

The Tab failure path returns without scheduling any retry; the retained main `nextTick` is outside the Tab branch and preserves the main-surface release behavior.

- [ ] **Step 5: Bind surface classes and enforce fixed toolbar reserve**

Replace the root class binding with:

```vue
<div
  ref="containerRef"
  class="chart-base-container"
  :style="tabInsightControlsStyle"
  :class="[
    `insight-density-${insightDensity}`,
    isTabDashboardSurface ? 'dashboard-layout-surface-tab' : '',
    isTabDashboardSurface ? `tab-controls-${tabInsightControlsVariant}` : '',
  ]"
>
```

Add these scoped styles inside `.chart-base-container` after its base custom properties:

```less
&.dashboard-layout-surface-tab {
  --tab-insight-controls-reserve: 0px;

  .dashboard-filter-controls {
    flex: 0 0 var(--tab-insight-controls-reserve);
    block-size: var(--tab-insight-controls-reserve);
    min-height: 0;
    overflow: hidden;
  }

  .dashboard-filter-controls--combined {
    flex-wrap: nowrap;
    margin-block: 0;

    > .pivot-toolbar,
    > .date-filter-toolbar {
      margin-block: 0;
    }
  }
}
```

Keep `:key="chartComponentKey"` unchanged. Both existing `ChartInsightHeader` branches continue to use `canShowInsightHeader`, so an explicit `insight.enabled=false` prevents mounting at the `SQView` layer.

- [ ] **Step 6: Run focused integration tests and verify GREEN**

Run:

```powershell
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
node src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/dashboard/preview/SQPreview.resize-observer.test.mjs
node src/views/dashboard/editor/DashboardEditor.resize-lifecycle.test.mjs
```

Expected: all six commands exit `0`; structural assertions confirm the Tab observer is root-only and `ChartComponent` remains a guarded size consumer.

- [ ] **Step 7: Commit Task 3**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
git commit -m "修复：切断 Tab 卡片内容尺寸反馈链"
```

---

### Task 4: 完整回归与真实 Tab 验收

**Files:**
- Verify only; no source file is created solely to claim success.

**Interfaces:**
- Consumes: all Task 1-3 deliverables.
- Produces: reproducible command output and browser observations proving the user-visible loop is gone.

- [ ] **Step 1: Run the complete focused regression set**

From `frontend` run:

```powershell
node src/views/dashboard/utils/dashboardLayoutSurface.contract.test.mjs
node src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/chat/component/ChartComponent.atomic-render.test.mjs
node src/views/dashboard/preview/SQPreview.resize-observer.test.mjs
node src/views/dashboard/editor/DashboardEditor.resize-lifecycle.test.mjs
npm run build
```

Expected: every Node command exits `0`; `npm run build` completes without TypeScript, Vue template, or bundle errors.

- [ ] **Step 2: Check the diff for scope and forbidden writes**

Run from the linked worktree root:

```powershell
git diff --check
rg -n "resizeObserver\.observe\((chartShowAreaRef|dashboardFilterControlsRef)" frontend/src/views/dashboard/components/sq-view/index.vue
rg -n "(?:sizeX|sizeY)\s*=" frontend/src/views/dashboard/components/sq-view/index.vue
git status --short
```

Expected: `git diff --check` is clean; the first `rg` only finds the guarded non-Tab controls observer and never `chartShowAreaRef`; the second `rg` has no matches; status contains no build artifacts.

- [ ] **Step 3: Start or restart the complete local stack using the repository runbook**

Use the `starting-chat-bi-local` skill. The frontend must run from this linked worktree so the browser exercises the new code; API `8000`, MCP `8001`, and one Worker must share the same non-`default` `local-*` queue. Use the standard stack/status commands with `-SkipDatabase -SkipRedis -SkipNginx`, verify frontend `5173` independently, and confirm:

```text
frontend 5173: HTTP 200
backend 8000: HTTP response (401 is acceptable)
MCP 8001: listening (404 at / is acceptable)
Worker: running on the same local-* queue
LLM settings: 120 900 1
```

If `5173` belongs to a Vite process from another checkout, stop only after verifying its normalized command path, then start Vite from `D:\AIWork3\chat-bi\.worktrees\codex-tab-card-content-adaptive\frontend`.

- [ ] **Step 4: Verify Tab preview stability in the application browser**

Use the Browser skill against `http://127.0.0.1:5173/`. Open a dashboard containing an `SQTab` with an `SQView`, select the preview surface, and capture a three-second sample after each action:

```js
const samples = []
const root = document.querySelector('.dashboard-layout-surface-tab')
for (let index = 0; index < 30; index += 1) {
  const chart = root?.querySelector('.chart-container')
  samples.push({
    root: root ? [root.getBoundingClientRect().width, root.getBoundingClientRect().height] : null,
    density: [...(root?.classList || [])].find((name) => name.startsWith('insight-density-')),
    top: Boolean(root?.querySelector(':scope > .chart-show-area > .chart-insight-header')),
    side: Boolean(root?.querySelector('.chart-content-row.side-layout .chart-insight-header')),
    chart: chart ? [chart.getBoundingClientRect().width, chart.getBoundingClientRect().height] : null,
    activeLayers: root?.querySelectorAll('.chart-render-layer--active').length || 0,
    loading: Boolean(root?.querySelector('.chart-loading-info, .chart-refresh-overlay')),
  })
  await new Promise((resolve) => setTimeout(resolve, 100))
}
samples
```

Perform: summary on/off, top-summary chart to side-summary chart, table/metric no-summary chart, Tab hide/show, Tab container resize, Card resize, and two same-structure data refreshes. For each settled sample window require: one root geometry, one density/layout state, at most one active render layer, no loading oscillation, no `ResizeObserver loop` console error, and unchanged persisted `sizeX/sizeY`.

- [ ] **Step 5: Verify Tab editor stability independently**

Repeat Step 4 in the Tab editor surface. Record the editor Card pixel size separately from preview; different root dimensions and different density/layout are valid. Require the same one-state three-second stability and verify a user Card resize produces one new stable root geometry without any child-driven `sizeX/sizeY` mutation.

- [ ] **Step 6: Review final history and worktree state**

Run:

```powershell
git log --oneline -5
git status --short
```

Expected: the design and implementation-plan documentation commits plus three Chinese implementation commits are present; the linked worktree is clean. Do not push unless the user explicitly requests it.
