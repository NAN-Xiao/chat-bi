# AI 看板标签页级工作空间上下文 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前工作空间从跨标签页共享状态改为标签页级原子上下文，确保 AI 看板切换工作空间时请求租户、数据源、组件状态和缓存始终属于同一个上下文。

**Architecture:** 新增一个不依赖 Vue 的工作空间状态机核心及一个 Vue/sessionStorage 适配层，请求入口同步捕获状态机快照，响应按快照校验并静默拒绝旧上下文结果。用户 Store 负责一次完整的 latest-wins 切换事务，数据源、Agent、Data Skills 和页面只消费 `ready` 上下文，不改变后端权限边界。

**Tech Stack:** Vue 3、Pinia 3、TypeScript 5.7、Axios 1.8、Node.js `node:test`、Vite 6。

## Global Constraints

- Token、用户身份继续保存在 `localStorage`；活动工作空间 ID 只保存在 `sessionStorage`。
- 后端租户/数据源权限、数据库、AI Worker、SQL 生成流程不修改。
- 不重试或吞掉当前上下文的真实 401/403，不自动替换数据源，不引入跨租户回退。
- 平台工作空间代理继续使用其独立 `sessionStorage` 上下文和专用请求头，优先级高于普通工作空间。
- 旧 AI 任务可在原租户继续执行，但切换后的页面不能消费其响应。
- 所有生产代码遵循红-绿-重构；提交信息使用中文。

---

## File Map

- Create `frontend/src/utils/workspaceContextCore.ts`: 纯 TypeScript 状态机、事务、快照及过期错误。
- Create `frontend/src/utils/workspaceContext.ts`: Vue 响应式状态与 `sessionStorage` 适配，清理旧租户本地缓存。
- Create `frontend/src/utils/workspaceContextCore.test.mjs`: 双标签、latest-wins、回滚和请求快照单元测试。
- Modify `frontend/src/utils/request.ts`: 同步捕获普通/启动/显式切换请求快照，响应与流式请求校验。
- Modify `frontend/src/api/login.ts`: `AuthApi.info(config?)` 支持启动和切换验证策略。
- Modify `frontend/src/api/datasource.ts`: `accessibleList(config?)` 支持切换事务显式租户。
- Modify `frontend/src/stores/user.ts`: 拆分用户 DTO 请求/应用，执行原子切换和失败恢复。
- Modify `frontend/src/stores/datasourceContext.ts`: 按事务租户加载并丢弃旧结果。
- Modify `frontend/src/components/custom-agent/AgentSelector.vue`: ready 门禁、加载序号、租户缓存键。
- Modify `frontend/src/components/data-skill/DataSkillSelector.vue`: ready 门禁、加载序号、租户缓存键。
- Modify `frontend/src/components/layout/{ProjectSelector,Person,MenuItem,LayoutDsl}.vue`: 删除重复切换编排，只调用统一事务。
- Modify `frontend/src/router/watch.ts`: 标签页启动恢复和工作空间管理返回使用统一事务。
- Modify `frontend/src/views/account/workspaces/MyWorkspaces.vue`: 删除重复切换编排并显式处理无活动空间。
- Modify `frontend/src/views/chat/index.vue`: 直接绑定状态机 phase，并在过期错误时保持静默。
- Modify `frontend/src/views/chat/index.workspace-switch.test.mjs`: 覆盖统一 switching 门禁和事件顺序。
- Create `frontend/src/utils/workspaceRequestContext.test.mjs`: 请求入口快照、响应过期和流式快照回归测试。
- Create `frontend/src/components/workspaceSelectors.test.mjs`: 选择器门禁、序号和缓存边界静态回归测试。

### Task 1: 工作空间状态机核心与标签页存储

**Files:**
- Create: `frontend/src/utils/workspaceContextCore.ts`
- Create: `frontend/src/utils/workspaceContext.ts`
- Test: `frontend/src/utils/workspaceContextCore.test.mjs`

**Interfaces:**
- Produces: `WorkspacePhase`, `WorkspaceContextState`, `WorkspaceRequestSnapshot`, `WorkspaceSwitchTransaction`, `WorkspaceContextStaleError`。
- Produces: `createWorkspaceContextCore(storage, state?)`，返回 `restore()`, `captureRequest(mode, tenantId?, switchId?)`, `assertConsumable(snapshot, responseTenantId?)`, `beginSwitch(targetTenantId)`, `commitSwitch(transaction)`, `finishSwitch(transaction)`, `rollbackSwitch(transaction)`, `completeBootstrap(serverTenantId)`, `clear()`。
- Produces: singleton exports `workspaceContext`, `workspaceContextState`, `isWorkspaceReady`, `isWorkspaceSwitching`。

