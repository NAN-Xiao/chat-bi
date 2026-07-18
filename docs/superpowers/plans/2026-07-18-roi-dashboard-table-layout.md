# ROI 看板表格铺满布局 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ROI 看板表格始终使用卡片全部可用宽度，并优化标题、日期与操作区排版，同时保留固定高度和防闪烁行为。

**Architecture:** 保留现有 ROI 网格、卡片和 ChartComponent 数据流，仅在 S2 Table 实例的初始化与 ResizeObserver 原地更新路径中统一计算列宽。卡片层只调整 CSS 布局，不新增状态、接口或业务字段规则；所有回归通过现有源码约束测试和前端构建验证。

**Tech Stack:** Vue 3、TypeScript、Less、Element Plus、AntV S2 2.7.2、Node.js 断言测试、vue-tsc、Vite

## Global Constraints

- 保留 `frontend/src/views/dashboard/roi/RoiChartGrid.vue` 中 `320px` 固定网格行高，不改为内容驱动的自适应高度。
- 表格尺寸变化必须复用现有 S2 实例，通过 `setOptions`、`changeSheetSize` 和 `render(false)` 原地更新，不销毁并重建图表。
- 字段较少时分配剩余宽度；字段较多时保持最小可读列宽并由 S2 提供横向滚动。
- 不隐藏、替换或猜测 SQL 返回字段，不增加具体数据源、业务字段或行业场景硬编码。
- 不改变日期范围、重新执行 SQL、排序、宽度调整、编辑、删除及权限判断流程。
- 不提交或删除 `.superpowers/brainstorm/`。

---

## File Structure

- `frontend/src/views/chat/component/charts/Table.ts`：负责根据当前容器宽度和可见字段数计算统一列宽，并在 S2 resize 时原地更新样式与画布尺寸。
- `frontend/src/views/chat/component/ChartComponent.resize.test.mjs`：约束 Table resize 必须重算列宽、调用 `setOptions`，并继续避免重复 render 和实例重建。
- `frontend/src/views/dashboard/roi/RoiChartCard.vue`：负责卡片单行标题栏、日期选择器、操作区间距以及内容区满宽布局。
- `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs`：约束卡片布局与固定高度规则，防止后续样式回退。

---

### Task 1: S2 表格尺寸变化时重算列宽

**Files:**
- Modify: `frontend/src/views/chat/component/ChartComponent.resize.test.mjs:8`
- Modify: `frontend/src/views/chat/component/charts/Table.ts:79`

**Interfaces:**
- Consumes: `this.axis` 中未隐藏字段数量、ResizeObserver 提供的容器 `width` / `height`。
- Produces: `resolveTableColumnWidth(containerWidth: number, visibleColumnCount: number): number`；Table resize 路径使用同一列宽规则更新 S2 options。

- [ ] **Step 1: 写入失败的 resize 回归断言**

在 `frontend/src/views/chat/component/ChartComponent.resize.test.mjs` 的 Table 断言后加入：

```js
assert.match(
  table,
  /function resolveTableColumnWidth\(\s*containerWidth:\s*number,\s*visibleColumnCount:\s*number\s*\)[\s\S]*Math\.max\([\s\S]*TABLE_MIN_COLUMN_WIDTH,[\s\S]*Math\.floor\(containerWidth \/ Math\.max\(visibleColumnCount, 1\)\)/,
  'S2 表格必须按当前容器宽度和可见字段数计算最小 92px 的列宽'
)
assert.match(
  table,
  /debounce\(\s*async\s*\(width\?: number, height\?: number\)[\s\S]*this\.table\.setOptions\([\s\S]*colCell:[\s\S]*width: columnWidth[\s\S]*dataCell:[\s\S]*width: columnWidth[\s\S]*changeSheetSize\(contentWidth, height\)[\s\S]*render\(false\)/,
  '容器变宽后必须原地更新列宽和画布尺寸'
)
```

- [ ] **Step 2: 运行测试并确认失败**

运行：

```powershell
cd frontend
node src/views/chat/component/ChartComponent.resize.test.mjs
```

预期：退出码非 `0`，失败信息包含“S2 表格必须按当前容器宽度和可见字段数计算”。

