# 看板左右边距统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有顶层看板的左右总边距统一为 `16px`，同时保持卡片间距和 Tab 内嵌看板布局不变。

**Architecture:** 在公共网格工具中增加纯函数，独立计算容器宽度、边缘间距、卡片间距和列数对应的单列步进宽度；`SQPreview.vue` 根据是否为 Tab 选择边缘间距并消费该函数。已有网格坐标和持久化数据不变，测试通过纯函数断言和 Vue 源码契约覆盖关键边界。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert`、esbuild、Vite

## Global Constraints

- 所有顶层看板左右总边距必须统一为 `16px`。
- 顶层卡片之间继续使用现有 `10px` 间距。
- Tab 内嵌看板继续使用现有 `6px` 紧凑间距，不叠加顶层边距。
- 不修改看板持久化坐标、尺寸、后端接口、卡片内部 padding 或 AI 解读浮层。
- 极窄容器不得产生负卡片宽度或横向滚动条。

---

## File Structure

- Modify: `frontend/src/views/dashboard/utils/dashboardGridPosition.ts`：提供独立、可复用、可测试的横向网格宽度计算。
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue`：区分外边距与卡片间距，并将横向定位接入公共计算。
- Modify: `frontend/src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs`：覆盖左右边界、卡片间距、Tab 兼容和源码接线契约。

### Task 1: 增加横向网格宽度纯函数

**Files:**
- Modify: `frontend/src/views/dashboard/utils/dashboardGridPosition.ts`
- Test: `frontend/src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs`

**Interfaces:**
- Consumes: `containerWidth: number`、`columnCount: number`、`gridGap: number`、`edgeGap: number`。
- Produces: `getDashboardGridCellWidth(containerWidth, columnCount, gridGap, edgeGap): number`，供 `SQPreview.vue` 计算单列步进宽度。

- [ ] **Step 1: 扩展测试导入并写入失败断言**

将测试模块导入改为：

```js
const { getDashboardGridCellWidth, getDashboardGridContentRows } = await import(moduleUrl)
```

在现有内容行数断言后加入：

```js
const topLevelCellWidth = getDashboardGridCellWidth(1000, 72, 10, 16)
assert.equal(topLevelCellWidth, (1000 - 16 * 2 + 10) / 72)
assert.equal(16 + topLevelCellWidth * 72 - 10, 984)

const tabCellWidth = getDashboardGridCellWidth(1000, 72, 6, 6)
assert.equal(tabCellWidth, (1000 - 6) / 72)
assert.equal(6 + tabCellWidth * 72 - 6, 994)

assert.equal(getDashboardGridCellWidth(20, 72, 10, 16), 10 / 72)
```

- [ ] **Step 2: 运行测试并确认因缺少导出而失败**

Run:

```powershell
cd frontend
node src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
```

Expected: FAIL，错误指出 `getDashboardGridCellWidth is not a function`。

- [ ] **Step 3: 实现最小横向网格宽度函数**

在 `dashboardGridPosition.ts` 的类型声明后加入：

```ts
export function getDashboardGridCellWidth(
  containerWidth: number,
  columnCount: number,
  gridGap: number,
  edgeGap: number
): number {
  const safeContainerWidth = Number.isFinite(containerWidth) ? Math.max(0, containerWidth) : 0
  const safeColumnCount = Number.isFinite(columnCount)
    ? Math.max(1, Math.round(columnCount))
    : 1
  const safeGridGap = Number.isFinite(gridGap) ? Math.max(0, gridGap) : 0
  const safeEdgeGap = Number.isFinite(edgeGap) ? Math.max(0, edgeGap) : 0
  const availableWidth = Math.max(0, safeContainerWidth - safeEdgeGap * 2)

  return (availableWidth + safeGridGap) / safeColumnCount
}
```

- [ ] **Step 4: 运行聚焦测试并确认通过**

Run:

```powershell
cd frontend
node src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
```

Expected: PASS，并输出 `SQPreview scroll boundary tests passed`。

- [ ] **Step 5: 提交纯函数和测试**

```powershell
git add -- frontend/src/views/dashboard/utils/dashboardGridPosition.ts frontend/src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
git diff --cached --check
git commit -m "测试：覆盖看板横向边距计算"
```

### Task 2: 将顶层看板接入独立左右边距

**Files:**
- Modify: `frontend/src/views/dashboard/preview/SQPreview.vue`
- Test: `frontend/src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs`

**Interfaces:**
- Consumes: Task 1 导出的 `getDashboardGridCellWidth(containerWidth, columnCount, gridGap, edgeGap): number`。
- Produces: 顶层看板 `edgeGap=16`、`gridGap=10`，Tab 看板 `edgeGap=6`、`gridGap=6` 的公共预览布局。

- [ ] **Step 1: 添加 Vue 接线的失败契约测试**

在 `previewSource` 断言后加入：

