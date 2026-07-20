# ROI 看板固定入口样式统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让推荐看板下的 ROI 固定入口与普通推荐看板使用一致的图标、缩进、字号、行高、悬停和选中视觉，同时保留其虚拟分组、展开和菜单能力。

**Architecture:** 保留 ROI 固定入口的 `folder + virtual + roi scope` 业务身份，只在 `ResourceTree.vue` 模板中增加视觉角色 class，并让该节点复用普通推荐看板叶子的 `icon_dashboard_grid_add`、`icon-primary` 和 `18px` 左内边距。现有资源树数据、路由、权限、菜单、拖放和排序代码不改。

**Tech Stack:** Vue 3、TypeScript、Less、Element Plus Secondary、Node.js `assert` 源码契约测试、Vite、`vue-tsc`。

## Global Constraints

- ROI 固定入口继续保持 `node_type = 'folder'`、`virtual = true` 和 `dashboard_scope = 'roi'`。
- 只统一 ROI 固定入口视觉，不修改 ROI 数据源、后端模型、API、数据库迁移或业务数据。
- 图标必须使用现有 `icon_dashboard_grid_add` 和 `icon-primary`，不得新增图标资源。
- ROI 固定入口左内边距必须复用普通叶子的 `calc(var(--dashboard-tree-indent, 0px) + 18px)`。
- 其它虚拟根分组继续使用 `icon_dashboard_group_color` 和 `group-color-icon`。
- ROI 固定入口继续保留展开箭头、`newRoiDashboard`、`toggleTreeEditing` 和悬停三点菜单。
- ROI 子看板、普通推荐看板和“我的看板”的模板与样式不得改变。
- 不修改 `HandleMore.vue`、`buildCombinedTree()`、路由选择、权限、拖放或排序逻辑。
- 保留工作区中与本功能无关的 `.superpowers/brainstorm/` 和其它用户改动。

---

## File Map

- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue`
  - 为 ROI 固定入口增加视觉 class，选择普通看板网格图标，并局部复用叶子缩进。
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
  - 锁定视觉 class、图标分支、局部缩进和虚拟分组/菜单边界。
- Verify only: `frontend/src/views/dashboard/roi/roiNavigationBehavior.test.mjs`
  - 确认样式改动未影响 ROI 路由和命令白名单。
- Verify only: `frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`
  - 确认普通推荐看板复制行为不变。
- Verify only: `frontend/src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs`
  - 确认推荐看板刷新行为不变。

---

### Task 1: 统一 ROI 固定入口模板和局部样式

**Files:**
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:1663-1711`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:2319-2374`
- Test: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`

**Interfaces:**
- Consumes: 现有 `isRoiGroupNode(data)`、`icon_dashboard_grid_add`、`icon_dashboard_group_color`、`icon-primary` 和 `group-color-icon`。
- Produces: 模板 class `is-roi-entry-node`；ROI 专用图标分支；仅作用于该 class 的叶子同款左内边距。

- [ ] **Step 1: 写入失败的视觉契约测试**

在 `ResourceTree.roi.test.mjs` 末尾增加以下断言：

```js
assert.match(
  source,
  /'is-roi-entry-node': isRoiGroupNode\(data\)/,
  'ROI 固定入口必须具有独立视觉角色 class'
)

const roiEntryIcon = source.match(
  /<el-icon\s+v-else-if="isRoiGroupNode\(data\)"\s+class="tree-node-icon icon-primary">([\s\S]*?)<\/el-icon>/
)
assert.ok(roiEntryIcon, 'ROI 固定入口必须使用普通看板图标分支')
assert.match(roiEntryIcon[1], /name="icon_dashboard_grid_add"/)
assert.match(roiEntryIcon[1], /<icon_dashboard_grid_add class="svg-icon"/)
assert.doesNotMatch(roiEntryIcon[1], /icon_dashboard_group_color/)

assert.match(
  source,
  /v-else-if="data\.node_type !== 'leaf'"[\s\S]*?group-color-icon[\s\S]*?icon_dashboard_group_color/,
  '其它虚拟分组必须继续使用彩色分组图标'
)
assert.match(
  source,
  /&\.is-roi-entry-node\s*\{\s*padding-left:\s*calc\(var\(--dashboard-tree-indent, 0px\) \+ 18px\);\s*\}/,
  'ROI 固定入口必须复用普通叶子的 18px 左内边距'
)
assert.match(
  combinedTree[0],
  /createDashboardGroup\([\s\S]*?ROI_GROUP_ID[\s\S]*?ROI_SCOPE/,
  '样式统一不得把 ROI 固定入口改成真实叶子记录'
)
```

