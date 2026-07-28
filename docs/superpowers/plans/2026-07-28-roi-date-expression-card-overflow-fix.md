# ROI 日期表达式卡片底部遮挡修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复启用日期表达式的 ROI 卡片中折线图 X 轴和表格底部被卡片边界裁切的问题。

**Architecture:** 保留现有 `SQView` 卡片结构，只为包含 `.date-expression-toolbar` 的卡片增加内容区高度扣减规则。使用现有 `:has(...)` CSS 模式分别覆盖普通、紧凑、透视组合，避免影响普通日期筛选卡片。

**Tech Stack:** Vue 3、Less scoped CSS、Node.js 契约测试、Vite。

## Global Constraints

- 只修改启用 `date-expression-toolbar` 的 ROI 卡片。
- 不修改普通看板原日期筛选器的布局和行为。
- 不修改卡片持久化尺寸、看板数据或 SQL。
- 保留工作区中已有日志和并行计划文件，不使用 `git add .`。

---

### Task 1: 增加遮挡回归契约并修复高度规则

**Files:**
- Modify: `frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs`
- Modify: `frontend/src/views/dashboard/components/sq-view/index.vue:3309-3324`

**Interfaces:**
- Consumes: 当前 `.chart-show-area` 的普通、紧凑和透视组合高度规则。
- Produces: 日期表达式工具栏存在时的专用高度规则，只匹配 `.date-expression-toolbar`。

- [ ] **Step 1: 写失败测试**

在现有 `index.date-filter.test.mjs` 末尾增加断言，要求源码包含以下四种日期表达式高度规则：普通 `82px`、普通加透视 `116px`、紧凑 `70px`、紧凑加透视 `94px`，并覆盖 `insight-density-mini` 和 `insight-density-basic`。

```js
assert.match(
  source,
  /\.chart-base-container:has\(\.date-expression-toolbar\) \.chart-show-area[\s\S]*height: calc\(100% - 82px\)/
)
assert.match(
  source,
  /\.chart-base-container:has\(\.date-expression-toolbar\):has\(\.pivot-toolbar\) \.chart-show-area[\s\S]*height: calc\(100% - 116px\)/
)
assert.match(
  source,
  /\.insight-density-mini:has\(\.date-expression-toolbar\) \.chart-show-area[\s\S]*height: calc\(100% - 70px\)/
)
assert.match(
  source,
  /\.insight-density-basic:has\(\.date-expression-toolbar\):has\(\.pivot-toolbar\) \.chart-show-area[\s\S]*height: calc\(100% - 94px\)/
)
```

- [ ] **Step 2: 运行测试确认失败**

运行：

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
```

预期：失败，提示缺少 `.date-expression-toolbar` 的高度规则。

- [ ] **Step 3: 实现最小 CSS 修复**

在现有透视组合规则之后增加以下规则：

```less
.chart-base-container:has(.date-expression-toolbar) .chart-show-area {
  height: calc(100% - 82px);
}

.chart-base-container:has(.date-expression-toolbar):has(.pivot-toolbar) .chart-show-area {
  height: calc(100% - 116px);
}

.insight-density-mini:has(.date-expression-toolbar) .chart-show-area,
.insight-density-basic:has(.date-expression-toolbar) .chart-show-area {
  height: calc(100% - 70px);
}

.insight-density-mini:has(.date-expression-toolbar):has(.pivot-toolbar) .chart-show-area,
.insight-density-basic:has(.date-expression-toolbar):has(.pivot-toolbar) .chart-show-area {
  height: calc(100% - 94px);
}
```

- [ ] **Step 4: 运行 focused 测试确认通过**

运行：

```powershell
cd frontend
node src/views/dashboard/components/sq-view/index.date-filter.test.mjs
node src/views/dashboard/common/dashboardDateExpression.test.mjs
node src/views/dashboard/common/DashboardDateExpressionPicker.test.mjs
```

预期：三个测试均通过。

- [ ] **Step 5: 构建并检查工作区**

运行：

```powershell
cd frontend
npm run build
cd ..
git diff --check
git status --short
```

预期：构建成功；仅日期筛选测试、`sq-view/index.vue` 和本计划文件属于本次修改，已有日志及并行计划文件保持未暂存。

- [ ] **Step 6: 提交本次代码修复**

```powershell
git add -- frontend/src/views/dashboard/components/sq-view/index.vue frontend/src/views/dashboard/components/sq-view/index.date-filter.test.mjs
git diff --cached --stat
git commit -m "修复：避免 ROI 日期卡片底部遮挡"
```