```js
assert.match(previewSource, /const PREVIEW_EDGE_GAP = 16/)
assert.match(previewSource, /const edgeGap = props\.inTab \? gridGap : PREVIEW_EDGE_GAP/)
assert.match(
  previewSource,
  /getDashboardGridCellWidth\(\s*screenWidth,\s*props\.baseMatrixCount\.x,\s*gridGap,\s*edgeGap\s*\)/
)
assert.match(previewSource, /basePaddingLeft\.value = edgeGap/)
assert.match(
  previewSource,
  /left: cellWidth\.value \* \(gridX - 1\) \+ basePaddingLeft\.value \+ 'px'/
)
assert.match(
  previewSource,
  /width: Math\.max\(0, cellWidth\.value \* item\.sizeX - baseMarginLeft\.value\) \+ 'px'/
)
```

- [ ] **Step 2: 运行测试并确认源码契约失败**

Run:

```powershell
cd frontend
node src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
```

Expected: FAIL，第一个未满足断言为缺少 `PREVIEW_EDGE_GAP`。

- [ ] **Step 3: 修改 `SQPreview.vue` 的导入和布局状态**

将网格工具导入改为：

```ts
import {
  getDashboardGridCellWidth,
  getDashboardGridContentRows,
  normalizeDashboardGridCoordinate,
} from '@/views/dashboard/utils/dashboardGridPosition.ts'
```

删除只用于旧公式的 `baseWidth`，并增加独立左边距状态和顶层边距常量：

```ts
const cellWidth = ref(0)
const cellHeight = ref(0)
const viewportHeight = ref(0)
const baseHeight = ref(0)
const baseMarginLeft = ref(0)
const baseMarginTop = ref(0)
const basePaddingLeft = ref(0)
const basePaddingTop = ref(0)
const PREVIEW_GRID_GAP = 10
const PREVIEW_EDGE_GAP = 16
const PREVIEW_TOP_GAP = 4
const TAB_PREVIEW_GRID_GAP = 6
```

- [ ] **Step 4: 修改卡片横向样式和宽度计算**

将 `nowItemStyle` 的横向字段改为：

```ts
width: Math.max(0, cellWidth.value * item.sizeX - baseMarginLeft.value) + 'px',
left: cellWidth.value * (gridX - 1) + basePaddingLeft.value + 'px',
```

将 `sizeInit` 中旧的 `baseWidth` 横向计算替换为：

```ts
const gridGap = props.inTab ? TAB_PREVIEW_GRID_GAP : PREVIEW_GRID_GAP
const edgeGap = props.inTab ? gridGap : PREVIEW_EDGE_GAP
baseMarginLeft.value = gridGap
baseMarginTop.value = gridGap
basePaddingLeft.value = edgeGap
basePaddingTop.value = props.inTab ? gridGap : PREVIEW_TOP_GAP
cellWidth.value = getDashboardGridCellWidth(
  screenWidth,
  props.baseMatrixCount.x,
  gridGap,
  edgeGap
)
baseHeight.value =
  (screenHeight - baseMarginTop.value) / props.baseMatrixCount.y - baseMarginTop.value
cellHeight.value = baseHeight.value + baseMarginTop.value
```

- [ ] **Step 5: 运行聚焦测试和类型构建**

Run:

```powershell
cd frontend
node src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
npm run build
```

Expected: 测试输出 `SQPreview scroll boundary tests passed`；构建退出码为 `0`。

- [ ] **Step 6: 提交看板接线改动**

```powershell
git add -- frontend/src/views/dashboard/preview/SQPreview.vue frontend/src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
git diff --cached --check
git commit -m "优化：统一看板左右边距"
```

### Task 3: 浏览器验证公共看板布局

**Files:**
- Verify: `frontend/src/views/dashboard/preview/SQPreview.vue`

**Interfaces:**
- Consumes: Task 2 的公共看板预览布局。
- Produces: 桌面视口下左右边距、卡片间距和滚动行为的可见验证结果。

- [ ] **Step 1: 确认本地四服务状态**

从仓库根目录运行：

```powershell
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: API `8000`、MCP `8001`、Worker 和前端 `5173` 均处于运行状态。若未运行，使用 `starting-chat-bi-local` 技能按仓库标准启动，不操作远程服务。

- [ ] **Step 2: 在浏览器检查普通看板和长表格看板**

使用 `browser:control-in-app-browser` 打开 `http://127.0.0.1:5173/`，登录后分别检查一个普通多卡片看板和截图中的长表格看板。通过浏览器脚本读取 `.canvas-container` 与最左、最右 `.wrapper-outer` 的 `getBoundingClientRect()`。

Expected: 最左卡片到画布左边界为 `16px`，满宽或最右卡片到画布右边界为 `16px`，多列卡片间距仍为 `10px`。

- [ ] **Step 3: 验证缩放和溢出**

在至少 `1920x900` 和 `1280x720` 两个视口检查同一看板，并记录截图。

Expected: 两个视口的左右边距均对称；`canvas.scrollWidth === canvas.clientWidth`；长表格不越过右边界；页面元素无重叠。

- [ ] **Step 4: 最终回归检查**

Run:

```powershell
cd frontend
node src/views/dashboard/preview/SQPreview.scroll-boundary.test.mjs
npm run build
cd ..
git status --short
```

Expected: 聚焦测试和构建通过；工作区只包含明确保留的用户变更，不存在本任务未提交文件。
