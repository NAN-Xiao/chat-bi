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

const loadCanvasData = previewSource.match(
  /const loadCanvasData = \(params: any\) => \{([\s\S]*?)\n\}/
)
assert.ok(loadCanvasData, '普通看板加载入口必须存在')
assert.ok(
  loadCanvasData[1].indexOf('if (dashboardMode === ROI_SCOPE)') <
    loadCanvasData[1].indexOf('load_resource_prepare('),
  'ROI 分流必须早于普通看板 load_resource/default_load 路径'
)
