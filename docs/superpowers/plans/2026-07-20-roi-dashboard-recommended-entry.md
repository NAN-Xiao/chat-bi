# ROI 看板归入推荐看板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将固定的 ROI 看板入口移动到推荐看板下方，同时保留 ROI 子看板的独立路由、管理能力和排序语义，并禁止删除固定入口。

**Architecture:** 继续由前端组合普通推荐看板、ROI 看板和我的看板三类数据，不修改后端模型或 API。资源树把现有 ROI 虚拟分组嵌套为推荐看板的最后一个子节点，并在树组合、点击路由和排序持久化三个边界显式保持 `default` 与 `roi` 作用域隔离。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vue Router、Element Plus Secondary、Node.js `assert` 回归测试、Vite、`vue-tsc`。

## Global Constraints

- 固定的“ROI 看板”入口不可删除、不可重命名、不可复制，也不创建普通 `CoreDashboard` 或 `CoreDashboardTree` 记录。
- ROI 子看板继续使用 `CoreRoiDashboard`、`dashboardMode=roi`、ROI API 和现有工作空间权限。
- ROI 子看板继续允许工作空间所有者和管理员新建、重命名、删除和排序。
- 普通推荐看板继续使用 `dashboardMode=default`，复制、移出推荐看板和排序行为不得改变。
- 固定 ROI 入口始终位于普通推荐看板节点之后，不参与普通推荐看板后端排序。
- 普通推荐看板与 ROI 节点禁止跨作用域拖放，不增加静默兼容回退。
- 不修改后端模型、迁移、服务、API、ROI 数据源配置或 SQL 执行链路。
- 保留工作区中与本功能无关的未跟踪文件和用户改动。

---

## File Map

- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue`
  - 负责组合树层级、递归定位 ROI 虚拟入口、固定入口点击路由、菜单分发、拖放限制和三类排序持久化。
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
  - 以现有源码契约测试方式锁定 ROI 嵌套层级、固定入口不可删除、点击顺序和排序隔离。
- Reference only: `frontend/src/views/dashboard/preview/SQPreviewShow.vue`
  - 已支持 `dashboardMode=roi` 且 `resourceId` 为空时清理普通看板状态并展示 ROI 面板，无需修改。
- Reference only: `frontend/src/views/dashboard/roi/RoiDashboardPanel.vue`
  - 已支持空 `dashboardId` 的 ROI 空状态，并通过现有 Store 请求接收“新建下属看板”动作，无需新增页面内选择器。

---

### Task 1: 将 ROI 虚拟入口嵌套到推荐看板并隔离排序

**Files:**
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:243-359`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:937-960`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:1343-1361`

**Interfaces:**
- Consumes: 现有 `createDashboardGroup(id, name, scope, children)`、`normalizeDefaultDashboardNodes()`、`normalizeRoiDashboardNodes()`、`collectTreeOrderItems()`。
- Produces: 递归 `findDashboardGroupNode(nodes, groupId)`；顶层仅含推荐和我的组合树；普通推荐排序仅收集 `dashboard_scope === 'default'` 的真实节点。

- [ ] **Step 1: 写入失败的树结构和排序隔离断言**

在 `ResourceTree.roi.test.mjs` 中替换旧的三顶层顺序断言，并增加以下契约：

```js
const combinedTree = source.match(
  /const buildCombinedTree = \([\s\S]*?\r?\n\}\r?\n\r?\nconst findDashboardNode/
)
assert.ok(combinedTree, '必须保留组合看板树构造函数')
assert.match(
  combinedTree[0],
  /const defaultChildren = normalizeDefaultDashboardNodes\(defaultNodes\)/,
  '普通推荐看板应先形成独立子节点列表'
)
assert.match(
  combinedTree[0],
  /defaultChildren\.push\([\s\S]*?ROI_GROUP_ID[\s\S]*?normalizeRoiDashboardNodes\(roiNodes\)/,
  'ROI 虚拟入口必须追加到推荐看板内部'
)
assert.doesNotMatch(
  combinedTree[0],
  /\.\.\.\(canManageCurrentWorkspace\.value/,
  'ROI 入口不能继续作为顶层分组'
)

assert.match(
  source,
  /const findDashboardGroupNode = \([\s\S]*?findDashboardGroupNode\(node\.children \|\| \[\], groupId\)/,
  '嵌套后的 ROI 虚拟入口必须支持递归定位'
)
assert.match(
  source,
  /collectTreeOrderItems\([\s\S]*?DEFAULT_SCOPE,[\s\S]*?\(node\) => getDashboardScope\(node\) === DEFAULT_SCOPE/,
  '普通推荐排序必须排除 ROI 子树'
)
```

同时删除以下旧结构断言：