- [ ] **Step 1: Write the failing state-machine tests**

```js
test('两个 sessionStorage 适配器拥有独立活动租户', () => {
  const tabA = createWorkspaceContextCore(memoryStorage())
  const tabB = createWorkspaceContextCore(memoryStorage())
  tabA.completeBootstrap('tenant-a')
  tabB.completeBootstrap('tenant-b')
  assert.equal(tabA.state.activeTenantId, 'tenant-a')
  assert.equal(tabB.state.activeTenantId, 'tenant-b')
})

test('A 到 B 到 C 只允许 C 提交', () => {
  const context = readyContext('A')
  const toB = context.beginSwitch('B')
  const toC = context.beginSwitch('C')
  assert.equal(context.commitSwitch(toB), false)
  assert.equal(context.commitSwitch(toC), true)
  assert.equal(context.finishSwitch(toC), true)
  assert.deepEqual(context.state, {
    activeTenantId: 'C', pendingTenantId: '', phase: 'ready', epoch: 2, switchId: 2,
  })
})

test('旧快照在切换开始后抛出 WorkspaceContextStaleError', () => {
  const context = readyContext('A')
  const snapshot = context.captureRequest('normal')
  context.beginSwitch('B')
  assert.throws(() => context.assertConsumable(snapshot, 'A'), WorkspaceContextStaleError)
})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --experimental-strip-types --test src/utils/workspaceContextCore.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `workspaceContextCore.ts`.

- [ ] **Step 3: Implement the minimal core and adapter**

```ts
export type WorkspacePhase = 'bootstrapping' | 'ready' | 'switching'

export interface WorkspaceContextState {
  activeTenantId: string
  pendingTenantId: string
  phase: WorkspacePhase
  epoch: number
  switchId: number
}

export interface WorkspaceRequestSnapshot {
  tenantId: string
  epoch: number
  phase: WorkspacePhase
  mode: 'normal' | 'bootstrap' | 'switch' | 'none'
  switchId?: number
}

export class WorkspaceContextStaleError extends Error {
  readonly code = 'WORKSPACE_CONTEXT_STALE'
}
```

The core must persist only `activeTenantId`, increment `epoch` at every `beginSwitch`, compare both `epoch` and `switchId` for explicit switch responses, keep phase `switching` between commit and datasource completion, and leave earlier transaction results untouched.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cd frontend && node --experimental-strip-types --test src/utils/workspaceContextCore.test.mjs`

Expected: all tests PASS, zero failures.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/utils/workspaceContextCore.ts frontend/src/utils/workspaceContext.ts frontend/src/utils/workspaceContextCore.test.mjs
git commit -m "新增标签页级工作空间状态机"
```

### Task 2: 请求入口快照与响应隔离

**Files:**
- Modify: `frontend/src/utils/request.ts`
- Modify: `frontend/src/api/login.ts`
- Test: `frontend/src/utils/workspaceRequestContext.test.mjs`

**Interfaces:**
- Consumes: `workspaceContext.captureRequest(...)`, `workspaceContext.assertConsumable(...)`, `WorkspaceContextStaleError`。
- Produces: `RequestOptions.workspaceMode?: 'normal' | 'bootstrap' | 'switch' | 'none'`, `workspaceTenantId?: string`, `workspaceSwitchId?: number`。
- Produces: internal `FullRequestConfig.__workspaceSnapshot?: WorkspaceRequestSnapshot` captured inside `HttpService.request()` before Axios interceptor scheduling。

- [ ] **Step 1: Write failing request-source regression tests**

```js
test('request 在同步入口捕获工作空间且拦截器不读取旧 localStorage 租户', () => {
  assert.match(source, /captureWorkspaceRequestConfig\(config\)/)
  assert.doesNotMatch(interceptorSource, /wsCache\.get\('user\.tenantId'\)/)
  assert.doesNotMatch(source, /syncTenantContextFromResponse/)
})

test('成功和失败响应都先校验工作空间快照', () => {
  assert.match(source, /assertWorkspaceResponseConsumable\(response\.config, response\)/)
  assert.match(source, /assertWorkspaceResponseConsumable\(config, error\.response\)/)
  assert.match(source, /isWorkspaceContextStaleError/)
})

