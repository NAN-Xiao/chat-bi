# 看板抽屉自适应布局实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有看板抽屉按图表主体的真实可用宽高自适应，消除指标卡对比信息和其他图表内容在小尺寸下被裁切或遮挡的问题。

**Architecture:** 新增无业务依赖的图表尺寸协议，由 `ChartComponent` 测量自身容器并把稳定的 `mini / basic / regular` 布局上下文传给图表实例。`SQView` 改用纵向 Flex 让标题和工具区自然占位，图表主体消费真实剩余空间；Metric 使用明确的信息降级规则，G2 图表使用共享的轴、图例和内边距策略，S2 表格继续在自身容器内原地调整尺寸。

**Tech Stack:** Vue 3、TypeScript 5.7、Less、AntV G2 5、AntV S2 2、Node.js `node:test`/`assert`、Vite、Playwright（Codex Browser）。

## Global Constraints

- 不修改 SQL、指标口径、日期口径、Data Skills、数据源配置或看板持久化数据。
- 不为“活跃用户”、某个数据源、看板 ID、字段名或业务领域写特殊分支。
- 不使用 CSS `transform: scale(...)` 或随视口宽度连续缩放字体。
- 不在字段缺失时自动替换轴、指标、系列或其他配置。
- 图表实例继续挂载到当前组件拥有的 DOM ref，不查询全局图表 id。
- Metric 最多展示两项明确配置的对比字段；对比值无有效分母时继续显示 `-`。
- 表格保持表头与可读字号，只有表格内容区允许滚动。
- Chat、分析助手、商店预览和全屏图表不继承看板专用的重复标题隐藏行为。
- 保留工作区中与本任务无关的现有修改；每次只暂存本任务文件，提交信息使用中文。

---

## File Map

- Create `frontend/src/views/chat/component/chartLayout.ts`: 通用尺寸上下文、密度判定和边界稳定策略。
- Create `frontend/src/views/chat/component/chartLayout.test.mjs`: 直接执行密度纯函数的边界测试。
- Modify `frontend/src/views/chat/component/BaseChart.ts`: 图表实例可选布局上下文接口。
- Modify `frontend/src/views/chat/component/ChartComponent.vue`: 测量实际挂载容器、生成布局上下文并传给实例。
- Modify `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`: 尺寸上下文传播和 table 不重建契约。
- Modify `frontend/src/views/dashboard/components/sq-view/index.vue`: 外层纵向 Flex、真实剩余空间测量、看板表面标记。
- Create `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`: 禁止固定高度扣减并验证布局结构。
- Modify `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`: 将旧固定 `calc(...)` 断言替换为自然布局断言。
- Create `frontend/src/views/chat/component/charts/metricLayout.ts`: Metric 三档布局参数。
- Create `frontend/src/views/chat/component/charts/Metric.responsive.test.mjs`: Metric 信息优先级和小尺寸契约。
- Modify `frontend/src/views/chat/component/charts/Metric.ts`: 消费布局参数，解决重复标题与内容裁切。
- Create `frontend/src/views/chat/component/charts/g2Responsive.ts`: G2 图表共享的紧凑轴、图例、内边距和标签参数。
- Create `frontend/src/views/chat/component/charts/g2Responsive.test.mjs`: 共享 G2 参数和所有图表接线测试。
- Modify `frontend/src/views/chat/component/charts/Line.ts`, `Area.ts`, `Column.ts`, `Bar.ts`, `Scatter.ts`, `Heatmap.ts`: 消费共享笛卡尔坐标布局。
- Modify `frontend/src/views/chat/component/charts/Pie.ts`, `Funnel.ts`, `Sankey.ts`, `Treemap.ts`: 消费共享结构图布局。
- Modify `frontend/src/views/chat/component/charts/Table.ts`: 仅补足极小高度下的表头/内容尺寸保护，不改变数据与交互。

---

### Task 1: 建立共享尺寸协议

**Files:**
- Create: `frontend/src/views/chat/component/chartLayout.ts`
- Create: `frontend/src/views/chat/component/chartLayout.test.mjs`

**Interfaces:**
- Consumes: 无。
- Produces: `ChartDensity`、`ChartSurface`、`ChartLayoutContext`、`resolveChartDensity(width, height, previous?)`、`buildChartLayoutContext(params)`；后续任务不得复制阈值判断。

- [ ] **Step 1: 写密度边界的失败测试**

