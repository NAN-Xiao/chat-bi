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
assert.match(previewSource, /<RoiDashboardPanel[\s\S]*dashboard-id="routeDashboardId"/)
assert.match(previewSource, /shouldInitializeOrdinaryDashboardCanvas/)
assert.match(previewSource, /resolveRoiPreviewAccessPlan/)
assert.match(previewSource, /canAccessRoiDashboard/)
assert.match(previewSource, /v-if="isAuthorizedRoiDashboardMode"/)

const unauthorizedRedirect = previewSource.match(
  /const redirectUnauthorizedRoi = async \(\) => \{([\s\S]*?)\n\}/
)
assert.ok(unauthorizedRedirect, '未授权 ROI 重定向入口必须存在')
assert.match(unauthorizedRedirect[1], /resolveBusinessDashboardLandingTarget\(userStore\)/)
assert.match(unauthorizedRedirect[1], /!canAccessRoiDashboard\(userStore\)/)

const routeWatchStart = previewSource.indexOf(
  '() => [routeDashboardId.value, routeDashboardMode.value, canAccessRoiDashboardMode.value]'
)
const routeWatchEnd = previewSource.indexOf('{ immediate: true }', routeWatchStart)
const routeWatch = previewSource.slice(routeWatchStart, routeWatchEnd)
assert.ok(routeWatchStart >= 0 && routeWatchEnd > routeWatchStart, 'ROI 路由 watcher 必须存在')
assert.ok(
  routeWatch.indexOf('if (!props.defaultMode && accessPlan.redirectToLanding)') <
    routeWatch.indexOf('loadCanvasData({ id: resourceId, dashboardScope: dashboardMode })'),
  '未授权 ROI 必须在普通看板加载前重定向并 return'
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