```js
assert.ok(source.indexOf('DEFAULT_GROUP_ID') < source.indexOf('ROI_GROUP_ID'))
assert.ok(source.indexOf('ROI_GROUP_ID') < source.indexOf('MY_GROUP_ID'))
```

- [ ] **Step 2: 运行测试并确认它因旧三顶层结构失败**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
```

Expected: FAIL，失败信息至少包含“ROI 虚拟入口必须追加到推荐看板内部”或“嵌套后的 ROI 虚拟入口必须支持递归定位”。

- [ ] **Step 3: 实现递归分组定位和两顶层组合树**

在 `ResourceTree.vue` 中用递归分组定位替换三个只查找顶层的 `nodes.find(...)`：

```ts
const findDashboardGroupNode = (
  nodes: SQTreeNode[] = [],
  groupId: string
): SQTreeNode | undefined => {
  for (const node of nodes) {
    if (isVirtualNode(node) && String(node.id || '') === groupId) return node
    const matched = findDashboardGroupNode(node.children || [], groupId)
    if (matched) return matched
  }
  return undefined
}

const findDefaultGroupNode = (nodes: SQTreeNode[] = []) =>
  findDashboardGroupNode(nodes, DEFAULT_GROUP_ID)
const findMyGroupNode = (nodes: SQTreeNode[] = []) =>
  findDashboardGroupNode(nodes, MY_GROUP_ID)
const findRoiGroupNode = (nodes: SQTreeNode[] = []) =>
  findDashboardGroupNode(nodes, ROI_GROUP_ID)
```

将 `buildCombinedTree` 改为先构造推荐看板子节点，并在有 ROI 权限时把 ROI 虚拟入口追加到末尾：

```ts
const buildCombinedTree = (
  defaultNodes: SQTreeNode[] = [],
  roiNodes: RoiDashboard[] = [],
  myNodes: SQTreeNode[] = []
) => {
  const defaultChildren = normalizeDefaultDashboardNodes(defaultNodes)
  if (canManageCurrentWorkspace.value) {
    defaultChildren.push(
      createDashboardGroup(
        ROI_GROUP_ID,
        t('dashboard.roi_dashboard'),
        ROI_SCOPE,
        normalizeRoiDashboardNodes(roiNodes)
      )
    )
  }
  return [
    createDashboardGroup(
      DEFAULT_GROUP_ID,
      t('dashboard.default_dashboard'),
      DEFAULT_SCOPE,
      defaultChildren
    ),
    createDashboardGroup(
      MY_GROUP_ID,
      t('dashboard.dashboard'),
      MY_SCOPE,
      normalizeMyDashboardNodes(myNodes)
    ),
  ]
}
```

- [ ] **Step 4: 过滤普通推荐看板排序并保持 ROI 独立排序**

在 `saveTreeOrder()` 中给普通推荐看板收集器传入现有 `includeNode` 参数，防止递归进入 ROI 虚拟入口后把 ROI ID 作为普通看板提交：

```ts
const defaultItems = collectTreeOrderItems(
  defaultNodes,
  props.defaultMode ? 'root' : DEFAULT_GROUP_ID,
  DEFAULT_SCOPE,
  [],
  (node) => getDashboardScope(node) === DEFAULT_SCOPE
)
```

保留现有 ROI 排序代码，通过新的递归 `findRoiGroupNode(state.resourceTree)` 读取嵌套入口的直接子节点：

```ts
const roiNodes = findRoiGroupNode(state.resourceTree)?.children || []
const roiItems = roiNodes.map((node, index) => ({
  id: String(getRawDashboardId(node)),
  sort: index + 1,
  version: Number(node.version),
}))
```

- [ ] **Step 5: 运行资源树测试并确认通过**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
```

Expected: PASS，进程退出码 `0` 且无断言错误。

- [ ] **Step 6: 提交树结构和排序隔离**

```powershell
git add -- frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
git commit -m "功能：将ROI入口归入推荐看板"
```

---

### Task 2: 实现固定 ROI 入口点击和不可删除契约

**Files:**
- Modify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:402-460`
- Modify: `frontend/src/views/dashboard/common/ResourceTree.vue:482-545`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.vue:753-835`

**Interfaces:**
- Consumes: Task 1 产出的嵌套 ROI 虚拟入口；现有 `findDashboardNode()`、`findFirstLeafDashboardNode()`、`selectDashboardNode()`、`emitDashboardNodeClick()`。
- Produces: `resolveRoiGroupTarget(data): SQTreeNode | undefined`、`syncEmptyRoiRoute(): void` 和 `activateRoiGroupNode(data): void`；固定入口点击保留有效当前子看板，否则选择首个子看板，无子看板时进入无 `resourceId` 的 ROI 空路由。

- [ ] **Step 1: 写入失败的点击顺序和菜单断言**

