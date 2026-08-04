# 看板图表二维布局稳定性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除摘要可见时由宽高反馈引起的看板图表持续重绘和加载遮罩闪烁。

**Architecture:** 保留现有摘要显隐和密度策略，仅在 `SQView` 布局边界修正 Flex 尺寸所有权。外层图表区域与内部图表行使用零 Flex 基准，并在宽高两个轴向允许收缩，使 `ResizeObserver` 只响应真实的卡片尺寸变化。

**Tech Stack:** Vue 3、TypeScript、Less、Node.js `assert` 回归测试。

## Global Constraints

- 不增加新的摘要宽高阈值或业务特例。
- 不修改数据加载、刷新状态或摘要统计口径。
- 顶部摘要和侧边摘要必须共用同一套双轴收缩约束。
- 所有源代码修改都在链接工作树 `D:\AIWork3\chat-bi\.worktrees\codex-dashboard-chart-layout-thrash-flicker` 完成。

---

### Task 1: 稳定摘要与图表的二维 Flex 分配

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:3470`

**Interfaces:**
- Consumes: `chart-show-area`、`chart-content-row` 和子级 `chart-container` 的现有 DOM 结构。
- Produces: 顶部和侧边摘要共用的稳定剩余空间，不改变 Vue props、events 或数据接口。

- [ ] **Step 1: 写入失败的双轴布局回归断言**

将原有 `chart-show-area` 的 `flex: 1 1 auto` 断言替换为以下断言，并增加图表行及图表容器断言：

```js
assert.match(
  style,
  /\.chart-show-area\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '图表外层必须使用零基准并允许双轴收缩，避免摘要尺寸反推父容器'
)
assert.match(
  style,
  /\.chart-content-row\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '顶部和侧边摘要共用的图表行必须使用稳定剩余空间'
)
assert.match(
  style,
  /:deep\(\.chart-container\)\s*\{[^}]*flex:\s*1\s+1\s+0[^}]*min-width:\s*0[^}]*min-height:\s*0/s,
  '图表容器不能通过内容宽高反向撑开图表行'
)
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```powershell
node frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
```

Expected: FAIL，错误指出 `chart-show-area` 尚未使用 `flex: 1 1 0` 或缺少 `min-width: 0`。

- [ ] **Step 3: 写入最小 Flex 修复**

在 `index.vue` 的现有样式中更新三层容器：

```less
.chart-show-area {
  width: 100%;
  flex: 1 1 0;
  height: auto;
  min-width: 0;
  min-height: 0;

  :deep(.chart-container) {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
  }

  .chart-content-row {
    flex: 1 1 0;
    min-width: 0;
    min-height: 0;
  }
}
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run:

```powershell
node frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node frontend/src/views/dashboard/components/sq-view/index.state-machine.test.mjs
node frontend/src/views/dashboard/components/sq-view/index.empty-state.test.mjs
Push-Location frontend
node src/views/chat/component/ChartComponent.resize.test.mjs
node src/views/chat/component/ChartComponent.atomic-render.test.mjs
npm run build
Pop-Location
```

Expected: 所有测试通过，Vite 构建成功；允许保留仓库已有的 Rollup/Vite 警告。

- [ ] **Step 5: 提交实现**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs frontend/src/views/dashboard/components/sq-view/index.vue docs/superpowers/plans/2026-08-04-dashboard-chart-two-dimensional-layout-stability.md
git diff --cached --check
git commit -m "修复看板图表摘要二维布局闪烁"
```