test('fetchStream 在 refreshCertificate await 前捕获快照', () => {
  assert.ok(source.indexOf('captureWorkspaceRequest') < source.indexOf('await assistantStore.refreshCertificate'))
})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test src/utils/workspaceRequestContext.test.mjs`

Expected: FAIL because request snapshot helpers are absent and response synchronization still exists.

- [ ] **Step 3: Implement synchronous capture and validation**

```ts
export interface RequestOptions {
  silent?: boolean
  rawResponse?: boolean
  customError?: boolean
  retryCount?: number
  workspaceMode?: WorkspaceRequestSnapshot['mode']
  workspaceTenantId?: string
  workspaceSwitchId?: number
}

public request<T = any>(config: FullRequestConfig): Promise<T> {
  const capturedConfig = captureWorkspaceRequestConfig(config)
  return this.instance.request({ cancelToken: this.cancelTokenSource.token, ...capturedConfig })
}
```

The interceptor must only add auth, assistant, locale and delegate headers; it must preserve the already captured tenant header. The success interceptor and error interceptor must reject stale context before business handling or Toasts. `fetchStream()` must capture before its first `await`, validate the returned `Response`, and keep the platform delegate and assistant bypass paths unchanged.

- [ ] **Step 4: Run focused tests and type check**

Run: `cd frontend && node --test src/utils/workspaceRequestContext.test.mjs && npx vue-tsc -b --pretty false`

Expected: request tests PASS and TypeScript exits 0.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/utils/request.ts frontend/src/api/login.ts frontend/src/utils/workspaceRequestContext.test.mjs
git commit -m "隔离工作空间请求与过期响应"
```

### Task 3: 用户与数据源原子切换事务

**Files:**
- Modify: `frontend/src/stores/user.ts`
- Modify: `frontend/src/stores/datasourceContext.ts`
- Modify: `frontend/src/api/datasource.ts`
- Test: `frontend/src/stores/workspaceSwitchTransaction.test.mjs`

**Interfaces:**
- Produces: `UserStore.requestInfo(config?) -> Promise<UserInfoDto>` and `UserStore.applyInfo(dto) -> void`。
- Produces: `UserStore.switchTenant(tenantId) -> Promise<boolean>` as the only ordinary switch coordinator。
- Produces: `DatasourceContextStore.loadDatasources(force?, options?: { tenantId?: string; workspaceSwitchId?: number })`。

- [ ] **Step 1: Write failing transaction tests**

```js
test('switchTenant 验证成功前不调用 applyInfo 或 setTenant', () => {
  assert.ok(source.indexOf('const userInfo = await this.requestInfo') < source.indexOf('this.applyInfo(userInfo)'))
  assert.match(source, /workspaceContext\.commitSwitch\(transaction\)/)
})

test('数据源加载携带显式事务租户并校验最新 switchId', () => {
  assert.match(datasourceSource, /workspaceTenantId: requestTenantId/)
  assert.match(datasourceSource, /workspaceSwitchId: options\?\.workspaceSwitchId/)
  assert.match(datasourceSource, /workspaceContext\.isCurrentSwitch/)
})

test('工作空间字段不再写入 localStorage', () => {
  assert.doesNotMatch(source, /wsCache\.set\('user\.tenantId'/)
  assert.doesNotMatch(source, /wsCache\.set\('user\.workspaceStatus'/)
})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test src/stores/workspaceSwitchTransaction.test.mjs`

Expected: FAIL because `info()` directly mutates state, the switch is non-atomic, and workspace fields use local storage.

- [ ] **Step 3: Implement bootstrap, switch, rollback and datasource loading**

```ts
async switchTenant(tenantId: string | number): Promise<boolean> {
  const transaction = workspaceContext.beginSwitch(String(tenantId || ''))
  if (!transaction) return false
  const previous = captureWorkspaceStoreSnapshot(this, datasourceContext.datasourceId)
  emitWorkspaceContextChange({ tenantId: transaction.targetTenantId, phase: 'changing' })
  clearWorkspaceSelectorCaches()
  datasourceContext.clear(false)
  try {
    const userInfo = await this.requestInfo(workspaceSwitchRequestOptions(transaction))
    assertUserInfoTenant(userInfo, transaction.targetTenantId)
    if (!workspaceContext.commitSwitch(transaction)) return false
    this.applyInfo(userInfo)
    await datasourceContext.loadDatasources(true, switchDatasourceLoadOptions(transaction))
    if (!workspaceContext.finishSwitch(transaction)) return false
    emitDatasourceAndWorkspaceChanged(transaction.targetTenantId)
    return true
  } catch (error) {
    if (!workspaceContext.isCurrentSwitch(transaction)) return false
    restoreWorkspaceStoreSnapshot(this, previous)
    workspaceContext.rollbackSwitch(transaction)
    await datasourceContext.loadDatasources(true)
    datasourceContext.setDatasourceById(previous.datasourceId, false)
    emitDatasourceAndWorkspaceChanged(previous.tenantId)
    throw error
  }
}
```

