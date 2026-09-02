import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const appSource = read('../App.vue')
const callsiteSources = [
  ['ProjectSelector.vue', read('../components/layout/ProjectSelector.vue')],
  ['Person.vue', read('../components/layout/Person.vue')],
  ['MenuItem.vue', read('../components/layout/MenuItem.vue')],
  ['LayoutDsl.vue', read('../components/layout/LayoutDsl.vue')],
  ['router/watch.ts', read('../router/watch.ts')],
  ['MyWorkspaces.vue', read('../views/account/workspaces/MyWorkspaces.vue')],
]
const userSource = read('./user.ts')
const chatSource = read('../views/chat/index.vue')
const resourceTreeSource = read('../views/dashboard/common/ResourceTree.vue')
const dataDictionarySource = read('../views/system/data-dictionary/DataDictionary.vue')
const distributionIntervalSettingsSource = read(
  '../views/dashboard/common/DistributionIntervalSettings.vue'
)

test('普通切换调用点不再重复加载数据源或发送 changing/changed', () => {
  for (const [name, source] of callsiteSources) {
    assert.doesNotMatch(
      source,
      /switchTenant[\s\S]{0,320}loadDatasources\(true\)/,
      `${name} still reloads datasources outside the transaction`
    )
    assert.doesNotMatch(
      source,
      /emitWorkspaceContextChange\([^)]*changing[^)]*\)[\s\S]{0,240}switchTenant/,
      `${name} still emits changing outside the transaction`
    )
  }
})

test('消息提示默认展示时长由根配置统一为 3000ms', () => {
  assert.match(appSource, /const messageConfig = \{ duration: 3000 \}/)
  assert.match(appSource, /<el-config-provider[^>]*:message="messageConfig"/)

  for (const name of ['ProjectSelector.vue', 'Person.vue']) {
    const source = callsiteSources.find(([callsiteName]) => callsiteName === name)[1]
    assert.match(
      source,
      /ElMessage\.success\(t\('common\.switch_success'\)\)/,
      `${name} should use the globally configured message duration`
    )
    assert.doesNotMatch(source, /duration\s*:/)
  }

  assert.match(dataDictionarySource, /import \{ ElMessage \} from 'element-plus-secondary'/)
  assert.match(
    distributionIntervalSettingsSource,
    /import \{ ElMessage \} from 'element-plus-secondary'/
  )
})

test('退出最后一个工作空间也由 User Store 统一处理', () => {
  assert.match(userSource, /async clearActiveTenant\(\): Promise<void>/)
  const myWorkspaces = callsiteSources.find(([name]) => name === 'MyWorkspaces.vue')[1]
  assert.match(myWorkspaces, /await userStore\.clearActiveTenant\(\)/)
  assert.doesNotMatch(myWorkspaces, /userStore\.setTenant\(null\)/)
})

test('退出当前工作空间后先废止旧上下文再切换剩余空间', () => {
  const myWorkspaces = callsiteSources.find(([name]) => name === 'MyWorkspaces.vue')[1]
  const activeLeave = myWorkspaces.slice(
    myWorkspaces.indexOf("if (tenantId === String(userStore.getTenantId || ''))"),
    myWorkspaces.indexOf('} else {', myWorkspaces.indexOf("if (tenantId === String(userStore.getTenantId || ''))"))
  )
  const clearIndex = activeLeave.indexOf('await userStore.clearActiveTenant()')
  const switchIndex = activeLeave.indexOf('await userStore.switchTenant(nextTenant.id)')

  assert.ok(clearIndex > 0)
  assert.ok(switchIndex > clearIndex)
})

test('聊天切换状态直接来自 WorkspaceContext 且不重复加载数据源', () => {
  assert.match(
    chatSource,
    /const workspaceContextSwitching = computed\(\(\) => workspaceContextState\.phase === 'switching'\)/
  )
  const eventHandler = chatSource.slice(
    chatSource.indexOf('name: WORKSPACE_CONTEXT_CHANGE_EVENT'),
    chatSource.indexOf('const recommendQuestionRef')
  )
  assert.doesNotMatch(eventHandler, /datasourceContext\.loadDatasources/)
  assert.match(eventHandler, /if \(event\?\.phase === 'changed'\)[\s\S]*getChatList\(\)/)
})

test('Dashboard 资源树在 changed 事件中直接使用已加载的数据源', () => {
  const eventHandler = resourceTreeSource.slice(
    resourceTreeSource.indexOf('name: WORKSPACE_CONTEXT_CHANGE_EVENT'),
    resourceTreeSource.indexOf('watch(', resourceTreeSource.indexOf('name: WORKSPACE_CONTEXT_CHANGE_EVENT'))
  )
  assert.doesNotMatch(eventHandler, /datasourceContext\.loadDatasources/)
  assert.match(eventHandler, /if \(event\?\.phase === 'changed'\)[\s\S]*getTree\(\)/)
})
