import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')

assert.doesNotMatch(source, /RoiDashboardPanel|useRoiDashboardStore/)
assert.doesNotMatch(source, /canAccessRoiDashboard|resolveRoiPreviewAccessPlan/)
assert.doesNotMatch(source, /roiLandingRedirect|dashboard\/roi/)
assert.doesNotMatch(source, /<RoiDashboardPanel/)
assert.match(source, /isUnsupportedDashboardMode/)
assert.match(source, /resolveBusinessDashboardLandingTarget/)
assert.match(source, /createDashboardLandingRedirectCoordinator/)
assert.match(source, /dashboardLandingRedirect\.redirect/)
assert.match(source, /dashboardLandingRedirect\.invalidate\(\)/)
assert.match(
  source,
  /firstDashboardMode\(route\.query\.dashboardMode\)/,
  '连续切换不同的无效 dashboardMode 时必须重新触发 watcher'
)
assert.doesNotMatch(
  source,
  /if \(resolvingDashboardTarget\.value\) return/,
  '连续无效路由必须启动最新重定向，不能因上一请求仍在解析而丢弃'
)

const workspaceChangeHandler = source.match(
  /useEmitt\(\{\s*name: WORKSPACE_CONTEXT_CHANGE_EVENT,\s*callback: \(\) => \{([\s\S]*?)\}\s*,?\s*\}\)/
)
assert.ok(workspaceChangeHandler, '必须保留工作空间切换处理')
assert.match(
  workspaceChangeHandler[1],
  /dashboardLandingRedirect\.invalidate\(\)/,
  '工作空间切换即使 URL 不变，也必须使旧 landing 解析结果失效'
)

console.log('SQPreviewShow no-ROI tests passed')
