import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const previewSource = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')

assert.match(previewSource, /dashboardMode.*roi[\s\S]*RoiDashboardPanel/)
assert.match(previewSource, /if \(dashboardMode === ROI_SCOPE\)[\s\S]*return/)
assert.match(previewSource, /useRoiDashboardStore/)
assert.match(previewSource, /roiDashboardStore\.reset\(\)/)
assert.doesNotMatch(previewSource, /<RoiDashboardPanel[\s\S]*dashboard-id=/)
assert.match(previewSource, /shouldInitializeOrdinaryDashboardCanvas/)
assert.match(previewSource, /resolveRoiPreviewAccessPlan/)
assert.match(previewSource, /canAccessRoiDashboard/)
assert.equal(
  previewSource.match(/<RoiDashboardPanel/g)?.length,
  1,
  '授权期间必须复用同一个 ROI 页面实例，避免路由后首图 editorState 写入已卸载实例'
)
assert.match(
  previewSource,
  /<RoiDashboardPanel[\s\S]*v-if="canAccessRoiDashboardMode"[\s\S]*v-show="isAuthorizedRoiDashboardMode"/
)
assert.match(previewSource, /createRoiLandingRedirectCoordinator/)
assert.match(previewSource, /runRoiLandingRedirect/)
assert.match(previewSource, /userStore\.getTenantId/)
assert.doesNotMatch(
  previewSource,
  /const redirectUnauthorizedRoi = async \(\) => \{[\s\S]*?if \(resolvingDashboardTarget\.value\) return/
)

const unauthorizedRedirect = previewSource.match(
  /const redirectUnauthorizedRoi = async \(\) => \{([\s\S]*?)\n\}/
)
assert.ok(unauthorizedRedirect, '未授权 ROI 重定向入口必须存在')
assert.match(unauthorizedRedirect[1], /resolveBusinessDashboardLandingTarget\(userStore\)/)
assert.match(unauthorizedRedirect[1], /currentRoiLandingSnapshot\(\)/)
assert.match(unauthorizedRedirect[1], /roiLandingRedirectCoordinator\.redirect/)

const routeWatchStart = previewSource.search(
  /routeDashboardId\.value,\s*routeDashboardMode\.value,\s*canAccessRoiDashboardMode\.value,\s*currentTenantId\.value/
)
const routeWatchEnd = previewSource.indexOf('{ immediate: true }', routeWatchStart)
const routeWatch = previewSource.slice(routeWatchStart, routeWatchEnd)
assert.ok(routeWatchStart >= 0 && routeWatchEnd > routeWatchStart, 'ROI 路由 watcher 必须存在')
assert.ok(
  routeWatch.indexOf('if (!props.defaultMode && accessPlan.redirectToLanding)') <
    routeWatch.indexOf('loadCanvasData({ id: resourceId, dashboardScope: dashboardMode })'),
  '未授权 ROI 必须在普通看板加载前重定向并 return'
)
assert.ok(
  routeWatch.indexOf('invalidateRoiLandingRedirect()') <
    routeWatch.indexOf('loadCanvasData({ id: resourceId, dashboardScope: dashboardMode })'),
  '合法路由或获得授权后必须先让旧 ROI landing 失效'
)

const beforeMount = previewSource.match(/onBeforeMount\(\(\) => \{([\s\S]*?)\n\}\)/)
assert.ok(beforeMount, '挂载初始化入口必须存在')
assert.ok(
  beforeMount[1].indexOf('shouldInitializeOrdinaryDashboardCanvas(') <
    beforeMount[1].indexOf('dashboardStore.canvasDataInit()'),
  '普通画布初始化前必须先判断当前是否为 ROI 路由'
)

const loadCanvasData = previewSource.match(
  /const loadCanvasData = \(params: any\) => \{([\s\S]*?)\n\}/
)
assert.ok(loadCanvasData, '普通看板加载入口必须存在')
assert.ok(
  loadCanvasData[1].indexOf('if (dashboardMode === ROI_SCOPE)') <
    loadCanvasData[1].indexOf('load_resource_prepare('),
  'ROI 分流必须早于普通看板 load_resource/default_load 路径'
)