保留文件中已有的菜单白名单、初始路由和排序隔离断言，不替换为更宽松的正则。

- [ ] **Step 2: 运行测试并确认旧模板失败**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
```

Expected: FAIL，失败信息至少包含“ROI 固定入口必须具有独立视觉角色 class”或“必须使用普通看板图标分支”。

- [ ] **Step 3: 为 ROI 固定入口增加视觉 class**

在 `custom-tree-node` 的动态 class 对象中，紧邻 `is-group-node` 与 `is-leaf-node` 插入这一行：

```vue
'is-roi-entry-node': isRoiGroupNode(data),
```

不要重排或重写其它 class 条件。

- [ ] **Step 4: 让 ROI 固定入口复用普通看板网格图标**

在真实目录图标分支之后、通用虚拟分组图标分支之前插入：

```vue
<el-icon v-else-if="isRoiGroupNode(data)" class="tree-node-icon icon-primary">
  <Icon name="icon_dashboard_grid_add">
    <icon_dashboard_grid_add class="svg-icon" />
  </Icon>
</el-icon>
```

后续通用虚拟分组分支保持为：

```vue
<el-icon
  v-else-if="data.node_type !== 'leaf'"
  class="tree-node-icon"
  :class="{ 'group-color-icon': isVirtualNode(data) }"
>
  <Icon v-if="isVirtualNode(data)" name="icon_dashboard_group_color">
    <icon_dashboard_group_color class="svg-icon" />
  </Icon>
  <Icon v-else name="icon_folder"><icon_folder class="svg-icon" /></Icon>
</el-icon>
```

普通叶子节点现有 `v-else` 分支不改。

- [ ] **Step 5: 为 ROI 固定入口复用普通叶子缩进**

在 `.custom-tree-node` 内、现有 `.is-leaf-node/.is-empty-folder-node` 规则之后增加：

```less
&.is-roi-entry-node {
  padding-left: calc(var(--dashboard-tree-indent, 0px) + 18px);
}
```

该选择器必须局限于 `.custom-tree-node`，不要修改 `.ed-tree-node__content`、全局展开图标或其它虚拟分组。

- [ ] **Step 6: 运行聚焦测试并确认通过**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
node src/views/dashboard/roi/roiNavigationBehavior.test.mjs
node src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs
node src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs
```

Expected: 四个命令均退出码 `0`；ROI 导航输出 `ROI navigation behavior tests passed`，其它源码契约测试无断言错误。

- [ ] **Step 7: 检查补丁并提交**

Run:

```powershell
Set-Location ..
git diff --check
git diff -- frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
git status --short
git add -- frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
git commit -m "样式：统一ROI看板入口视觉"
```

Expected: `git diff --check` 无输出；提交只包含两个指定前端文件，`.superpowers/brainstorm/` 不进入暂存区。

---

### Task 2: 完成构建和登录态视觉验收

**Files:**
- Verify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Verify: `frontend/src/views/dashboard/roi/*.test.mjs`
- Verify: `frontend/src/stores/roiDashboard.behavior.test.mjs`
- Verify: `frontend/src/stores/roiRequestCoordinator.test.mjs`

