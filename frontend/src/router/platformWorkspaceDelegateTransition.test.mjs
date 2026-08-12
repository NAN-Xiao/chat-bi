import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const routerSource = read('./watch.ts')
const layoutSource = read('../components/layout/LayoutDsl.vue')
const userSource = read('../stores/user.ts')

test('进入平台代理空间后不恢复之前记住的业务工作空间', () => {
  const restoreStart = routerSource.indexOf('const restoreBusinessTenantAfterWorkspaceAdmin')
  const restoreSource = routerSource.slice(
    restoreStart,
    routerSource.indexOf('\n}\n\nexport const watchRouter', restoreStart)
  )

  assert.match(restoreSource, /isPlatformWorkspaceDelegateSession\(\)/)
  assert.match(
    restoreSource,
    /if \(isPlatformWorkspaceDelegateSession\(\)\) return[\s\S]*?getRememberedBusinessTenant\(\)/
  )
  assert.match(
    routerSource,
    /if \(shouldEnterDelegate\) \{[\s\S]*?clearRememberedBusinessTenant\(\)[\s\S]*?\}/
  )
})

test('退出平台代理身份时当前系统页面不会因 shell 变化而重新挂载', () => {
  assert.match(
    layoutSource,
    /const workspaceScopedViewKey = computed\(\(\) =>[\s\S]*?showSysmenu\.value[\s\S]*?workspace-admin:\$\{workspaceAdminViewVersion\.value\}:\$\{route\.path\}/
  )
  assert.doesNotMatch(
    layoutSource,
    /workspaceScopedViewKey = computed\(\(\) =>[\s\S]*?showTopWorkspaceAdminSidebar\.value[\s\S]*?route\.path/
  )
})

test('退出按钮只发起路由转换且守卫统一完成身份退出', () => {
  const exitHandlerStart = layoutSource.indexOf('const exitPlatformWorkspaceDelegate = async () =>')
  const exitHandlerSource = layoutSource.slice(
    exitHandlerStart,
    layoutSource.indexOf('\n}\n\nconst toProjectList', exitHandlerStart)
  )

  assert.match(exitHandlerSource, /await router\.push\(PLATFORM_ADMIN_HOME\)/)
  assert.doesNotMatch(exitHandlerSource, /userStore\.exitPlatformWorkspaceDelegate/)
  assert.match(
    routerSource,
    /if \(shouldExitDelegate\) \{[\s\S]*?await userStore\.exitPlatformWorkspaceDelegate\(\)[\s\S]*?\} else \{[\s\S]*?await userStore\.info\(\)/
  )
  assert.match(userSource, /async exitPlatformWorkspaceDelegate\(\): Promise<void>/)
})