在 `ResourceTree.roi.test.mjs` 增加入口解析和空路由断言，并扩展文件中已有的 `nodeClick`、`roiMenu` 断言块，避免重复声明同名常量：

```js
assert.match(
  source,
  /const resolveRoiGroupTarget = \(data: SQTreeNode\)[\s\S]*?findFirstLeafDashboardNode\(data\.children \|\| \[\]\)/,
  '固定 ROI 入口必须解析当前或首个下属看板'
)
assert.match(
  source,
  /const syncEmptyRoiRoute = \(\)[\s\S]*?dashboardMode: ROI_SCOPE/,
  '无下属看板时必须进入明确的 ROI 空路由'
)

assert.ok(
  nodeClick[1].indexOf('isRoiGroupNode(data)') < nodeClick[1].indexOf('isVirtualNode(data)'),
  '固定 ROI 入口必须在通用虚拟节点返回前处理'
)
assert.match(nodeClick[1], /activateRoiGroupNode\(data\)/)

assert.ok(roiMenu, '固定 ROI 入口必须保留独立菜单')
assert.match(roiMenu[1], /newRoiDashboard/)
assert.match(roiMenu[1], /toggleTreeEditing/)
assert.doesNotMatch(
  roiMenu[1],
  /deleteRoiDashboard|renameRoiDashboard|copyDefault|removeDefault/,
  '固定 ROI 入口不得出现删除、重命名或普通推荐看板命令'
)
```

- [ ] **Step 2: 运行测试并确认固定入口尚未处理点击**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
```

Expected: FAIL，失败信息包含“固定 ROI 入口必须解析当前或首个下属看板”或“必须在通用虚拟节点返回前处理”。

- [ ] **Step 3: 实现当前或首个 ROI 子看板解析**

在 `findDashboardNode()` 和 `currentRouteDashboardId()` 可用之后新增：

```ts
const resolveRoiGroupTarget = (data: SQTreeNode) => {
  const currentId =
    currentRouteDashboardScope() === ROI_SCOPE ? currentRouteDashboardId() : undefined
  const currentNode = currentId
    ? findDashboardNode(data.children || [], currentId, ROI_SCOPE)
    : undefined
  return isLeafDashboardNode(currentNode)
    ? currentNode
    : findFirstLeafDashboardNode(data.children || [])
}
```

这保证重复点击固定入口不会强制切回第一个子看板；从普通看板进入时才选择第一个可用 ROI 子看板。

- [ ] **Step 4: 实现无下属看板的 ROI 空路由**

新增只服务于预览页的路由同步函数，显式移除普通或失效资源 ID：

```ts
const syncEmptyRoiRoute = () => {
  if (props.showPosition !== 'preview' || props.defaultMode) return
  const currentRoute = router.currentRoute.value
  if (currentRoute.path !== '/dashboard/index') return
  const query = { ...currentRoute.query }
  delete query.resourceId
  delete query.dashboardId
  router.replace({
    path: currentRoute.path,
    query: {
      ...query,
      dashboardMode: ROI_SCOPE,
    },
  })
}
```

保留下划线前缀变量，避免 TypeScript/ESLint 将解构出的待移除字段视为误用；不要使用空字符串伪造 ROI 看板 ID。

- [ ] **Step 5: 在通用虚拟节点返回前激活固定入口**

新增激活函数：

```ts
const activateRoiGroupNode = (data: SQTreeNode) => {
  const target = resolveRoiGroupTarget(data)
  if (target) {
    selectDashboardNode(target)
    emitDashboardNodeClick(target)
    return
  }
  selectedNodeKey.value = null
  resourceListTree.value?.setCurrentKey?.(null)
  syncEmptyRoiRoute()
}
```

并在 `nodeClick()` 中保持现有普通 Store 清理计划后、通用虚拟节点返回前处理 ROI 入口：

```ts
const nodeClick = (data: SQTreeNode, node: any) => {
  const clickPlan = createDashboardNodeClickPlan(getDashboardScope(data))
  if (clickPlan.resetOrdinaryDashboardSelection) {
    dashboardStore.setCurComponent({ component: null, index: null })
  }
  if (isRoiGroupNode(data)) {
    activateRoiGroupNode(data)
    return
  }
  if (isVirtualNode(data)) {
    resourceListTree.value?.setCurrentKey?.(null)
    return
  }
}
```

以上代码只替换 `nodeClick()` 中现有的通用 `if (isVirtualNode(data))` 片段；其后从 `if (node.disabled)` 开始的真实节点处理代码逐行保留。不要为固定入口添加 `deleteRoiDashboard` 分支。现有 `nodeMenuList()` 中 ROI 入口只含 `newRoiDashboard` 和 `toggleTreeEditing`，子看板菜单中的 `renameRoiDashboard` 和 `deleteRoiDashboard` 保持不变。

- [ ] **Step 6: 运行点击和菜单测试并确认通过**

Run:

```powershell
Set-Location frontend
node src/views/dashboard/common/ResourceTree.roi.test.mjs
node src/views/dashboard/roi/roiNavigationBehavior.test.mjs
node src/views/dashboard/roi/roiLandingRedirectCoordinator.test.mjs
```

Expected: 三个命令均退出码 `0`，分别输出资源树、ROI 导航和落地重定向测试的成功日志。

- [ ] **Step 7: 提交固定入口交互**

```powershell
git add -- frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
git commit -m "功能：完善ROI固定入口交互"
```

---

### Task 3: 完成 ROI 和推荐看板回归验证

**Files:**
- Verify: `frontend/src/views/dashboard/common/ResourceTree.vue`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs`
- Verify: `frontend/src/views/dashboard/roi/*.test.mjs`
- Verify: `frontend/src/stores/roiDashboard.behavior.test.mjs`
- Verify: `frontend/src/stores/roiRequestCoordinator.test.mjs`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.set-default-copy.test.mjs`
- Verify: `frontend/src/views/dashboard/common/ResourceTree.copy-default-refresh.test.mjs`

**Interfaces:**
- Consumes: Task 1 的嵌套树和排序隔离、Task 2 的固定入口路由。
- Produces: 测试、类型检查、生产构建和本地手工验收证据；本任务不新增业务接口。

- [ ] **Step 1: 运行资源树及全部 ROI 前端回归测试**

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

Expected: 所有命令退出码 `0`；普通推荐看板复制测试、ROI 导航、面板、图表、SQL 编辑器和 Store 测试全部输出成功日志。

- [ ] **Step 2: 运行前端类型检查和生产构建**

Run:

```powershell
Set-Location frontend
npm run build
```

Expected: `vue-tsc -b` 与 `vite build` 均成功，进程退出码 `0`。若构建只造成 `frontend/auto-imports.d.ts` 索引换行抖动且内容无业务变化，不得把该文件加入提交。

- [ ] **Step 3: 检查补丁质量和工作区边界**

Run:

```powershell
Set-Location ..
git diff --check
git status --short
git diff -- frontend/src/views/dashboard/common/ResourceTree.vue frontend/src/views/dashboard/common/ResourceTree.roi.test.mjs
```

Expected: `git diff --check` 无输出；状态中不包含意外的后端、迁移、ROI API 或用户未跟踪文件变更。

- [ ] **Step 4: 启动或确认完整本地四服务栈**

如本地服务未运行，按仓库标准命令启动：

```powershell
.\tools\stack-local.ps1 -Action start -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
$runtimeRoot = Join-Path (Resolve-Path '.').Path '.codex-runtime'
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath 'C:\Windows\System32\cmd.exe' -WorkingDirectory (Join-Path (Resolve-Path '.').Path 'frontend') -ArgumentList '/c','npm run dev' -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend-5173.current.out.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend-5173.current.err.log') -WindowStyle Hidden
}
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: API `8000`、MCP `8001`、前端 `5173` 和一个使用本地独立队列的 Worker 均处于运行状态；同时核对运行配置中的 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

