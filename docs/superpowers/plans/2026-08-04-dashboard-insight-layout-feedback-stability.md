# 看板摘要布局反馈环全局稳定修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有 `SQView` 看板图表使用不受摘要输出影响的规范化布局尺寸，消除抽屉卡片在异步数据回填后的持续跳动，同时保留真实 resize 的响应与迟滞。

**Architecture:** 新增纯几何模块，从卡片 border box、CSS 中的 compact 基准 chrome 和密度无关的工具栏占用计算策略尺寸。`SQView` 只观察根 border box 与工具栏包装层，不再观察 `.chart-show-area` 或从尺寸回调直接重建图表；`ChartComponent` 继续独占实际图表 resize。摘要显隐移除 `previousShow`，布局与密度迟滞保持不变。

**Tech Stack:** Vue 3 Composition API、TypeScript、Less、原生 `ResizeObserver`、Node `assert` 聚焦测试、Vite、浏览器真实 DOM 验证。

## Global Constraints

- 所有源码、测试和文档修改都在 linked worktree `D:\AIWork3\chat-bi\.worktrees\codex-dashboard-insight-layout-stability`、分支 `codex/dashboard-insight-layout-stability` 中完成。
- 不为单个看板 ID、数据源、业务字段、图表类型或录屏尺寸增加运行时特例。
- 不观察 `.chart-show-area` 作为布局策略触发源；只允许根 border box、工具栏有效贡献和明确的语义结构 watcher 触发重测。
- compact 基准固定为水平 padding `16px`、垂直 padding `14px`、标题最小高度 `34px`、标题下边距 `10px`，且这些值必须由 CSS 自定义属性直接驱动实际样式。
- `.dashboard-filter-controls` 在固定根宽度和固定结构下的 block contribution 必须与 `regular/compact/mini/basic` density 无关。
- 保留 `previousLayout`、`previousDensity` 以及现有图表布局资格；删除 `previousShow` 及其跨轴重新进入门槛。
- 初始无有效尺寸时保持 `unmeasured`、使用 compact 根样式并隐藏摘要；无效 CSS/非正尺寸不得静默替代，只保留上一有效尺寸并对同一错误诊断一次。
- 实施严格遵循 TDD：每个行为先写测试并确认失败，再写生产代码。
- 最终浏览器回归使用 workspace `flam`、看板 `f26870db68cb44bd974b0160ea91cdae`、视口 `1510x936`，稳定采样容差为 `1px`。

---

## File Structure

- Create `frontend/src/views/dashboard/components/sq-view/insightFrame.ts`: 纯 CSS 像素解析、规范化帧计算和尺寸相等判断，不访问 DOM。
- Create `frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs`: 规范化几何、边界网格和所有摘要图表族的闭环收敛测试。
- Modify `frontend/src/views/chat/component/chartInsight.ts`: 删除 `previousShow` 与摘要重新进入历史门槛，保留布局/密度迟滞。
- Modify `frontend/src/views/chat/component/chartInsight.layout-stability.test.mjs`: 固定布局历史验证摘要显隐的路径无关行为。
- Modify `frontend/src/views/dashboard/components/sq-view/index.vue`: 接入规范化帧、根/工具栏观察边界、unmeasured 状态和 density 无关工具栏盒模型。
- Modify `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`: 固化测量所有权、CSS 变量、工具栏不变量和无摘要生命周期契约。
- Verify `frontend/src/views/chat/component/ChartComponent.vue`: 不修改其既有 resize 所有权；浏览器验证它能独立适配实际空间。

---

### Task 1: Remove Cross-Axis Summary Visibility History

**Files:**
- Modify: `frontend/src/views/chat/component/chartInsight.layout-stability.test.mjs`
- Modify: `frontend/src/views/chat/component/chartInsight.ts:28-32,365-440`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:143-147,2094-2132`

**Interfaces:**
- Consumes: `resolveInsightDisplay(params)` with `previousLayout` and `previousDensity`.
- Produces: `resolveInsightDisplay(params)` without `previousShow`; `SQView` retains only `previousInsightLayout` and `previousInsightDensity`.

- [ ] **Step 1: Replace sticky-show assertions with a failing fixed-layout-history regression**

Replace the existing `previousShow` re-entry assertions in `chartInsight.layout-stability.test.mjs` with:

```js
const hiddenByWidth = resolveInsightDisplay({
  ...trend,
  width: 439,
  height: 400,
  previousLayout: 'top',
  previousDensity: 'mini',
})
assert.equal(hiddenByWidth.show, false, '宽度低于可读下界时应隐藏摘要')

