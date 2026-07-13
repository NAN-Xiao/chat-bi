# 编辑图表默认打开图表配置实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有新建和编辑图表入口在每次打开时默认进入“图表配置”，并请求当前图表的配置元数据。

**Architecture:** 默认行为由 `DashboardSqlEditor` 统一管理，不向父组件新增参数。组件初始状态与每次打开重置状态都使用 `builder`，`initEditor()` 在恢复当前图表状态后显式调用既有 `ensureBuilderSchemaLoaded()`，页签监听继续处理用户手动从 SQL 切回配置的场景。

**Tech Stack:** Vue 3、TypeScript、Node.js `assert` 源码契约测试、Vite、`vue-tsc`

## Global Constraints

- 新建图表、编辑已有图表以及关闭后重开都必须默认进入“图表配置”。
- 不持久化或记忆用户上次选择的页签。
- 不删除、隐藏或改变用户主动切换“SQL 明细”的能力。
- 不改变 AI 生成 SQL 后显式进入“SQL 明细”的现有行为。
- 图表配置与 SQL 明细继续使用 `v-if` 独立懒挂载。
- 不新增父组件默认页签参数，不增加兼容回退。

---

## 文件结构

- 修改 `frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs`：定义默认页签与每次打开加载配置元数据的回归契约。
- 修改 `frontend/src/views/dashboard/common/DashboardSqlEditor.vue`：实现统一默认页签，并在初始化完成后触发现有元数据加载入口。

### Task 1: 编辑器默认页签与重开加载

**Files:**
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs:8-46`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:231-243`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:1335-1347`
- Modify: `frontend/src/views/dashboard/common/DashboardSqlEditor.vue:3827-3888`
- Test: `frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs`

**Interfaces:**
- Consumes: 现有 `resetSqlBuilderState(): void`、`ensureBuilderSchemaLoaded(): void`、`initEditor(): void`。
- Produces: `sqlBuilder.activeTab` 打开时稳定为 `'builder'`，且每次 `initEditor()` 都为当前 `viewInfo` 触发一次配置元数据加载。

- [ ] **Step 1: 先修改回归测试，表达新行为**

在 `DashboardSqlEditor.lazy-open.test.mjs` 中保留现有函数截取逻辑，新增初始状态断言，并替换旧的 SQL 默认页签断言：

```js
assert.match(
  source,
  /const sqlBuilder = reactive\(\{\s*activeTab: 'builder'/,
  '编辑图表首次打开时应默认进入图表配置'
)
assert.match(
  resetBuilderMatch[1],
  /sqlBuilder\.activeTab = 'builder'/,
  '每次打开编辑图表都应重置到图表配置'
)
assert.match(
  initEditorMatch[1],
  /restoreSqlBuilderState\([\s\S]*ensureBuilderSchemaLoaded\(\)/,
  '编辑器恢复当前图表状态后应主动请求图表配置元数据，保证关闭后重开仍会加载'
)
assert.doesNotMatch(
  initEditorMatch[1],
  /loadSchemaTables\(\)/,
  '编辑器初始化应复用图表配置元数据加载入口，不应绕过请求有效性校验'
)
```

- [ ] **Step 2: 运行定向测试并确认按预期失败**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs
```

Expected: FAIL，首个失败信息为“编辑图表首次打开时应默认进入图表配置”，现有源码仍包含 `activeTab: 'sql'`。

- [ ] **Step 3: 实现最小业务改动**

在 `DashboardSqlEditor.vue` 中把初始状态和打开重置状态改为 `builder`：

```diff
 const sqlBuilder = reactive({
-  activeTab: 'sql',
+  activeTab: 'builder',
   timeField: '',

 function resetSqlBuilderState() {
-  sqlBuilder.activeTab = 'sql'
+  sqlBuilder.activeTab = 'builder'
   sqlBuilder.timeField = ''
```

在 `initEditor()` 完成表单、预览和 MCP 状态恢复后调用现有入口：

```diff
  if (hasMcpSource.value) {
    void loadMcpServers().then(() => loadMcpTools())
  } else {
    mcpServers.value = []
    mcpTools.value = []
    mcpFilterOptions.value = {}
  }
+  ensureBuilderSchemaLoaded()
 }
```

调用必须位于当前图表状态恢复完成之后，以便请求读取本次打开对应的 `props.viewInfo`、数据源和租户上下文。

- [ ] **Step 4: 运行定向测试并确认通过**

Run:

```powershell
node frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs
```

Expected: PASS，进程退出码为 `0` 且无错误输出。

- [ ] **Step 5: 运行编辑器相关回归测试**

Run:

```powershell
Get-ChildItem frontend/src/views/dashboard/common/DashboardSqlEditor.*.test.mjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
```

Expected: 所有 `DashboardSqlEditor.*.test.mjs` 进程退出码为 `0`，无断言失败。

- [ ] **Step 6: 运行前端构建检查**

Run:

```powershell
npm run build
```

Working directory: `frontend`

Expected: `vue-tsc -b` 与 `vite build` 均成功，命令退出码为 `0`。

- [ ] **Step 7: 检查变更并提交**

Run:

```powershell
git diff --check
git diff -- frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs
git status --short
```

确认仅包含本计划要求的默认页签、初始化加载和测试变更后提交：

```powershell
git add frontend/src/views/dashboard/common/DashboardSqlEditor.vue frontend/src/views/dashboard/common/DashboardSqlEditor.lazy-open.test.mjs
git commit -m "修复编辑图表默认打开图表配置"
```

Expected: 提交成功，提交仅包含上述两个前端文件。
