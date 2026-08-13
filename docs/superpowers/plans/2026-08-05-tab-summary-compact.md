# Tab 卡片紧凑摘要显示调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让内容区达到 `300x250` 的小卡片显示紧凑摘要，仅在低于任一硬下界时隐藏摘要。

**Architecture:** 保持现有 `resolveInsightDisplay` 和 Tab 单向协调器边界，只调整顶部摘要的显示阈值。`TINY_MIN_WIDTH/HEIGHT` 是唯一硬隐藏边界；更大的卡片继续由已有 density 迟滞决定 `basic/mini/compact`，不写外框尺寸、不改变 ChartComponent key。

**Tech Stack:** Vue 3、TypeScript、Node 原生 `.mjs` 回归测试、`vue-tsc`、Vite。

## Global Constraints

- 内容区达到 `300x250` 时显示摘要；低于任一尺寸才隐藏。
- `300x250` 至 `440x360` 使用紧凑摘要密度。
- Tab 只由 Card 根节点 `border-box` 提供几何输入。
- 不观察 `chart-show-area`，不回写 `sizeX/sizeY`、外框或布局策略。
- ChartComponent 保持稳定 key；失败保留上一稳定状态，不使用异步重试。

---

### Task 1: 放宽摘要显示下界

**Files:**
- Modify: `frontend/src/views/chat/component/chartInsight.ts:440-459`
- Test: `frontend/src/views/chat/component/chartInsight.layout-stability.test.mjs:100-128`
- Test: `frontend/src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs`

**Interfaces:**
- Consumes: `resolveInsightDisplay` 的现有 `width`、`height`、`dashboard`、`previousDensity` 参数。
- Produces: 在 `300x250` 内容区返回 `show: true`、`density: 'basic'`；在 `299x250` 或 `300x249` 返回 `show: false`。

- [ ] **Step 1: Write the failing tests**

在 `chartInsight.layout-stability.test.mjs` 增加：

```js
const compactAtHardFloor = resolveInsightDisplay({
  ...trend,
  width: 300,
  height: 250,
  previousLayout: 'top',
})
assert.equal(compactAtHardFloor.show, true)
assert.equal(compactAtHardFloor.density, 'basic')

assert.equal(
  resolveInsightDisplay({ ...trend, width: 299, height: 250 }).show,
  false,
)
assert.equal(
  resolveInsightDisplay({ ...trend, width: 300, height: 249 }).show,
  false,
)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from `frontend`:

```powershell
node src/views/chat/component/chartInsight.layout-stability.test.mjs
```

Expected failure: the `300x250` assertion reports `false !== true`, proving the existing `440x360` early return is the behavior under change.

- [ ] **Step 3: Implement the minimal change**

In `resolveInsightDisplay`, keep the hard `TINY_MIN_WIDTH/HEIGHT` return. Remove the `topSummaryTooSmall` early return so the existing `belowBasicThreshold` branch returns a visible `basic` strategy for dimensions above the hard floor. Do not change observer, coordinator, key, or frame code.

- [ ] **Step 4: Run focused and regression tests**

```powershell
node src/views/chat/component/chartInsight.layout-stability.test.mjs
node src/views/chat/component/chartInsight.top-density-stability.test.mjs
node src/views/dashboard/components/sq-view/tabInsightLayout.test.mjs
node src/views/dashboard/components/sq-view/index.responsive-layout.test.mjs
node src/views/dashboard/components/sq-view/insightFrame.stability.test.mjs
```

Expected: all commands exit `0`; no `ResizeObserver` or key-related assertions change.

- [ ] **Step 5: Run typecheck and build**

```powershell
npx vue-tsc -b --pretty false
npm run build
```

Expected: both exit `0`; existing Rollup warnings may remain.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/views/chat/component/chartInsight.ts frontend/src/views/chat/component/chartInsight.layout-stability.test.mjs
git commit -m "修复：允许小尺寸卡片显示紧凑摘要"
```