创建 `chartLayout.test.mjs`，通过 TypeScript `transpileModule` 执行纯函数：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/chartLayout.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveChartDensity, buildChartLayoutContext } = await import(moduleUrl)

assert.equal(resolveChartDensity(213, 79), 'mini')
assert.equal(resolveChartDensity(360, 180), 'basic')
assert.equal(resolveChartDensity(720, 420), 'regular')
assert.equal(resolveChartDensity(263, 123, 'mini'), 'mini')
assert.equal(resolveChartDensity(280, 140, 'mini'), 'basic')
assert.equal(resolveChartDensity(416, 216, 'regular'), 'regular')
assert.deepEqual(
  buildChartLayoutContext({ width: 213, height: 79, surface: 'dashboard', hasOuterTitle: true }),
  { width: 213, height: 79, density: 'mini', surface: 'dashboard', hasOuterTitle: true }
)
console.log('Chart layout tests passed')
```

- [ ] **Step 2: 运行测试并确认正确失败**

Run: `cd frontend; node src/views/chat/component/chartLayout.test.mjs`

Expected: FAIL，错误为找不到 `chartLayout.ts` 或导出函数不存在。

- [ ] **Step 3: 实现最小尺寸协议**

创建 `chartLayout.ts`：

```ts
export type ChartDensity = 'mini' | 'basic' | 'regular'
export type ChartSurface = 'dashboard' | 'chat' | 'fullscreen' | 'preview'

export interface ChartLayoutContext {
  width: number
  height: number
  density: ChartDensity
  surface: ChartSurface
  hasOuterTitle: boolean
}

const MINI_MAX_WIDTH = 260
const MINI_MAX_HEIGHT = 120
const BASIC_MAX_WIDTH = 420
const BASIC_MAX_HEIGHT = 220
const DENSITY_HYSTERESIS = 8

function rawDensity(width: number, height: number): ChartDensity {
  if (width < MINI_MAX_WIDTH || height < MINI_MAX_HEIGHT) return 'mini'
  if (width < BASIC_MAX_WIDTH || height < BASIC_MAX_HEIGHT) return 'basic'
  return 'regular'
}

export function resolveChartDensity(
  width: number,
  height: number,
  previous?: ChartDensity
): ChartDensity {
  const next = rawDensity(width, height)
  if (previous === 'mini' && (width < MINI_MAX_WIDTH + DENSITY_HYSTERESIS || height < MINI_MAX_HEIGHT + DENSITY_HYSTERESIS)) return 'mini'
  if (previous === 'basic' && next === 'mini' && width >= MINI_MAX_WIDTH - DENSITY_HYSTERESIS && height >= MINI_MAX_HEIGHT - DENSITY_HYSTERESIS) return 'basic'
  if (previous === 'basic' && next === 'regular' && (width < BASIC_MAX_WIDTH + DENSITY_HYSTERESIS || height < BASIC_MAX_HEIGHT + DENSITY_HYSTERESIS)) return 'basic'
  if (previous === 'regular' && next === 'basic' && width >= BASIC_MAX_WIDTH - DENSITY_HYSTERESIS && height >= BASIC_MAX_HEIGHT - DENSITY_HYSTERESIS) return 'regular'
  return next
}

export function buildChartLayoutContext(params: {
  width: number
  height: number
  surface?: ChartSurface
  hasOuterTitle?: boolean
  previousDensity?: ChartDensity
}): ChartLayoutContext {
  const width = Math.max(0, Math.round(params.width))
  const height = Math.max(0, Math.round(params.height))
  return {
    width,
    height,
    density: resolveChartDensity(width, height, params.previousDensity),
    surface: params.surface || 'preview',
    hasOuterTitle: params.hasOuterTitle === true,
  }
}
```

- [ ] **Step 4: 运行测试与格式检查**

Run: `cd frontend; node src/views/chat/component/chartLayout.test.mjs`

Expected: `Chart layout tests passed`。

Run: `git diff --check -- frontend/src/views/chat/component/chartLayout.ts frontend/src/views/chat/component/chartLayout.test.mjs`

Expected: exit 0。

- [ ] **Step 5: 提交尺寸协议**

```powershell
git add -- frontend/src/views/chat/component/chartLayout.ts frontend/src/views/chat/component/chartLayout.test.mjs
git commit -m "新增：统一图表尺寸密度协议"
```

---

### Task 2: 将真实容器尺寸传入图表实例

**Files:**
- Modify: `frontend/src/views/chat/component/BaseChart.ts`
- Modify: `frontend/src/views/chat/component/ChartComponent.vue`
- Modify: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`

