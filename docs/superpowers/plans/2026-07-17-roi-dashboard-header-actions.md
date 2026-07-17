# ROI 看板顶部操作区精简 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 ROI 看板顶部的数据源设置和全局刷新按钮，仅保留“添加图表”，同时保留内部数据源配置与图表重载能力。

**Architecture:** 只修改 ROI 面板展示层和对应源码断言测试。删除两个顶部入口、专用图标导入及仅由顶部刷新入口调用的函数，不改 Store、API、弹窗组件、卡片内部操作或路由/异常恢复使用的重载函数。

**Tech Stack:** Vue 3、TypeScript、Element Plus Secondary、Node.js 源码断言测试、Vite。

## Global Constraints

- 只移除 ROI 看板顶部“数据源设置”和“全局刷新”两个入口。
- 顶部右侧必须保留“添加图表”按钮及其权限逻辑。
- 必须保留图表卡片内部日期、单图刷新、排序、宽度、编辑和删除功能。
- 必须保留 `RoiDatasourceDialog`、首次创建看板的数据源配置流程、`reloadCharts()` 与 `reloadChartsAfterConfigSave()`。
- 不修改后端、Store、API 或数据库配置。
- Git 提交信息使用中文。

---

### Task 1: 精简 ROI 看板顶部操作区

**Files:**
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs`
- Modify: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`

**Interfaces:**
- Consumes: 现有 `openNewChartEditor()`、`RoiDatasourceDialog`、`reloadCharts()` 和 `reloadChartsAfterConfigSave()`。
- Produces: 顶部只包含“添加图表”的 `RoiDashboardPanel`，不新增公共接口。

- [ ] **Step 1: 写入失败的顶部入口源码断言**

在 `frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs` 读取的 `panel` 源码断言区域增加：

```javascript
assert.doesNotMatch(panel, /content="设置数据源"/)
assert.doesNotMatch(panel, /content="刷新图表"/)
assert.doesNotMatch(panel, /refreshCurrentCharts/)
assert.doesNotMatch(panel, /Setting/)
assert.doesNotMatch(panel, /RefreshRight/)
assert.match(panel, /<el-button[^>]*type="primary"[\s\S]*?添加图表/)
assert.match(panel, /<RoiDatasourceDialog/)
assert.match(panel, /async function reloadCharts\(\)/)
assert.match(panel, /async function reloadChartsAfterConfigSave\(\)/)
```

- [ ] **Step 2: 运行测试确认红灯**

Run:

```powershell
Set-Location D:\AIWork3\chat-bi\frontend
node src/views/dashboard/roi/RoiDashboardPanel.test.mjs
```

Expected: FAIL，至少命中“设置数据源”“刷新图表”或 `refreshCurrentCharts` 仍存在。

- [ ] **Step 3: 删除顶部两个入口及专用代码**

在 `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue` 完成以下最小修改：

1. 将图标导入改为：

```typescript
import { Plus } from '@element-plus/icons-vue'
```

2. 完整删除 `refreshCurrentCharts()`，但保留 `refreshChart()`、`reloadCharts()` 与 `reloadChartsAfterConfigSave()`。

3. 将顶部操作区改为：

```vue
<div class="roi-dashboard-panel__actions">
  <el-button
    type="primary"
    :icon="Plus"
    :disabled="!canEdit"
    @click="openNewChartEditor"
  >
    添加图表
  </el-button>
</div>
```

4. 保留 `.roi-dashboard-panel__actions` 样式，以继续承担桌面端右对齐和移动端换行布局。

- [ ] **Step 4: 运行 ROI 面板与卡片回归测试**

Run:

```powershell
Set-Location D:\AIWork3\chat-bi\frontend
node src/views/dashboard/roi/RoiDashboardPanel.test.mjs
node src/views/dashboard/roi/RoiChartGrid.test.mjs
node src/views/chat/component/ChartComponent.resize.test.mjs
```

Expected:

```text
ROI dashboard panel tests passed
ROI chart grid tests passed
ChartComponent resize tests passed
```

- [ ] **Step 5: 运行类型检查和生产构建**

Run:

```powershell
Set-Location D:\AIWork3\chat-bi\frontend
npx vue-tsc -b --pretty false
npm run build
```

Expected: 两个命令退出码均为 `0`；Vite 输出 `built in`，允许保留现有 chunk size 和动态导入警告。

- [ ] **Step 6: 检查差异并提交**

Run:

```powershell
Set-Location D:\AIWork3\chat-bi
git diff --check
git status --short
git add -- frontend/src/views/dashboard/roi/RoiDashboardPanel.vue frontend/src/views/dashboard/roi/RoiDashboardPanel.test.mjs
git commit -m "界面：精简 ROI 看板顶部操作区"
```

Expected: 提交只包含上述两个实现/测试文件；不得包含 `.superpowers/brainstorm/`。
