# Table Container Size Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 S2 表格始终使用自身挂载容器的实际可用尺寸，避免父容器内边距造成底部和右侧裁切。

**Architecture:** 在 `Table.ts` 中增加统一的挂载容器尺寸读取函数，初始渲染与 `ResizeObserver` 回调都调用该函数。观察目标改为表格自身容器，保留现有 S2 原地 resize 与滚动条配置。

**Tech Stack:** Vue 3、TypeScript、AntV S2、Node 静态回归测试

## Global Constraints

- 不修改 ROI 卡片的布局和 `10px` 内边距。
- 不修改业务数据、SQL、图表字段或语义配置。
- 不执行 Git 提交或推送，除非用户明确要求。

---

### Task 1: 增加表格尺寸回归测试

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`
- Test: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`

**Interfaces:**
- Consumes: `Table` 类的挂载容器与 `ResizeObserver` 初始化代码。
- Produces: 对“监听自身容器并读取 clientWidth/clientHeight”的静态回归约束。

- [ ] **Step 1: 写入失败断言**

```js
assert.match(
  table,
  /resolveTableContainerSize[\s\S]*clientWidth[\s\S]*clientHeight/,
  'S2 表格尺寸必须来自自身挂载容器的实际可用宽高'
)
assert.match(
  table,
  /this\.resizeObserver\.observe\(this\.container\)/,
  'S2 表格必须监听自身挂载容器，而不是带内边距的父容器'
)
assert.doesNotMatch(
  table,
  /this\.resizeObserver\.observe\(this\.container\.parentElement\)/,
  'S2 表格不得继续使用父容器尺寸'
)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `node src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: FAIL，提示缺少 `resolveTableContainerSize` 或仍监听父容器。

### Task 2: 使用自身容器尺寸调整 S2

**Files:**
- Modify: `frontend/src/views/chat/component/charts/Table.ts`
- Test: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`

**Interfaces:**
- Consumes: `this.container: S2MountContainer | null`。
- Produces: `resolveTableContainerSize(container): { width: number; height: number } | null`。

- [ ] **Step 1: 增加统一尺寸读取函数**

```ts
function resolveTableContainerSize(container: S2MountContainer | null) {
  if (!(container instanceof HTMLElement)) return null
  const width = Math.round(container.clientWidth)
  const height = Math.round(container.clientHeight)
  return width > 0 && height > 0 ? { width, height } : null
}
```

- [ ] **Step 2: 监听自身挂载容器**

```ts
this.resizeObserver = new ResizeObserver(() => {
  const size = resolveTableContainerSize(this.container)
  if (!size) return
  const { width, height } = size
  if (width === this.lastResizeWidth && height === this.lastResizeHeight) return
  this.lastResizeWidth = width
  this.lastResizeHeight = height
  this.debounceRender(width, height)
})

if (this.container instanceof HTMLElement) {
  this.resizeObserver.observe(this.container)
}
```

- [ ] **Step 3: 初始渲染复用尺寸函数**

```ts
const containerSize = resolveTableContainerSize(this.container)
const containerWidth = Math.max((containerSize?.width || 600) - TABLE_HORIZONTAL_INSET, 320)
const containerHeight = containerSize?.height || 360
```

- [ ] **Step 4: 运行专项测试**

Run: `node src/views/chat/component/ChartComponent.resize.test.mjs`

Expected: 输出 `ChartComponent resize tests passed`。

### Task 3: 验证构建与页面效果

**Files:**
- Verify: `frontend/src/views/chat/component/charts/Table.ts`
- Verify: `frontend/src/views/dashboard/roi/RoiChartCard.vue`

**Interfaces:**
- Consumes: 本地 Vite 页面和 flam 工作空间 ROI 看板。
- Produces: 画布尺寸不超过 `.chart-container` 的浏览器实测结果。

- [ ] **Step 1: 运行前端构建**

Run: `npm run build`

Expected: `vue-tsc -b` 和 `vite build` 均成功退出。

- [ ] **Step 2: 浏览器实测尺寸**

检查第二个 ROI 表格的 `.chart-container` 和 `canvas`：

```js
const container = document.querySelectorAll('article')[1].querySelector('.chart-container')
const canvas = container.querySelector('canvas')
canvas.getBoundingClientRect().width <= container.clientWidth
  && canvas.getBoundingClientRect().height <= container.clientHeight
```

Expected: `true`，并且滚动到底后最后一行、最右列完整可见。