const restoredAfterWidth = resolveInsightDisplay({
  ...trend,
  width: 520,
  height: 400,
  previousLayout: 'top',
  previousDensity: 'mini',
  previousShow: false,
})
const freshAtRestoredSize = resolveInsightDisplay({
  ...trend,
  width: 520,
  height: 400,
  previousLayout: 'top',
  previousDensity: 'mini',
})
assert.equal(restoredAfterWidth.show, true, '恢复宽度后不应再额外要求高度达到 430px')
assert.deepEqual(
  restoredAfterWidth,
  freshAtRestoredSize,
  '固定布局与密度历史时，显隐结果不能依赖 previousShow 路径'
)

const topHistory = resolveInsightDisplay({
  ...trend,
  width: 1102,
  height: 270,
  previousLayout: 'top',
  previousDensity: 'basic',
})
const sideHistory = resolveInsightDisplay({
  ...trend,
  width: 1102,
  height: 270,
  previousLayout: 'side',
  previousDensity: 'mini',
})
assert.equal(topHistory.layout, 'top', '布局迟滞区允许保留 top 历史')
assert.equal(sideHistory.layout, 'side', '布局迟滞区允许保留 side 历史')
```

- [ ] **Step 2: Run the policy test and verify the new regression fails**

Run:

```powershell
cd frontend
node src/views/chat/component/chartInsight.layout-stability.test.mjs
```

Expected: FAIL at `恢复宽度后不应再额外要求高度达到 430px`; current result remains `false` because `previousShow=false` also requires height `>=430`.

- [ ] **Step 3: Remove `previousShow` from the strategy and SQView state**

In `chartInsight.ts`:

```ts
// Delete TOP_SUMMARY_REENTER_MIN_HEIGHT.
// Delete previousShow from resolveInsightDisplay params.