**Interfaces:**
- Consumes: Task 1 的 `ChartLayoutContext`、`ChartSurface`、`buildChartLayoutContext`。
- Produces: `BaseChart.layoutContext?: ChartLayoutContext`；`ChartComponent` 新 props `surface?: ChartSurface`、`hasOuterTitle?: boolean`。

- [ ] **Step 1: 扩展现有 resize 契约测试并确认失败**

在 `ChartComponent.resize.test.mjs` 增加：

```js
assert.match(component, /surface\?:\s*ChartSurface/, 'ChartComponent 必须声明调用表面')
assert.match(component, /hasOuterTitle\?:\s*boolean/, '调用方必须能声明外层已有标题')
assert.match(component, /buildChartLayoutContext\(/, '组件必须从自身容器尺寸构建布局上下文')
assert.match(component, /chartInstance\.layoutContext\s*=\s*currentLayoutContext\.value/, '实例初始化前必须收到布局上下文')
assert.match(component, /previousDensity:/, '密度切换必须使用前一档做边界稳定')
assert.match(component, /params\.type\s*!==\s*['"]table['"]/, 'table 仍由自身 ResizeObserver 原地调整')
```

Run: `cd frontend; node src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: FAIL，首个缺失项为 `ChartSurface` prop 或 `buildChartLayoutContext`。

- [ ] **Step 2: 扩展 BaseChart 接口**

在 `BaseChart.ts` 导入类型并增加实例属性：

```ts
import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export abstract class BaseChart {
  // 保留现有字段
  layoutContext?: ChartLayoutContext
}
```

- [ ] **Step 3: 在 ChartComponent 中生成稳定布局上下文**

增加 props、容器尺寸和计算属性：

```ts
import {
  buildChartLayoutContext,
  type ChartDensity,
  type ChartSurface,
} from '@/views/chat/component/chartLayout.ts'

surface?: ChartSurface
hasOuterTitle?: boolean

const chartSize = ref({ width: 0, height: 0 })
const previousDensity = ref<ChartDensity>()
const currentLayoutContext = computed(() => {
  const context = buildChartLayoutContext({
    ...chartSize.value,
    surface: params.surface,
    hasOuterTitle: params.hasOuterTitle,
    previousDensity: previousDensity.value,
  })
  previousDensity.value = context.density
  return context
})

function measureChartContainer() {
  const element = chartContainerRef.value
  if (!element) return false
  const width = Math.round(element.clientWidth)
  const height = Math.round(element.clientHeight)
  if (width <= 0 || height <= 0) return false
  if (width !== chartSize.value.width || height !== chartSize.value.height) {
    chartSize.value = { width, height }
  }
  return true
}
```

在 `renderChart()` 中先测量，再赋值后初始化：

```ts
if (!measureChartContainer()) return
chartInstance = getChartInstance(params.type, container)
if (chartInstance) {
  chartInstance.layoutContext = currentLayoutContext.value
  chartInstance.showLabel = params.showLabel
  // 保留其余属性和 init/render 流程
}
```

ResizeObserver 中先调用 `measureChartContainer()`；非 table 才 `scheduleRenderChart(80)`，table 不销毁重建。

- [ ] **Step 4: 运行 resize 契约与类型检查**

Run: `cd frontend; node src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: `ChartComponent resize tests passed`。

Run: `cd frontend; npx vue-tsc -b --pretty false`

Expected: exit 0，无 TypeScript 错误。

- [ ] **Step 5: 提交布局上下文传播**

```powershell
git add -- frontend/src/views/chat/component/BaseChart.ts frontend/src/views/chat/component/ChartComponent.vue frontend/src/views/chat/component/ChartComponent.resize.test.mjs
git commit -m "重构：向图表传递真实容器尺寸"
```

---

### Task 3: 用自然布局替换 SQView 固定高度扣减

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Create: `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`

**Interfaces:**
- Consumes: Task 2 的 `ChartComponent.surface` 和 `ChartComponent.hasOuterTitle`。
- Produces: `SQView` 的标题区、工具区和图表区自然占位；`frameSize` 改为图表展示区真实尺寸，供洞察摘要继续判定密度。

- [ ] **Step 1: 写自然布局失败测试**

创建 `index.responsive-layout.test.mjs`：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const style = source.slice(source.indexOf('<style scoped'))