`info()` must use bootstrap mode, explicitly warn if saved tenant is invalid and the server resolves another tenant, then commit the server tenant and apply the DTO. Empty accessible datasource lists are a valid ready result; request failure triggers rollback.

- [ ] **Step 4: Run transaction tests and type check**

Run: `cd frontend && node --test src/stores/workspaceSwitchTransaction.test.mjs && npx vue-tsc -b --pretty false`

Expected: transaction tests PASS and TypeScript exits 0.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/stores/user.ts frontend/src/stores/datasourceContext.ts frontend/src/api/datasource.ts frontend/src/stores/workspaceSwitchTransaction.test.mjs
git commit -m "实现工作空间原子切换事务"
```

### Task 4: Agent 与 Data Skills 的 ready 门禁

**Files:**
- Modify: `frontend/src/components/custom-agent/AgentSelector.vue`
- Modify: `frontend/src/components/data-skill/DataSkillSelector.vue`
- Modify: `frontend/src/utils/requestDedupe.ts`
- Test: `frontend/src/components/workspaceSelectors.test.mjs`

**Interfaces:**
- Consumes: `workspaceContextState.activeTenantId`, `workspaceContextState.phase`。
- Produces: cache keys `${prefix}${tenantId}|${datasourceId}|${targetScope}|...` and monotonically increasing local `loadSequence` guards。
- Produces: `clearWorkspaceSelectorCaches()` clearing only `agent-selector:` and `data-skill-selector:` entries.

- [ ] **Step 1: Write failing selector tests**

```js
test('两个选择器仅在 ready 且有数据源时请求', () => {
  for (const source of [agentSource, skillSource]) {
    assert.match(source, /workspaceContextState\.phase !== 'ready'/)
    assert.match(source, /!datasourceIdValue\.value/)
  }
})

test('缓存键同时包含租户、数据源和目标作用域', () => {
  assert.match(agentSource, /activeTenantId.*datasourceIdValue.*targetScope/s)
  assert.match(skillSource, /activeTenantId.*datasourceIdValue.*targetScope/s)
})

test('只有最新加载序号可以更新列表与 loading', () => {
  for (const source of [agentSource, skillSource]) {
    assert.match(source, /const loadId = \+\+loadSequence/)
    assert.match(source, /if \(loadId !== loadSequence\) return/)
    assert.match(source, /if \(loadId === loadSequence\).*loading\.value = false/s)
  }
})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test src/components/workspaceSelectors.test.mjs`

Expected: FAIL because selectors load during switching and use unscoped cache keys.

- [ ] **Step 3: Add ready gate, tenant cache key and sequence guard**

Both `loadAgents()` and `loadSkills()` must increment sequence before checking the gate, clear visible list when the context is not consumable, capture tenant/datasource/scope before awaiting, and update list/selection/loading only when the captured values and sequence still match.

- [ ] **Step 4: Run selector tests and type check**

Run: `cd frontend && node --test src/components/workspaceSelectors.test.mjs && npx vue-tsc -b --pretty false`

Expected: selector tests PASS and TypeScript exits 0.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/custom-agent/AgentSelector.vue frontend/src/components/data-skill/DataSkillSelector.vue frontend/src/utils/requestDedupe.ts frontend/src/components/workspaceSelectors.test.mjs
git commit -m "隔离工作空间选择器加载与缓存"
```

### Task 5: 统一所有工作空间切换调用点

**Files:**
- Modify: `frontend/src/components/layout/ProjectSelector.vue`
- Modify: `frontend/src/components/layout/Person.vue`
- Modify: `frontend/src/components/layout/MenuItem.vue`
- Modify: `frontend/src/components/layout/LayoutDsl.vue`
- Modify: `frontend/src/router/watch.ts`
- Modify: `frontend/src/views/account/workspaces/MyWorkspaces.vue`
- Modify: `frontend/src/views/chat/index.vue`
- Modify: `frontend/src/views/chat/index.workspace-switch.test.mjs`
- Test: `frontend/src/stores/workspaceSwitchCallsites.test.mjs`