if (layout === 'top') {
  const topSummaryTooSmall = width < TOP_BASIC_MAX_WIDTH || height < TOP_BASIC_MAX_HEIGHT
  if (topSummaryTooSmall) {
    return {
      show: false,
      layout,
      density: 'basic',
      maxStats: 0,
      featuredSide: false,
    }
  }
```

In `SQView/index.vue`, delete `previousInsightShow`, its reset, its argument to `resolveInsightDisplay()`, and its assignment. Keep the existing layout state key reset for layout and density.

- [ ] **Step 4: Run the policy regressions**

Run:

```powershell
cd frontend
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
```

Expected: both print their `passed` lines with exit code `0`.

- [ ] **Step 5: Commit the deterministic show policy**

```powershell
git add -- frontend/src/views/chat/component/chartInsight.ts frontend/src/views/chat/component/chartInsight.layout-stability.test.mjs frontend/src/views/dashboard/components/sq-view/index.vue
git commit -m "修复：移除看板摘要显隐历史粘滞"
```

---

### Task 2: Add Canonical Insight Frame Geometry

**Files:**
- Create: `frontend/src/views/dashboard/components/sq-view/insightFrame.ts`
- Create: `frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs`

**Interfaces:**
- Consumes: numeric border-box and chrome geometry; `resolveInsightDisplay()` from Task 1.
- Produces:
  - `INSIGHT_FRAME_CSS_PROPERTIES`
  - `parseCssPixel(value: string): number | null`
  - `resolveCanonicalInsightFrame(geometry: InsightFrameGeometry): InsightFrameSize | null`
  - `sameInsightFrame(left: InsightFrameSize | null, right: InsightFrameSize | null): boolean`

- [ ] **Step 1: Write the failing geometry and closed-loop test**

Create `insightFrame.stability.test.mjs` with the following complete scenario structure:

```js
import assert from 'node:assert/strict'
import { resolveInsightDisplay } from '../../../chat/component/chartInsight.ts'
import {
  parseCssPixel,
  resolveCanonicalInsightFrame,
  sameInsightFrame,
} from './insightFrame.ts'

assert.equal(parseCssPixel('16px'), 16)
assert.equal(parseCssPixel(' -0.5px '), -0.5)
assert.equal(parseCssPixel('0'), null)
assert.equal(parseCssPixel('calc(10px + 2px)'), null)
assert.equal(parseCssPixel(''), null)

function geometryForFrame(width, height, controlsBlock = 0) {
  return {
    borderBox: { width: width + 32, height: height + 72 + controlsBlock },
    borderInline: 0,
    borderBlock: 0,
    compactPaddingInline: 16,
    compactPaddingBlock: 14,
    compactHeaderHeight: 34,
    compactHeaderGap: 10,
    controlsBlock,
  }
}

assert.deepEqual(
  resolveCanonicalInsightFrame({
    borderBox: { width: 1179, height: 360 },
    borderInline: 0,
    borderBlock: 0,
    compactPaddingInline: 16,
    compactPaddingBlock: 14,
    compactHeaderHeight: 34,
    compactHeaderGap: 10,
    controlsBlock: 36,
  }),
  { width: 1147, height: 252 },
  '录屏卡片必须归一到 compact 稳定帧，不能继续使用 basic/mini 的 280/270px 子区域'
)
assert.equal(resolveCanonicalInsightFrame(geometryForFrame(0, 300)), null)
assert.equal(
  sameInsightFrame(
    resolveCanonicalInsightFrame(geometryForFrame(520, 400, 36)),
    { width: 520, height: 400 }
  ),
  true
)

const dates = [
  { date: '2026-08-01', value: 10, group: 'A' },
  { date: '2026-08-02', value: 12, group: 'B' },
]
const metricAxes = ['m1', 'm2', 'm3', 'm4'].map((value) => ({ value }))
const groupedData = ['A', 'B', 'C', 'D', 'E', 'F'].map((group, index) => ({
  date: '2026-08-01',
  value: index + 1,
  group,
}))
const weeklyDates = [
  { date: '2026-08-01 week', value: 10 },
  { date: '2026-08-08 week', value: 12 },
]
const monthlyDates = [
  { date: '2026-07', value: 10 },
  { date: '2026-08', value: 12 },
]
const scenarios = [
  { name: 'multi-line', chartType: 'line', data: dates, x: [{ value: 'date' }], y: metricAxes, series: [] },
  { name: 'multi-area', chartType: 'area', data: dates, x: [{ value: 'date' }], y: metricAxes, series: [] },
  { name: 'multi-column', chartType: 'column', data: dates, x: [{ value: 'date' }], y: metricAxes, series: [] },
  { name: 'multi-bar', chartType: 'bar', data: dates, x: [{ value: 'date' }], y: metricAxes, series: [] },
  { name: 'six-groups', chartType: 'line', data: groupedData, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [{ value: 'group' }] },
  { name: 'sankey', chartType: 'sankey', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'treemap', chartType: 'treemap', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'wide-day-trend', chartType: 'line', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'wide-week-trend', chartType: 'line', data: weeklyDates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'wide-month-trend', chartType: 'line', data: monthlyDates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'rich-bar', chartType: 'bar', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'rich-column', chartType: 'column', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'rich-heatmap', chartType: 'heatmap', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'rich-scatter', chartType: 'scatter', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'rich-funnel', chartType: 'funnel', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'pie', chartType: 'pie', data: dates, x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
  { name: 'empty-line', chartType: 'line', data: [], x: [{ value: 'date' }], y: [{ value: 'value' }], series: [] },
]
const frameWidths = [299, 300, 301, 439, 440, 441, 499, 500, 501, 559, 560, 561, 679, 680, 681, 759, 760, 761, 899, 900, 901, 1099, 1100, 1101]
const frameHeights = [249, 250, 251, 259, 260, 261, 279, 280, 281, 329, 330, 331, 359, 360, 361, 389, 390, 391, 429, 430, 431]

function assertConverges(scenario, frame) {
  let previousLayout
  let previousDensity
  let previousSignature = ''
  for (let step = 0; step < 8; step += 1) {
    const display = resolveInsightDisplay({
      ...scenario,
      dashboard: true,
      width: frame.width,
      height: frame.height,
      previousLayout,
      previousDensity,
    })
    const signature = JSON.stringify(display)
    if (signature === previousSignature) return
    previousSignature = signature
    previousLayout = display.layout
    previousDensity = display.density
  }
  assert.fail(`${scenario.name} 未在稳定帧 ${frame.width}x${frame.height} 收敛`)
}

for (const scenario of scenarios) {
  for (const width of frameWidths) {
    for (const height of frameHeights) {
      for (const controlsBlock of [0, 30, 36, 66]) {
        const frame = resolveCanonicalInsightFrame(geometryForFrame(width, height, controlsBlock))
        assert.ok(frame, `${scenario.name} 应生成正规范化尺寸`)
        assert.deepEqual(frame, { width, height })
        assertConverges(scenario, frame)
      }
    }
  }
}

console.log('insight frame stability tests passed')
```

- [ ] **Step 2: Run the new test and verify the module is missing**

```powershell
cd frontend
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `insightFrame.ts`.

- [ ] **Step 3: Implement the pure geometry module**

Create `insightFrame.ts`:

```ts
export interface InsightFrameSize {
  width: number
  height: number
}

export interface InsightFrameGeometry {
  borderBox: InsightFrameSize
  borderInline: number
  borderBlock: number
  compactPaddingInline: number
  compactPaddingBlock: number
  compactHeaderHeight: number
  compactHeaderGap: number
  controlsBlock: number
}

export const INSIGHT_FRAME_CSS_PROPERTIES = {
  compactPaddingInline: '--insight-frame-compact-padding-inline',
  compactPaddingBlock: '--insight-frame-compact-padding-block',
  compactHeaderHeight: '--insight-frame-compact-header-height',
  compactHeaderGap: '--insight-frame-compact-header-gap',
} as const

const CSS_PIXEL_PATTERN = /^-?(?:\d+(?:\.\d+)?|\.\d+)px$/

export function parseCssPixel(value: string): number | null {
  const normalized = String(value || '').trim()
  if (!CSS_PIXEL_PATTERN.test(normalized)) return null
  const parsed = Number(normalized.slice(0, -2))
  return Number.isFinite(parsed) ? parsed : null
}

export function resolveCanonicalInsightFrame(
  geometry: InsightFrameGeometry
): InsightFrameSize | null {
  const values = [
    geometry.borderBox.width,
    geometry.borderBox.height,
    geometry.borderInline,
    geometry.borderBlock,
    geometry.compactPaddingInline,
    geometry.compactPaddingBlock,
    geometry.compactHeaderHeight,
    geometry.compactHeaderGap,
    geometry.controlsBlock,
  ]
  if (values.some((value) => !Number.isFinite(value) || value < 0)) return null

  const width = Math.round(
    geometry.borderBox.width - geometry.borderInline - geometry.compactPaddingInline * 2
  )
  const height = Math.round(
    geometry.borderBox.height
      - geometry.borderBlock
      - geometry.compactPaddingBlock * 2
      - geometry.compactHeaderHeight
      - geometry.compactHeaderGap
      - geometry.controlsBlock
  )
  return width > 0 && height > 0 ? { width, height } : null
}

export function sameInsightFrame(
  left: InsightFrameSize | null,
  right: InsightFrameSize | null
) {
  return left?.width === right?.width && left?.height === right?.height
}
```

- [ ] **Step 4: Run the geometry scan and policy regressions**

```powershell
cd frontend
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
```

Expected: all three print `passed`; the grid scan exits `0` without a non-converging scenario.

- [ ] **Step 5: Commit the geometry boundary**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/insightFrame.ts frontend/src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
git commit -m "新增：看板摘要规范化尺寸计算"
```

---

### Task 3: Integrate Stable Measurement Ownership in SQView

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:138-163,2077-2200,2305-2328,2346-2460,2750-3138`

**Interfaces:**
- Consumes: all exports from `insightFrame.ts` in Task 2.
- Produces: `frameSize: Ref<InsightFrameSize | null>`, `measureCanonicalFrame(): boolean`, root and controls border-box observation, density-independent controls contribution.

- [ ] **Step 1: Rewrite the source contract test to require the new ownership**

In `index.responsive-layout.test.mjs`, keep the existing flex zero-basis assertions and replace old `measureFrame`/observer assertions with these contracts:

```js
assert.match(source, /ref="dashboardFilterControlsRef"[^>]*class="dashboard-filter-controls"/)
assert.match(source, /const frameSize = ref<InsightFrameSize \| null>\(null\)/)
assert.match(source, /function measureCanonicalFrame\(\) \{[\s\S]*resolveCanonicalInsightFrame/)
assert.match(source, /if \(isDashboardSurface\.value && !frameSize\.value\) \{\s*return false\s*\}/)
assert.match(
  source,
  /if \(measuredFrame \|\| !isDashboardSurface\.value\) \{\s*previousInsightLayout = display\.layout\s*previousInsightDensity = display\.density/,
  'unmeasured 默认展示不能污染首次有效测量的迟滞历史'
)
assert.match(source, /resizeObserver\.observe\(containerRef\.value, \{ box: 'border-box' \}\)/)
assert.match(source, /resizeObserver\.observe\(dashboardFilterControlsRef\.value, \{ box: 'border-box' \}\)/)
assert.doesNotMatch(source, /resizeObserver\.observe\(chartShowAreaRef\.value/)

const observerCallback = source.match(
  /resizeObserver = new ResizeObserver\(\([^)]*\) => \{([\s\S]*?)\r?\n\s*\}\)/
)
assert.ok(observerCallback, '需要统一的稳定边界 ResizeObserver')
assert.match(observerCallback[1], /measureCanonicalFrame\(\)/)
assert.doesNotMatch(
  observerCallback[1],
  /scheduleRenderChart/,
  '尺寸回调只能更新策略尺寸，图表 resize 由 ChartComponent 独占'
)

assert.match(style, /--insight-frame-compact-padding-inline:\s*16px/)
assert.match(style, /--insight-frame-compact-padding-block:\s*14px/)
assert.match(style, /--insight-frame-compact-header-height:\s*34px/)
assert.match(style, /--insight-frame-compact-header-gap:\s*10px/)
assert.match(style, /padding:\s*var\(--insight-frame-compact-padding-block\)\s+var\(--insight-frame-compact-padding-inline\)/)
assert.match(style, /min-height:\s*var\(--insight-frame-compact-header-height\)/)
assert.match(style, /margin-bottom:\s*var\(--insight-frame-compact-header-gap\)/)
assert.match(
  style,
  /\.dashboard-filter-controls--combined\s*\{[\s\S]*> \.pivot-toolbar\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0/s
)
assert.doesNotMatch(
  style,
  /\.pivot-toolbar\s*\{\s*margin-bottom:\s*4px/,
  'density 不得改变工具栏外层 block contribution'
)
assert.match(source, /type !== 'table' && type !== 'metric'/)
```

- [ ] **Step 2: Run the responsive contract and verify it fails on old ownership**

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
```

Expected: FAIL because `dashboardFilterControlsRef`, nullable `frameSize`, CSS variables, border-box options and canonical measurement do not exist.

- [ ] **Step 3: Add refs, nullable frame state and DOM geometry readers**

Import the Task 2 APIs and replace the frame declarations with:

```ts
import {
  INSIGHT_FRAME_CSS_PROPERTIES,
  parseCssPixel,
  resolveCanonicalInsightFrame,
  sameInsightFrame,
  type InsightFrameSize,
} from './insightFrame.ts'

const containerRef = ref<HTMLElement | null>(null)
const dashboardFilterControlsRef = ref<HTMLElement | null>(null)
const chartShowAreaRef = ref<HTMLElement | null>(null)
const frameSize = ref<InsightFrameSize | null>(null)
const reportedFrameMeasurementErrors = new Set<string>()
```

Add the exact measurement helpers near the current `measureFrame()` location:

```ts
function reportFrameMeasurementError(reason: string) {
  if (reportedFrameMeasurementErrors.has(reason)) return
  reportedFrameMeasurementErrors.add(reason)
  console.error(`[SQView] insight frame measurement failed: ${reason}`)
}

function requiredCssPixel(style: CSSStyleDeclaration, property: string) {
  const value = parseCssPixel(style.getPropertyValue(property))
  if (value === null) reportFrameMeasurementError(`invalid ${property}`)
  return value
}

function elementBlockContribution(element: HTMLElement) {
  const style = window.getComputedStyle(element)
  const marginStart = parseCssPixel(style.marginBlockStart)
  const marginEnd = parseCssPixel(style.marginBlockEnd)
  if (marginStart === null || marginEnd === null) {
    reportFrameMeasurementError('invalid dashboard filter block margin')
    return null
  }
  return element.getBoundingClientRect().height + marginStart + marginEnd
}

function measureCanonicalFrame() {
  const container = containerRef.value
  const controls = dashboardFilterControlsRef.value
  if (!container || !controls) return false

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
  const controlsBlock = elementBlockContribution(controls)
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

- [ ] **Step 4: Wire unmeasured behavior, structural triggers and observer ownership**

Use a local `measuredFrame = frameSize.value` when computing `insightDisplay`. Pass its optional width/height to `resolveInsightDisplay()`, but only persist layout/density history after a valid measurement:

```ts
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
```

Change `canShowInsightHeader` so dashboard summaries remain hidden until a valid frame exists:

```ts
const canShowInsightHeader = computed(() => {
  if (!showInsightHeader.value) return false
  if (isDashboardSurface.value && !frameSize.value) return false
  return insightDisplay.value.show
})
```

Add a stable structure key and post-render measurement:

```ts
const insightFrameStructureKey = computed(() =>
  JSON.stringify([
    showDashboardDateExpression.value,
    showDashboardDateFilter.value && !dateExpressionPickerEnabled.value,
    pivotEnabled.value,
    locale.value,
  ])
)

watch(
  insightFrameStructureKey,
  () => nextTick(measureCanonicalFrame),
  { flush: 'post' }
)
```

Replace the mounted observer with:

```ts
onMounted(() => {
  props.viewInfo.chart['sourceType'] =
    props.viewInfo.chart['sourceType'] ?? props.viewInfo.chart.type
  nextTick(() => {
    measureCanonicalFrame()
    resizeObserver = new ResizeObserver((entries) => {
      const ownsEntry = entries.some(
        (entry) =>
          entry.target === containerRef.value ||
          entry.target === dashboardFilterControlsRef.value
      )
      if (ownsEntry) measureCanonicalFrame()
    })
    if (containerRef.value) {
      resizeObserver.observe(containerRef.value, { box: 'border-box' })
    }
    if (dashboardFilterControlsRef.value) {
      resizeObserver.observe(dashboardFilterControlsRef.value, { box: 'border-box' })
    }
  })
})
```

Add `ref="dashboardFilterControlsRef"` to the always-mounted `.dashboard-filter-controls`. Do not observe `chartShowAreaRef` and do not call `scheduleRenderChart()` from this observer.

- [ ] **Step 5: Co-locate compact CSS values and make toolbar contribution density-independent**

Update the root and header declarations:

```less
.chart-base-container {
  --insight-frame-compact-padding-inline: 16px;
  --insight-frame-compact-padding-block: 14px;
  --insight-frame-compact-header-height: 34px;
  --insight-frame-compact-header-gap: 10px;

  padding: var(--insight-frame-compact-padding-block)
    var(--insight-frame-compact-padding-inline) !important;

  .header-bar {
    min-height: var(--insight-frame-compact-header-height);
    margin-bottom: var(--insight-frame-compact-header-gap);
  }
}
```

In `.dashboard-filter-controls--combined > .pivot-toolbar`, add:

```less
flex: 1 1 0;
min-width: 0;
```

Remove only the density-specific `margin-bottom: 4px` from `.insight-density-mini/.insight-density-basic .pivot-toolbar`. Keep its smaller internal `gap` and hidden secondary items; their content no longer controls combined flex line allocation.

- [ ] **Step 6: Run focused tests and fix only contract mismatches**

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
```

Expected: all four print `passed`. If the observer regex cannot isolate the callback because of formatting, adjust the test parser to the exact callback boundary; do not weaken the ownership assertions.

- [ ] **Step 7: Run frontend type/build validation**

```powershell
cd frontend
if (!(Test-Path node_modules)) { npm ci }
npm run build
```

Expected: `vue-tsc -b` and `vite build` exit `0`. Existing bundle-size warnings are informational; TypeScript errors in the new geometry path must be fixed before proceeding.

- [ ] **Step 8: Commit the SQView ownership change**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
git commit -m "修复：统一看板摘要稳定尺寸测量"
```

---

### Task 4: Real DOM and Exact-Reproduction Verification

**Files:**
- Verify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Verify: `frontend/src/views/chat/component/ChartComponent.vue`
- Verify: dashboard `f26870db68cb44bd974b0160ea91cdae` in workspace `flam`

**Interfaces:**
- Consumes: completed Tasks 1-3 and the local four-service stack.
- Produces: browser evidence that density/toolbars preserve canonical geometry and the recorded card no longer oscillates.

- [ ] **Step 1: Start or restart the complete local stack from the task worktree**

Use the `starting-chat-bi-local` skill. The backend virtual environment is in the primary checkout and this task changes frontend code only, so start API/MCP/Worker from `D:\AIWork3\chat-bi`:

```powershell
Set-Location D:\AIWork3\chat-bi
.\tools\stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
```

Start the task worktree frontend from `D:\AIWork3\chat-bi\.worktrees\codex-dashboard-insight-layout-stability\frontend` on `0.0.0.0:5173` with `npm run dev`. Then run the backend status command from the primary checkout:

```powershell
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: API `8000`, MCP `8001`, frontend `5173`, and one isolated-queue Worker are all running. Confirm the resolved LLM values are `LLM_REQUEST_TIMEOUT=120`, `LLM_TASK_MAX_WAIT_SECONDS=900`, `LLM_MAX_RETRIES=1`.

- [ ] **Step 2: Run a real DOM density/toolbar invariant check**

Using the in-app browser, log in, switch to workspace `flam`, open:

```text
http://127.0.0.1:5173/dashboard/index?resourceId=f26870db68cb44bd974b0160ea91cdae
```

At viewport `1510x936`, execute this browser-side check on the first chart card:

```js
async function nextPaint() {
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
}

function blockContribution(element) {
  const style = getComputedStyle(element)
  return element.getBoundingClientRect().height
    + Number.parseFloat(style.marginBlockStart)
    + Number.parseFloat(style.marginBlockEnd)
}

const root = document.querySelector(
  '.canvas-container .wrapper-outer.is-report-chart-target .chart-base-container'
)
if (!(root instanceof HTMLElement)) throw new Error('first dashboard chart not found')
const controls = root.querySelector('.dashboard-filter-controls')
if (!(controls instanceof HTMLElement)) throw new Error('dashboard filter controls not found')

const originalClass = root.className
const results = []
for (const density of ['regular', 'compact', 'mini', 'basic']) {
  root.classList.remove(
    'insight-density-regular',
    'insight-density-compact',
    'insight-density-mini',
    'insight-density-basic'
  )
  root.classList.add(`insight-density-${density}`)
  await nextPaint()
  const rootStyle = getComputedStyle(root)
  const rect = root.getBoundingClientRect()
  const controlsBlock = blockContribution(controls)
  const width = Math.round(
    rect.width
      - Number.parseFloat(rootStyle.borderInlineStartWidth)
      - Number.parseFloat(rootStyle.borderInlineEndWidth)
      - Number.parseFloat(rootStyle.getPropertyValue('--insight-frame-compact-padding-inline')) * 2
  )
  const height = Math.round(
    rect.height
      - Number.parseFloat(rootStyle.borderBlockStartWidth)
      - Number.parseFloat(rootStyle.borderBlockEndWidth)
      - Number.parseFloat(rootStyle.getPropertyValue('--insight-frame-compact-padding-block')) * 2
      - Number.parseFloat(rootStyle.getPropertyValue('--insight-frame-compact-header-height'))
      - Number.parseFloat(rootStyle.getPropertyValue('--insight-frame-compact-header-gap'))
      - controlsBlock
  )
  results.push({ density, width, height, controlsBlock })
}
root.className = originalClass
await nextPaint()

const widthSpread = Math.max(...results.map((item) => item.width)) - Math.min(...results.map((item) => item.width))
const heightSpread = Math.max(...results.map((item) => item.height)) - Math.min(...results.map((item) => item.height))
const controlsSpread = Math.max(...results.map((item) => item.controlsBlock)) - Math.min(...results.map((item) => item.controlsBlock))
if (widthSpread > 1 || heightSpread > 1 || controlsSpread > 1) {
  throw new Error(`density box model changed canonical frame: ${JSON.stringify(results)}`)
}
results
```

Then run the complete mode/locale fixture matrix below. It clones the rendered scoped DOM off-screen, so it exercises the real compiled Less without changing Vue state:

```js
const liveRoot = document.querySelector(
  '.canvas-container .wrapper-outer.is-report-chart-target .chart-base-container'
)
if (!(liveRoot instanceof HTMLElement)) throw new Error('chart root not found')
const liveControls = liveRoot.querySelector('.dashboard-filter-controls')
if (!(liveControls instanceof HTMLElement)) throw new Error('controls root not found')
const dateTemplate = liveControls.querySelector('.date-filter-toolbar')
const pivotTemplate = liveControls.querySelector('.pivot-toolbar')
const dividerTemplate = liveControls.querySelector('.dashboard-filter-divider')
if (!(dateTemplate instanceof HTMLElement)) throw new Error('date toolbar template not found')
if (!(pivotTemplate instanceof HTMLElement)) throw new Error('pivot toolbar template not found')

const fixture = liveRoot.cloneNode(true)
if (!(fixture instanceof HTMLElement)) throw new Error('failed to clone chart root')
fixture.style.setProperty('position', 'fixed', 'important')
fixture.style.setProperty('left', '-10000px', 'important')
fixture.style.setProperty('top', '0', 'important')
fixture.style.setProperty('height', '420px', 'important')
fixture.style.setProperty('visibility', 'hidden', 'important')
fixture.style.setProperty('pointer-events', 'none', 'important')
document.body.append(fixture)

const fixtureControls = fixture.querySelector('.dashboard-filter-controls')
if (!(fixtureControls instanceof HTMLElement)) throw new Error('fixture controls not found')
const densityClasses = [
  'insight-density-regular',
  'insight-density-compact',
  'insight-density-mini',
  'insight-density-basic',
]
const modes = [
  { name: 'none', width: 900, combined: false, nodes: [] },
  { name: 'date-only', width: 900, combined: false, nodes: ['date'] },
  { name: 'pivot-only', width: 900, combined: false, nodes: ['pivot'] },
  { name: 'combined-row', width: 900, combined: true, nodes: ['pivot', 'divider', 'date'] },
  { name: 'combined-wrap', width: 300, combined: true, nodes: ['pivot', 'divider', 'date'], forceWrap: true },
]
const localeText = {
  'zh-CN': { date: '最近二十八天', pivot: '按自然周查看' },
  en: { date: 'Most recent twenty-eight days', pivot: 'View by calendar week' },
}
const matrix = []

function cloneModeNode(kind) {
  if (kind === 'date') return dateTemplate.cloneNode(true)
  if (kind === 'pivot') return pivotTemplate.cloneNode(true)
  if (dividerTemplate instanceof HTMLElement) return dividerTemplate.cloneNode(true)
  const divider = document.createElement('span')
  divider.className = 'dashboard-filter-divider'
  divider.setAttribute('aria-hidden', 'true')
  return divider
}

for (const [localeName, labels] of Object.entries(localeText)) {
  for (const mode of modes) {
    fixture.style.setProperty('width', `${mode.width}px`, 'important')
    fixtureControls.classList.toggle('dashboard-filter-controls--combined', mode.combined)
    fixtureControls.replaceChildren(...mode.nodes.map(cloneModeNode))
    const date = fixtureControls.querySelector('.date-filter-trigger-label, .date-expression-trigger')
    const pivot = fixtureControls.querySelector('.pivot-chip')
    if (date instanceof HTMLElement) date.textContent = labels.date
    if (pivot instanceof HTMLElement) pivot.textContent = labels.pivot
    if (mode.forceWrap) {
      const wrappedPivot = fixtureControls.querySelector('.pivot-toolbar')
      const wrappedDate = fixtureControls.querySelector('.date-filter-toolbar')
      if (wrappedPivot instanceof HTMLElement) wrappedPivot.style.flex = '1 1 160px'
      if (wrappedDate instanceof HTMLElement) wrappedDate.style.minWidth = '220px'
    }

    const modeResults = []
    for (const densityClass of densityClasses) {
      fixture.classList.remove(...densityClasses)
      fixture.classList.add(densityClass)
      await nextPaint()
      modeResults.push({
        density: densityClass,
        controlsBlock: blockContribution(fixtureControls),
      })
    }
    const values = modeResults.map((item) => item.controlsBlock)
    const spread = Math.max(...values) - Math.min(...values)
    matrix.push({ localeName, mode: mode.name, spread, modeResults })
    if (spread > 1) {
      throw new Error(`controls block changed by density: ${JSON.stringify(matrix)}`)
    }
  }
}
fixture.remove()
matrix
```

Expected: all ten locale/mode rows report `spread <= 1`, including the forced combined wrap case.

- [ ] **Step 3: Sample the exact oscillation reproduction for three seconds**

After the first chart has an active canvas/SVG and no loading overlay, execute:

```js
const target = document.querySelector(
  '.canvas-container .wrapper-outer.is-report-chart-target .chart-base-container'
)
if (!(target instanceof HTMLElement)) throw new Error('first dashboard chart not found')

function snapshot() {
  const rootRect = target.getBoundingClientRect()
  const showArea = target.querySelector('.chart-show-area')
  const chart = target.querySelector('.chart-container')
  return {
    rootWidth: Math.round(rootRect.width * 10) / 10,
    rootHeight: Math.round(rootRect.height * 10) / 10,
    density: [...target.classList].find((name) => name.startsWith('insight-density-')),
    layout: showArea instanceof HTMLElement
      ? [...showArea.classList].find((name) => name.startsWith('insight-layout-'))
      : null,
    summary: Boolean(target.querySelector('.chart-insight-header')),
    chartWidth: chart instanceof HTMLElement
      ? Math.round(chart.getBoundingClientRect().width * 10) / 10
      : null,
    loading: Boolean(target.querySelector('.chart-loading-info')),
  }
}

const samples = []
for (let index = 0; index < 31; index += 1) {
  samples.push(snapshot())
  await new Promise((resolve) => setTimeout(resolve, 100))
}
const stableFields = ['density', 'layout', 'summary', 'loading']
for (const field of stableFields) {
  if (new Set(samples.map((sample) => sample[field])).size !== 1) {
    throw new Error(`${field} changed during stability window: ${JSON.stringify(samples)}`)
  }
}
for (const field of ['rootWidth', 'rootHeight', 'chartWidth']) {
  const values = samples.map((sample) => sample[field]).filter(Number.isFinite)
  if (Math.max(...values) - Math.min(...values) > 1) {
    throw new Error(`${field} moved more than 1px: ${JSON.stringify(samples)}`)
  }
}
if (samples.some((sample) => sample.loading)) {
  throw new Error(`loading overlay reappeared: ${JSON.stringify(samples)}`)
}
samples
```

Expected: 31 samples with one density, one layout, one summary state, no loading, and at most `1px` width/height spread. Confirm the browser console has no `ResizeObserver loop` warning.

- [ ] **Step 4: Verify real external resizing remains responsive**

Change the viewport across `680`, `760`, `900`, and `1100` normalized-width boundaries and resize a dashboard card across `250`, `280`, `330`, `360`, `390`, and `430` normalized-height boundaries. At every stop, wait `500ms` and capture two snapshots `300ms` apart.

Expected: layout/density may change once after a real root or toolbar boundary change, then both snapshots match. Top, side and rich-top summaries remain readable with no overlap or clipping.

- [ ] **Step 5: Run final automated verification from a clean worktree**

```powershell
cd frontend
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
npm run build
cd ..
git diff --check
git status --short --branch
```

Expected: every test prints `passed`, build exits `0`, `git diff --check` is empty, and status contains only the intentional task commits/files.

---

## Completion Review

Before reporting completion, invoke `verification-before-completion`, then `requesting-code-review`. The reviewer must inspect the full branch diff from `5bcaa2ed` and specifically check:

- no `.chart-show-area` observation remains in `SQView`;
- root observation uses `border-box` and controls contribution is density-invariant;
- no size callback calls `SQView.scheduleRenderChart()`;
- `previousShow` and its re-entry constant/state are fully removed;
- the exhaustive scan covers multi-metric, grouped, Sankey, Treemap, wide trend, rich top, pie and thresholds;
- browser evidence uses the exact workspace, dashboard, viewport, ready condition, sampling interval and `1px` tolerance.
