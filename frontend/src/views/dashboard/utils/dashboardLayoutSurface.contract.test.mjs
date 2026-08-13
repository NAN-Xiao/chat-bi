import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const utilsDir = dirname(fileURLToPath(import.meta.url))
const dashboardDir = join(utilsDir, '..')
const surfacePath = join(utilsDir, 'dashboardLayoutSurface.ts')
const read = (path) => readFileSync(path, 'utf8')

assert.equal(existsSync(surfacePath), true, '需要共享 DashboardLayoutSurface 类型')
const surfaceSource = read(surfacePath)
const tabSource = read(join(dashboardDir, 'components', 'sq-tab', 'index.vue'))
const previewSource = read(join(dashboardDir, 'preview', 'SQPreview.vue'))
const wrapperSource = read(join(dashboardDir, 'preview', 'SQComponentWrapper.vue'))
const editorSource = read(join(dashboardDir, 'editor', 'DashboardEditor.vue'))
const canvasSource = read(join(dashboardDir, 'canvas', 'CanvasCore.vue'))

assert.match(surfaceSource, /export type DashboardLayoutSurface = 'main' \| 'tab'/)
assert.match(surfaceSource, /DEFAULT_DASHBOARD_LAYOUT_SURFACE[^=]*= 'main'/)
assert.match(tabSource, /<SQPreview[\s\S]*dashboard-layout-surface="tab"[\s\S]*in-tab/)
assert.match(tabSource, /<DashboardEditor[\s\S]*dashboard-layout-surface="tab"[\s\S]*in-tab/)
assert.match(previewSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(previewSource, /<SQComponentWrapper[\s\S]*:dashboard-layout-surface="dashboardLayoutSurface"/)
assert.match(wrapperSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(
  wrapperSource,
  /configItem\?\.component === 'SQView'[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)
assert.match(editorSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(editorSource, /<CanvasCore[\s\S]*:dashboard-layout-surface="dashboardLayoutSurface"/)
assert.match(canvasSource, /dashboardLayoutSurface:[\s\S]*DashboardLayoutSurface/)
assert.match(
  canvasSource,
  /item\.component === 'SQView'[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)
assert.doesNotMatch(wrapperSource, /frameless\s*\?\s*['"]tab['"]/)
const canvasLayoutProps = canvasSource.match(
  /function componentLayoutProps\(item: CanvasItem\) \{([\s\S]*?)\r?\n\}/
)
assert.ok(canvasLayoutProps, 'CanvasCore 需要仅面向 SQView 的 surface props helper')
assert.match(
  canvasLayoutProps[1],
  /item\.component !== 'SQView'\) return \{\}[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)
assert.doesNotMatch(canvasLayoutProps[1], /canvasId|inTab|classList|closest/)

const wrapperExtraProps = wrapperSource.match(
  /const componentExtraProps = computed\(\(\) => \{([\s\S]*?)\r?\n\}\)/
)
assert.ok(wrapperExtraProps, 'SQComponentWrapper 需要仅面向 SQView 的 surface props helper')
assert.match(
  wrapperExtraProps[1],
  /configItem\?\.component !== 'SQView'\) return \{\}[\s\S]*dashboardLayoutSurface: props\.dashboardLayoutSurface/
)

console.log('dashboard layout surface contract tests passed')