**Interfaces:**
- Consumes: Task 1 的 `is-roi-entry-node`、普通网格图标分支和 `18px` 局部缩进。
- Produces: 自动测试、生产构建、DOM 尺寸比较和截图验收证据；本任务不新增源码提交。

- [ ] **Step 1: 运行完整资源树与 ROI 回归**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
node src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs
node src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs
Get-ChildItem src/views/dashboard/roi -Filter '*.test.mjs' | Sort-Object Name | ForEach-Object {
  node $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "ROI test failed: $($_.Name)" }
}
node src/stores/roiDashboard.behavior.test.mjs
node src/stores/roiRequestCoordinator.test.mjs
```

Expected: 所有命令退出码 `0`，ROI 图表、面板、导航、SQL 编辑器和 Store 测试全部通过。

- [ ] **Step 2: 运行生产构建**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: `vue-tsc -b` 与 `vite build` 均通过，进程退出码 `0`。既有 Rollup 动态导入和大 chunk 警告可以记录，但不得出现新增编译错误。

- [ ] **Step 3: 确认本地前端和四服务状态**

Run:

```powershell
Set-Location ..
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: API `8000`、MCP `8001`、一个本地 Worker 和前端 `5173` 均运行；同时核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

- [ ] **Step 4: 在登录态页面量化对齐结果**

打开 `http://127.0.0.1:5173/#/dashboard/index?dashboardMode=roi`。在浏览器只读执行以下 DOM 投影，分别读取一个普通推荐看板叶子和 ROI 固定入口：

```js
Array.from(document.querySelectorAll('.custom-tree-node')).
  filter((node) => ['核心看板', 'ROI 看板'].includes(node.querySelector('.label-tooltip')?.textContent?.trim())).
  map((node) => {
    const icon = node.querySelector('.tree-node-icon')
    const label = node.querySelector('.label-tooltip')
    const row = node.closest('.ed-tree-node__content')
    const iconRect = icon?.getBoundingClientRect()
    const labelRect = label?.getBoundingClientRect()
    const rowRect = row?.getBoundingClientRect()
    return {
      label: label?.textContent?.trim(),
      nodeClasses: node.className,
      iconClasses: icon?.className,
      iconLeft: iconRect?.left,
      iconWidth: iconRect?.width,
      labelLeft: labelRect?.left,
      rowHeight: rowRect?.height,
      fontSize: label ? getComputedStyle(label).fontSize : null,
      lineHeight: label ? getComputedStyle(label).lineHeight : null,
    }
  })
```

Expected:

```text
ROI 看板 nodeClasses 包含 is-roi-entry-node，iconClasses 包含 icon-primary。
两行 iconWidth 都为 14px，rowHeight 都为 32px。
两行 iconLeft 差值不超过 1px，labelLeft 差值不超过 1px。
两行 fontSize 都为 13px，lineHeight 都为 20px。
```

- [ ] **Step 5: 检查五种可见状态**

依次验证并保存截图证据：

```text
1. 默认：ROI 使用灰色网格图标，不再出现彩色分组图标。
2. 悬停：行背景与普通推荐看板一致，三点菜单只在悬停时出现。
3. 选中：行背景使用统一 active 色，网格图标使用统一主色和缩放。
4. 展开：存在 ROI 子看板时展开箭头可用，子看板仍显示在入口下方。
5. 空子树：没有 ROI 子看板时图标和文字位置不跳动，入口菜单仍可新建下属看板。
```

不得为了截图删除现有 ROI 子看板；空子树状态只在已有可控空工作空间或无数据测试环境中验证，否则明确记录该项未执行。

- [ ] **Step 6: 完成最终 Git 边界检查**

Run:

```powershell
git diff --check
git status --short
git show --stat --oneline HEAD
```

Expected: `git diff --check` 无输出；除用户原有 `.superpowers/brainstorm/` 外工作区干净；最终功能提交仅包含 `ResourceTree.vue` 和 `ResourceTree.roi.test.mjs`。