- [ ] **Step 3: 提取统一列宽计算函数**

在 `frontend/src/views/chat/component/charts/Table.ts` 的 `Table` 类之前加入：

```ts
const TABLE_MIN_COLUMN_WIDTH = 92
const TABLE_HORIZONTAL_INSET = 8

function resolveTableColumnWidth(containerWidth: number, visibleColumnCount: number) {
  return Math.max(
    TABLE_MIN_COLUMN_WIDTH,
    Math.floor(containerWidth / Math.max(visibleColumnCount, 1))
  )
}
```

初始化容器宽度继续扣除 `TABLE_HORIZONTAL_INSET`，并用该函数替换当前内联的 `Math.max(92, ...)`：

```ts
const containerWidth = Math.max(
  (containerElement?.clientWidth || 600) - TABLE_HORIZONTAL_INSET,
  320
)
const containerHeight = containerElement?.clientHeight || 360
const columnWidth = resolveTableColumnWidth(containerWidth, visibleAxis.length)
```

- [ ] **Step 4: 在 ResizeObserver 路径原地更新列宽**

把 `debounceRender` 更新为在当前 S2 实例上合并尺寸样式，不重新创建 Table：

```ts
this.debounceRender = debounce(async (width?: number, height?: number) => {
  if (this.table && width && height) {
    const visibleColumnCount = this.axis?.filter((axis) => !axis.hidden).length ?? 0
    const contentWidth = Math.max(width - TABLE_HORIZONTAL_INSET, 320)
    const columnWidth = resolveTableColumnWidth(contentWidth, visibleColumnCount)

    this.table.setOptions({
      width: contentWidth,
      height,
      style: {
        layoutWidthType: 'adaptive',
        colCell: {
          height: 32,
          width: columnWidth,
        },
        dataCell: {
          height: 30,
          width: columnWidth,
        },
      },
    })
    this.table.changeSheetSize(contentWidth, height)
    await this.table.render(false)
  }
}, 200)
```

保留 `lastResizeWidth` / `lastResizeHeight` 的相同尺寸短路逻辑。少字段时 `columnWidth` 填满内容宽度；多字段时每列至少 `92px`，S2 总列宽超过画布后继续横向滚动。

- [ ] **Step 5: 运行 resize 测试并确认通过**

运行：

```powershell
cd frontend
node src/views/chat/component/ChartComponent.resize.test.mjs
```

预期：输出 `ChartComponent resize tests passed`，退出码 `0`。

- [ ] **Step 6: 提交表格宽度修复**

```powershell
git add frontend/src/views/chat/component/charts/Table.ts frontend/src/views/chat/component/ChartComponent.resize.test.mjs
git commit -m "修复：表格随容器宽度铺满显示"
```

---

### Task 2: 优化 ROI 卡片标题栏排版

**Files:**
- Modify: `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs:17`
- Modify: `frontend/src/views/dashboard/roi/RoiChartCard.vue:202`

**Interfaces:**
- Consumes: 现有 `chart.title`、`dateRange`、`refreshing` 和操作事件。
- Produces: 单行、无覆盖、间距统一的 `.roi-chart-card__header`；不改变任何 Vue props、emit 或业务逻辑。

- [ ] **Step 1: 写入失败的卡片布局断言**

在 `frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs` 的现有卡片 CSS 断言附近加入：

```js
assert.match(
  card,
  /\.roi-chart-card__header\s*\{[\s\S]*?gap:\s*8px[\s\S]*?flex-wrap:\s*nowrap/,
  '卡片标题栏必须保持单行并统一分区间距'
)
assert.match(
  card,
  /\.roi-chart-card__date-range\s*\{[\s\S]*?max-width:\s*250px[\s\S]*?padding:\s*0/,
  '日期选择器必须限制最大宽度并取消额外横向 padding'
)
assert.match(
  card,
  /\.roi-chart-card__actions\s*\{[\s\S]*?gap:\s*2px/,
  '卡片操作按钮必须使用统一间距'
)
assert.match(
  card,
  /\.roi-chart-card__actions[\s\S]*?:deep\(\.ed-button \+ \.ed-button\)[\s\S]*?margin-left:\s*0/,
  'Element Plus 默认相邻按钮外边距不得破坏操作区间距'
)
```