**Interfaces:**
- Consumes: `userStore.switchTenant(tenantId)` as a complete transaction that owns changing/changed events and datasource loading。
- Consumes: `workspaceContextState.phase` for chat UI disabling。

- [ ] **Step 1: Write failing call-site tests**

```js
test('调用点不再重复发送事件或加载数据源', () => {
  for (const file of callsiteSources) {
    assert.doesNotMatch(file.source, /switchTenant[\s\S]{0,300}loadDatasources\(true\)/)
    assert.doesNotMatch(file.source, /emitWorkspaceContextChange[\s\S]{0,300}switchTenant/)
  }
})

test('聊天禁用状态直接来自 workspaceContext phase', () => {
  assert.match(chatSource, /workspaceContextState\.phase === 'switching'/)
})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test src/stores/workspaceSwitchCallsites.test.mjs src/views/chat/index.workspace-switch.test.mjs`

Expected: FAIL because six callers each duplicate event/datasource orchestration and chat keeps a separate switching ref.

- [ ] **Step 3: Replace duplicated orchestration**

Each ordinary caller becomes:

```ts
try {
  await userStore.switchTenant(tenantId)
  await router.push(target)
} catch (error) {
  ElMessage.error(formatRequestErrorMessage(error, '工作空间切换失败'))
}
```

The router startup must restore the singleton before `userStore.info()`. The chat page must compute switching from `workspaceContextState.phase`; its event handler keeps the view cleanup/abort work but must not independently end switching before datasource completion.

- [ ] **Step 4: Run focused integration tests**

Run: `cd frontend && node --test src/stores/workspaceSwitchCallsites.test.mjs src/views/chat/index.workspace-switch.test.mjs`

Expected: all tests PASS, zero failures.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/layout/ProjectSelector.vue frontend/src/components/layout/Person.vue frontend/src/components/layout/MenuItem.vue frontend/src/components/layout/LayoutDsl.vue frontend/src/router/watch.ts frontend/src/views/account/workspaces/MyWorkspaces.vue frontend/src/views/chat/index.vue frontend/src/views/chat/index.workspace-switch.test.mjs frontend/src/stores/workspaceSwitchCallsites.test.mjs
git commit -m "统一工作空间切换调用与页面状态"
```

### Task 6: 完整回归与双标签浏览器验证

**Files:**
- Modify only if a verified regression requires a scoped fix in files listed above.

**Interfaces:**
- Verifies all prior interfaces without widening production behavior.

- [ ] **Step 1: Run all workspace-focused tests**

Run: `cd frontend && node --experimental-strip-types --test src/utils/workspaceContextCore.test.mjs src/utils/workspaceRequestContext.test.mjs src/stores/workspaceSwitchTransaction.test.mjs src/components/workspaceSelectors.test.mjs src/stores/workspaceSwitchCallsites.test.mjs src/views/chat/index.workspace-switch.test.mjs`

Expected: all tests PASS, zero failures.

- [ ] **Step 2: Install dependencies if absent and build**

Run: `cd frontend && npm install && npm run build`

Expected: `vue-tsc -b` and `vite build` exit 0.

- [ ] **Step 3: Verify the four-service local stack before browser QA**

Run: `powershell -ExecutionPolicy Bypass -File .\tools\stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`

Run: `Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess`

Expected: frontend 5173, API 8000, MCP 8001 and one local Worker are reported; local LLM settings resolve to `LLM_REQUEST_TIMEOUT=120`, `LLM_TASK_MAX_WAIT_SECONDS=900`, `LLM_MAX_RETRIES=1`.

- [ ] **Step 4: Browser regression with two tabs**

Use the in-app browser to keep one tab in 修仙 and one tab in Flam. In each tab submit an AI 看板 question, switch only one tab twice while the other continues, and inspect requests to confirm each request's `X-SHUZHI-TENANT-ID` matches that tab's selected datasource. Refresh both tabs and confirm each restores its own workspace. Confirm stale requests produce no generic error Toast while a deliberate current-context unauthorized datasource request still shows a 403 message.

- [ ] **Step 5: Final diff and commit**

Run: `git diff --check && git status --short && git diff --stat origin/release/release_1.0.0...HEAD`

Expected: no whitespace errors, only planned frontend/spec/plan changes, and no credentials or generated build artifacts staged.

```powershell
git add <only-the-verified-files>
git commit -m "完成标签页工作空间切换回归"
```