- [ ] **Step 5: 在浏览器执行手工验收**

打开 `http://127.0.0.1:5173/#/dashboard/index`，使用具备 ROI 权限的工作空间逐项验证：

```text
1. 顶层只显示“推荐看板”和“我的看板”，不再显示并列的“ROI 看板”。
2. “推荐看板”末尾显示可展开的固定“ROI 看板”。
3. 固定入口菜单只有新建下属看板和排序编辑，不出现删除、重命名、复制或移出推荐看板。
4. 展开入口可看到全部 ROI 子看板，点击子看板后 URL 含 dashboardMode=roi 和真实 resourceId。
5. 点击固定入口时保持当前有效 ROI 子看板；从普通看板点击时进入第一个 ROI 子看板。
6. 删除一个 ROI 子看板后入口仍存在，剩余子看板可继续访问。
7. 普通推荐看板的复制到我的看板、移出推荐看板和排序功能仍正常。
8. 切换到普通成员账号或无 ROI 权限工作空间后，固定 ROI 入口不可见，直接 ROI 路由仍按现有逻辑重定向。
```

Expected: 八项均通过，页面无重叠、空白区域或控制台新增错误。

- [ ] **Step 6: 汇总验证证据并确认提交边界**

记录 Task 3 Step 1 至 Step 5 的通过结果、构建退出码、四服务状态和八项手工验收结果。运行 `git status --short`，确认功能提交只包含 `ResourceTree.vue` 与 `ResourceTree.roi.test.mjs`；不得创建空提交，也不得暂存 `.superpowers/brainstorm/` 或其它用户改动。如任一验证失败，回到引入该行为的 Task 1 或 Task 2，补充对应的失败测试后重新执行红绿循环。