- [ ] **Step 2: 运行测试并确认失败**

运行：

```powershell
cd frontend
node src/views/dashboard/roi/RoiChartGrid.test.mjs
```

预期：退出码非 `0`，失败信息包含“卡片标题栏必须保持单行”。

- [ ] **Step 3: 调整标题栏、日期和操作区样式**

在 `frontend/src/views/dashboard/roi/RoiChartCard.vue` 中保留现有 DOM 结构，仅更新样式：

```less
.roi-chart-card__header {
  display: flex;
  min-height: 48px;
  padding: 0 12px 0 16px;
  align-items: center;
  border-bottom: 1px solid var(--ed-border-color-extra-light);
  flex-wrap: nowrap;
  gap: 8px;
}

.roi-chart-card__title {
  min-width: 0;
  overflow: hidden;
  color: var(--ed-text-color-primary);
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1 1 auto;
}

.roi-chart-card__date-range {
  display: flex;
  min-width: 0;
  max-width: 250px;
  flex: 0 1 250px;
  padding: 0;

  span,
  :deep(.ed-date-editor) {
    width: 100%;
  }
}

.roi-chart-card__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;

  :deep(.ed-button + .ed-button) {
    margin-left: 0;
  }
}
```

保留 `.roi-chart-card__body` 的 `width: 100%`、`flex: 1 1 auto`、`overflow: hidden` 和图表容器 `width/height: 100%`，不调整固定卡片高度。

- [ ] **Step 4: 运行 ROI 网格测试并确认通过**

运行：

```powershell
cd frontend
node src/views/dashboard/roi/RoiChartGrid.test.mjs
```

预期：测试完整执行并以退出码 `0` 结束。

- [ ] **Step 5: 提交卡片排版优化**

```powershell
git add frontend/src/views/dashboard/roi/RoiChartCard.vue frontend/src/views/dashboard/roi/RoiChartGrid.test.mjs
git commit -m "界面：优化 ROI 图表卡片排版"
```

---

### Task 3: 完整回归与视觉验证

**Files:**
- Verify: `frontend/src/views/dashboard/roi/RoiChartCard.vue`
- Verify: `frontend/src/views/dashboard/roi/RoiChartGrid.vue`
- Verify: `frontend/src/views/chat/component/charts/Table.ts`

**Interfaces:**
- Consumes: Task 1 的动态列宽更新和 Task 2 的卡片样式。
- Produces: 通过 ROI、resize、类型检查、生产构建和本地页面检查的最终实现。

- [ ] **Step 1: 运行聚焦回归测试**

运行：

```powershell
cd frontend
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/dashboard/roi/RoiChartGrid.test.mjs
node src/views/dashboard/roi/RoiDashboardPanel.test.mjs
```

预期：三个命令均退出码 `0`；resize 测试输出 `ChartComponent resize tests passed`。

- [ ] **Step 2: 运行类型检查与生产构建**

运行：

```powershell
cd frontend
npx vue-tsc -b
npm run build
```

预期：类型检查与 Vite 构建均退出码 `0`，不新增 TypeScript 或 Less 错误。

- [ ] **Step 3: 本地视觉验证**

使用仓库标准本地环境打开 ROI 看板，依次验证：

1. 全宽卡片中少字段表格铺满内容区，右侧无大面积空白。
2. 半宽和三分之一宽卡片标题、日期与操作按钮保持单行且不互相覆盖。
3. 多字段表格保持至少 `92px` 列宽并可横向滚动。
4. 切换页面、修改日期、单图刷新重新执行 SQL 时卡片高度保持 `320px`，不逐行扩展、不明显闪烁。
5. 拖动排序、宽度调整、编辑和删除入口保持可用。

- [ ] **Step 4: 检查最终工作区和提交记录**

运行：

```powershell
git status --short
git log -3 --oneline
```

预期：只保留用户已有的无关未跟踪目录 `.superpowers/brainstorm/`；最近提交包含表格宽度修复和卡片排版优化两个中文提交。