assert.match(source, /ref="chartShowAreaRef"[^>]*class="chart-show-area"/)
assert.match(source, /surface="dashboard"/)
assert.match(source, /:has-outer-title="true"/)
assert.match(style, /\.chart-base-container\s*\{[^}]*display:\s*flex[^}]*flex-direction:\s*column/s)
assert.match(style, /\.header-bar\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(style, /\.dashboard-filter-controls\s*\{[^}]*flex:\s*0\s+0\s+auto/s)
assert.match(style, /\.chart-show-area\s*\{[^}]*flex:\s*1\s+1\s+auto[^}]*height:\s*auto/s)
assert.doesNotMatch(style, /\.chart-show-area\s*\{[^}]*height:\s*calc\(/s)
assert.doesNotMatch(style, /:has\([^)]*(?:pivot-toolbar|date-expression-toolbar)[^)]*\)[^{]*\.chart-show-area\s*\{[^}]*height:/s)
assert.doesNotMatch(style, /\.chart-loading-info\s*\{[^}]*min-height:\s*140px/s)
console.log('SQView responsive layout tests passed')
```

- [ ] **Step 2: 更新旧日期控件断言并确认失败**

在 `index.date-filter.test.mjs` 删除对 `height: calc(100% - 82px)` 的正向断言，替换为：

```js
assert.match(source, /\.dashboard-filter-controls--combined[\s\S]*?flex-wrap:\s*wrap/)
assert.doesNotMatch(source, /\.chart-show-area[\s\S]{0,120}?height:\s*calc\(/)
```

Run: `cd frontend; node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`

Expected: FAIL，缺少 `chartShowAreaRef` 或根容器纵向 Flex。

Run: `cd frontend; node src/views/dashboard/components/sq-view/index.date-filter.test.mjs`

Expected: FAIL，因为当前仍存在固定 `calc(...)` 规则。

- [ ] **Step 3: 改造 SQView 结构和测量点**

在脚本区新增 `chartShowAreaRef`，`measureFrame()` 改读图表展示区：

```ts
const chartShowAreaRef = ref<HTMLElement | null>(null)

function measureFrame() {
  const el = chartShowAreaRef.value
  if (!el) return
  const nextSize = {
    width: Math.round(el.clientWidth),
    height: Math.round(el.clientHeight),
  }
  if (nextSize.width !== frameSize.value.width || nextSize.height !== frameSize.value.height) {
    frameSize.value = nextSize
  }
}
```

Mounted 时同时观察根容器和 `chartShowAreaRef`，模板与 `ChartComponent` 改为：

```vue
<div ref="chartShowAreaRef" class="chart-show-area" :class="`insight-layout-${effectiveInsightLayout}`">
  <!-- 现有状态、摘要和 chart-content-row -->
  <ChartComponent
    surface="dashboard"
    :has-outer-title="true"
    <!-- 保留现有 props -->
  />
</div>
```

- [ ] **Step 4: 替换固定高度 CSS**

根布局和子区使用：

```less
.chart-base-container {
  display: flex;
  flex-direction: column;
  min-height: 0;

  .header-bar { flex: 0 0 auto; }
  .dashboard-filter-controls { flex: 0 0 auto; }
}

.dashboard-filter-controls--combined {
  display: flex;
  flex-wrap: wrap;
}

.chart-show-area {
  width: 100%;
  height: auto;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
```

删除所有针对 `.chart-show-area` 的固定 `calc(...)` 组合规则；`.chart-loading-info` 去掉 `min-height: 140px`，让加载/空态使用真实剩余空间。

- [ ] **Step 5: 运行 SQView 相关测试**

Run:

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/components/sq-view/index.state-machine.test.mjs
node src/views/dashboard/components/sq-view/index.empty-state.test.mjs
```

Expected: 四条命令均 exit 0，各自输出通过信息。

- [ ] **Step 6: 提交自然布局改造**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
git commit -m "修复：看板抽屉使用真实剩余高度"
```

---

### Task 4: 让指标卡在三档尺寸下完整显示

**Files:**
- Create: `frontend/src/views/chat/component/charts/metricLayout.ts`
- Create: `frontend/src/views/chat/component/charts/Metric.responsive.test.mjs`
- Modify: `frontend/src/views/chat/component/charts/Metric.ts`

**Interfaces:**
- Consumes: Task 1/2 的 `ChartLayoutContext` 和 `BaseChart.layoutContext`。
- Produces: `resolveMetricLayout(context, compareCount)`，Metric DOM 上的 `.metric-wrapper`、`.metric-card`、`.metric-date`、`.metric-value`、`.metric-comparisons` 稳定类名。

- [ ] **Step 1: 写 Metric 布局参数与接线失败测试**

创建 `Metric.responsive.test.mjs`：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const layoutSource = readFileSync('src/views/chat/component/charts/metricLayout.ts', 'utf8')
const compiled = ts.transpileModule(layoutSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveMetricLayout } = await import(moduleUrl)

const mini = resolveMetricLayout({ width: 213, height: 79, density: 'mini', surface: 'dashboard', hasOuterTitle: true }, 2)
assert.equal(mini.showInnerLabel, false)
assert.equal(mini.showAccent, false)
assert.equal(mini.comparisonColumns, 2)
assert.ok(mini.requiredHeight <= 79)

const basic = resolveMetricLayout({ width: 360, height: 180, density: 'basic', surface: 'dashboard', hasOuterTitle: true }, 2)
assert.equal(basic.showInnerLabel, true)
assert.equal(basic.showAccent, true)

const chatMini = resolveMetricLayout({ width: 213, height: 79, density: 'mini', surface: 'chat', hasOuterTitle: false }, 2)
assert.equal(chatMini.showInnerLabel, true)

const metricSource = readFileSync('src/views/chat/component/charts/Metric.ts', 'utf8')
assert.match(metricSource, /resolveMetricLayout\(this\.layoutContext/)
assert.match(metricSource, /className = ['"]metric-comparisons['"]/)
assert.match(metricSource, /gridTemplateColumns/)
assert.match(metricSource, /if \(layout\.showInnerLabel/)
assert.match(metricSource, /if \(layout\.showAccent/)
console.log('Metric responsive tests passed')
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/chat/component/charts/Metric.responsive.test.mjs`

Expected: FAIL，找不到 `metricLayout.ts`。

- [ ] **Step 3: 实现 Metric 布局纯函数**

创建 `metricLayout.ts`，显式返回 mini 所需高度不超过 79px：

```ts
import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export interface MetricLayout {
  showInnerLabel: boolean
  showAccent: boolean
  wrapperPadding: string
  cardPadding: string
  valueFontSize: number
  valueLineHeight: number
  comparisonColumns: number
  comparisonGap: string
  requiredHeight: number
}

export function resolveMetricLayout(context: ChartLayoutContext, compareCount: number): MetricLayout {
  if (context.density === 'mini') {
    return {
      showInnerLabel: !(context.surface === 'dashboard' && context.hasOuterTitle),
      showAccent: false,
      wrapperPadding: '0 4px',
      cardPadding: '0 6px',
      valueFontSize: 26,
      valueLineHeight: 30,
      comparisonColumns: compareCount > 1 && context.width >= 180 ? 2 : 1,
      comparisonGap: '2px 10px',
      requiredHeight: context.surface === 'dashboard' && context.hasOuterTitle ? 68 : 79,
    }
  }
  if (context.density === 'basic') {
    return {
      showInnerLabel: true,
      showAccent: true,
      wrapperPadding: '2px 6px 4px',
      cardPadding: '6px 10px 8px',
      valueFontSize: 28,
      valueLineHeight: 34,
      comparisonColumns: compareCount > 1 ? 2 : 1,
      comparisonGap: '4px 12px',
      requiredHeight: 132,
    }
  }
  return {
    showInnerLabel: true,
    showAccent: true,
    wrapperPadding: '6px 10px 10px',
    cardPadding: '12px 18px 14px',
    valueFontSize: 36,
    valueLineHeight: 44,
    comparisonColumns: compareCount > 1 ? 2 : 1,
    comparisonGap: '6px 14px',
    requiredHeight: 174,
  }
}
```

- [ ] **Step 4: 改造 Metric DOM 布局**

在 `Metric.render()` 中使用 `this.layoutContext`；若缺少上下文，以当前容器尺寸构造 preview 上下文。给关键节点稳定类名，mini 模式只在看板且外层有标题时隐藏内部重复标签。日期节点不再依赖指标标签是否显示：

```ts
const context = this.layoutContext || buildChartLayoutContext({
  width: this.container.clientWidth,
  height: this.container.clientHeight,
  surface: 'preview',
})
const layout = resolveMetricLayout(context, compareAxes.length)

wrapper.className = 'metric-wrapper'
card.className = 'metric-card'
date.className = 'metric-date'
value.className = 'metric-value'
compareRow.className = 'metric-comparisons'
compareRow.style.display = 'grid'
compareRow.style.gridTemplateColumns = `repeat(${layout.comparisonColumns}, minmax(0, 1fr))`

if (layout.showInnerLabel && axisLabel) card.appendChild(label)
if (dateAxis) card.appendChild(date)
card.appendChild(value)
if (compareAxes.length > 0) card.appendChild(compareRow)
if (layout.showAccent) card.appendChild(accent)
```

保留现有 `isCompareAxis`、正负颜色和百分比格式逻辑；最多两项对比的 `.slice(0, 2)` 不变。

- [ ] **Step 5: 运行 Metric 测试和类型检查**

Run: `cd frontend; node src/views/chat/component/charts/Metric.responsive.test.mjs`

Expected: `Metric responsive tests passed`。

Run: `cd frontend; npx vue-tsc -b --pretty false`

Expected: exit 0。

- [ ] **Step 6: 提交指标卡适配**

```powershell
git add -- frontend/src/views/chat/component/charts/metricLayout.ts frontend/src/views/chat/component/charts/Metric.responsive.test.mjs frontend/src/views/chat/component/charts/Metric.ts
git commit -m "修复：指标卡按可用空间展示对比信息"
```

---

### Task 5: 让 G2 图表共享紧凑轴、图例和标签策略

**Files:**
- Create: `frontend/src/views/chat/component/charts/g2Responsive.ts`
- Create: `frontend/src/views/chat/component/charts/g2Responsive.test.mjs`
- Modify: `frontend/src/views/chat/component/charts/Line.ts`
- Modify: `frontend/src/views/chat/component/charts/Area.ts`
- Modify: `frontend/src/views/chat/component/charts/Column.ts`
- Modify: `frontend/src/views/chat/component/charts/Bar.ts`
- Modify: `frontend/src/views/chat/component/charts/Scatter.ts`
- Modify: `frontend/src/views/chat/component/charts/Heatmap.ts`
- Modify: `frontend/src/views/chat/component/charts/Pie.ts`
- Modify: `frontend/src/views/chat/component/charts/Funnel.ts`
- Modify: `frontend/src/views/chat/component/charts/Sankey.ts`
- Modify: `frontend/src/views/chat/component/charts/Treemap.ts`

**Interfaces:**
- Consumes: `BaseChart.layoutContext`。
- Produces: `resolveG2ResponsiveStyle(context, family)`；所有 G2 图表使用同一密度参数，不包含业务字段判断。

- [ ] **Step 1: 写共享参数与全图表接线失败测试**

创建 `g2Responsive.test.mjs`，执行纯函数并检查所有目标文件：

```js
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync('src/views/chat/component/charts/g2Responsive.ts', 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`
const { resolveG2ResponsiveStyle } = await import(moduleUrl)

const miniCartesian = resolveG2ResponsiveStyle({ width: 280, height: 110, density: 'mini', surface: 'dashboard', hasOuterTitle: true }, 'cartesian')
assert.equal(miniCartesian.axisLabelFontSize, 9)
assert.equal(miniCartesian.showPointLabels, false)
assert.deepEqual(miniCartesian.padding, [4, 6, 18, 28])

const miniStructure = resolveG2ResponsiveStyle({ width: 240, height: 110, density: 'mini', surface: 'dashboard', hasOuterTitle: true }, 'structure')
assert.equal(miniStructure.legendPosition, 'bottom')
assert.equal(miniStructure.structureLabelFontSize, 9)

const files = ['Line.ts', 'Area.ts', 'Column.ts', 'Bar.ts', 'Scatter.ts', 'Heatmap.ts', 'Pie.ts', 'Funnel.ts', 'Sankey.ts', 'Treemap.ts']
for (const file of files) {
  const chart = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(chart, /resolveG2ResponsiveStyle\(this\.layoutContext/, `${file} 必须消费共享尺寸策略`)
}
console.log('G2 responsive tests passed')
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd frontend; node src/views/chat/component/charts/g2Responsive.test.mjs`

Expected: FAIL，找不到 `g2Responsive.ts`。

- [ ] **Step 3: 实现共享 G2 参数**

创建 `g2Responsive.ts`：

```ts
import type { ChartLayoutContext } from '@/views/chat/component/chartLayout.ts'

export type G2ChartFamily = 'cartesian' | 'structure'

export function resolveG2ResponsiveStyle(
  context: ChartLayoutContext | undefined,
  family: G2ChartFamily
) {
  const density = context?.density || 'regular'
  if (density === 'mini') {
    return {
      padding: family === 'cartesian' ? [4, 6, 18, 28] : [4, 6, 16, 6],
      axisLabelFontSize: 9,
      structureLabelFontSize: 9,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 10,
      showPointLabels: false,
      outerRadius: 0.7,
    }
  }
  if (density === 'basic') {
    return {
      padding: family === 'cartesian' ? [8, 10, 22, 34] : [6, 8, 20, 8],
      axisLabelFontSize: 10,
      structureLabelFontSize: 10,
      legendPosition: 'bottom' as const,
      legendItemFontSize: 11,
      showPointLabels: false,
      outerRadius: 0.76,
    }
  }
  return {
    padding: 'auto' as const,
    axisLabelFontSize: 11,
    structureLabelFontSize: 11,
    legendPosition: 'bottom' as const,
    legendItemFontSize: 12,
    showPointLabels: true,
    outerRadius: 0.8,
  }
}
```

- [ ] **Step 4: 接入笛卡尔与热力图图表**

在 `Line/Area/Column/Bar/Scatter/Heatmap` 的 `init()` 中创建：

```ts
const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'cartesian')
```

在 G2 options 中统一设置：

```ts
padding: responsive.padding,
axis: {
  x: {
    // 保留原有 formatter 和 auto hide
    labelFontSize: responsive.axisLabelFontSize,
  },
  y: {
    // 保留原有 formatter、隐藏值轴等行为
    labelFontSize: responsive.axisLabelFontSize,
  },
},
```

已有 `showLabel` 只有在 `responsive.showPointLabels` 为 true 时才生成 labels；tooltip、encode、scale、forecast 和字段选择保持不变。

- [ ] **Step 5: 接入结构图表**

在 `Pie/Funnel/Sankey/Treemap` 中使用：

```ts
const responsive = resolveG2ResponsiveStyle(this.layoutContext, 'structure')
```

应用 `padding`、`structureLabelFontSize` 和紧凑图例。Pie 使用：

```ts
coordinate: { type: 'theta', outerRadius: responsive.outerRadius },
legend: {
  color: {
    position: responsive.legendPosition,
    itemLabelFontSize: responsive.legendItemFontSize,
    layout: { justifyContent: 'center' },
  },
},
```

Funnel 继续 `legend: false`，小尺寸只收紧 padding 并在 `responsive.showPointLabels` 为 false 时隐藏内部 labels；Sankey/Treemap 只调整标签字号和 padding，不改变节点、边、层级或度量字段。

- [ ] **Step 6: 运行共享图表测试**

Run:

```powershell
cd frontend
node src/views/chat/component/charts/g2Responsive.test.mjs
node src/views/chat/component/charts/axis-date-label.test.mjs
npx vue-tsc -b --pretty false
```

Expected: 两个测试输出通过，类型检查 exit 0。

- [ ] **Step 7: 提交 G2 自适应策略**

```powershell
git add -- frontend/src/views/chat/component/charts/g2Responsive.ts frontend/src/views/chat/component/charts/g2Responsive.test.mjs frontend/src/views/chat/component/charts/Line.ts frontend/src/views/chat/component/charts/Area.ts frontend/src/views/chat/component/charts/Column.ts frontend/src/views/chat/component/charts/Bar.ts frontend/src/views/chat/component/charts/Scatter.ts frontend/src/views/chat/component/charts/Heatmap.ts frontend/src/views/chat/component/charts/Pie.ts frontend/src/views/chat/component/charts/Funnel.ts frontend/src/views/chat/component/charts/Sankey.ts frontend/src/views/chat/component/charts/Treemap.ts
git commit -m "优化：图表按抽屉尺寸收紧轴与图例"
```

---

### Task 6: 固化表格小尺寸行为并完成全链路验证

**Files:**
- Modify: `frontend/src/views/chat/component/charts/Table.ts`
- Modify: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`
- Verify: `frontend/src/views/dashboard/components/sq-view/index.vue`
- Verify: all files changed in Tasks 1-5

**Interfaces:**
- Consumes: SQView 真实剩余高度、Table 自身 ResizeObserver。
- Produces: 极小高度仍保持表头和至少一行内容的 S2 viewport；最终视觉与几何验证证据。

- [ ] **Step 1: 增加表格极小高度失败断言**

在 `ChartComponent.resize.test.mjs` 增加：

```js
assert.match(
  table,
  /function resolveTableViewportHeight\([\s\S]*Math\.max\(containerHeight, TABLE_HEADER_CELL_HEIGHT\)/,
  '极小高度下 S2 viewport 至少保住表头，内容区由自身滚动处理'
)
assert.doesNotMatch(
  dashboardView,
  /\.chart-loading-info\s*\{[^}]*min-height:\s*140px/s,
  '加载态不得撑破小尺寸抽屉'
)
```

Run: `cd frontend; node src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: FAIL，`resolveTableViewportHeight` 尚未对极小高度显式夹紧表头高度。

- [ ] **Step 2: 最小调整表格 viewport**

将 `resolveTableViewportHeight` 的极小高度分支改为：

```ts
function resolveTableViewportHeight(containerHeight: number) {
  const safeHeight = Math.max(containerHeight, TABLE_HEADER_CELL_HEIGHT)
  const minimumTableHeight = TABLE_HEADER_CELL_HEIGHT + TABLE_DATA_CELL_HEIGHT
  if (safeHeight <= minimumTableHeight) return safeHeight
  const availableDataHeight = safeHeight - TABLE_HEADER_CELL_HEIGHT
  const completeDataRows = Math.max(1, Math.floor(availableDataHeight / TABLE_DATA_CELL_HEIGHT))
  return TABLE_HEADER_CELL_HEIGHT + completeDataRows * TABLE_DATA_CELL_HEIGHT
}
```

不改 TableSheet 数据、排序、筛选、列宽和 ResizeObserver 原地 `changeSheetSize` 流程。

- [ ] **Step 3: 运行完整前端测试与构建**

Run:

```powershell
cd frontend
node src/views/chat/component/chartLayout.test.mjs
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/chat/component/charts/Metric.responsive.test.mjs
node src/views/chat/component/charts/g2Responsive.test.mjs
node src/views/chat/component/charts/axis-date-label.test.mjs
node src/views/chat/component/Table.null-display.test.mjs
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/components/sq-view/index.state-machine.test.mjs
node src/views/dashboard/components/sq-view/index.empty-state.test.mjs
npm run build
```

Expected: 所有 Node 测试通过，`vue-tsc` 和 Vite build exit 0。

- [ ] **Step 4: 使用本地服务做桌面视觉验证**

确认 `http://127.0.0.1:5173/` 可访问；若前端未运行，按仓库 runbook 从 `frontend` 启动 `npm run dev`。使用 Codex Browser 打开核心看板和用户截图对应看板，检查以下几何条件：

```js
const cards = Array.from(document.querySelectorAll('.chart-base-container'))
const metricCards = cards.filter((card) => card.querySelector('.metric-wrapper'))
metricCards.map((card) => {
  const chart = card.querySelector('.chart-container')
  const critical = Array.from(chart.querySelectorAll('.metric-date, .metric-value, .metric-comparisons'))
  const chartRect = chart.getBoundingClientRect()
  return {
    title: card.querySelector('.title')?.textContent?.trim(),
    fits: critical.every((node) => {
      const rect = node.getBoundingClientRect()
      return rect.top >= chartRect.top && rect.bottom <= chartRect.bottom
    }),
    clientHeight: chart.clientHeight,
    scrollHeight: chart.scrollHeight,
  }
})
```

Expected: 含“日环比/周同比”的指标卡 `fits: true` 且 `scrollHeight <= clientHeight`；其他指标卡不重复显示内部标题。折线、柱状、饼图、漏斗和表格无文本覆盖，表格只在内容区滚动。

- [ ] **Step 5: 验证窄宽与全屏**

用 Browser viewport 能力分别检查 `390x844` 和 `1440x900`；移动宽度下卡片单列或双列时对比项受控换行，文本不越界。打开任一图表全屏预览，确认其使用完整布局且关闭后原卡片仍按当前尺寸渲染。

Expected: 两个 viewport 均无重叠；全屏图表不隐藏自身必要标题/标签，关闭后无空白 Canvas。

- [ ] **Step 6: 最终差异和工作区边界检查**

Run:

```powershell
git diff --check
git diff --stat HEAD~5..HEAD
git status --short
```

Expected: `git diff --check` exit 0；差异只覆盖本计划文件和实现文件；用户原有未提交修改仍保留且未被暂存。

- [ ] **Step 7: 提交表格保护与最终验证调整**

```powershell
git add -- frontend/src/views/chat/component/charts/Table.ts frontend/src/views/chat/component/ChartComponent.resize.test.mjs
git commit -m "修复：小尺寸表格保留可读表头"
```

提交后重新运行 Task 6 Step 3 的完整命令，任何失败都必须修复并重新验证后才能宣告完成。
