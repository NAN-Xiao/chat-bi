import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardEditor.vue', import.meta.url)),
  'utf8'
)

assert.doesNotMatch(source, /useEmittLazy/, '尺寸回调不能动态注册 Vue 卸载钩子')
assert.match(source, /onBeforeUnmount/, '编辑器需要在卸载时清理窗口监听和定时器')
assert.match(
  source,
  /let lastEditorSize = \{\s*width: -1,\s*height: -1,?\s*\}/,
  '编辑器需要记录上一次有效尺寸'
)
assert.match(
  source,
  /let viewRenderTimer: ReturnType<typeof window\.setTimeout> \| undefined/,
  '编辑器需要持有自己的重绘定时器'
)

const sizeInitMatch = source.match(/const sizeInit = \(force = false\) => \{([\s\S]*?)\r?\n\}/)
assert.ok(sizeInitMatch, '编辑器需要统一测量尺寸')
assert.match(
  sizeInitMatch[1],
  /if \(\s*!force\s*&&\s*screenWidth === lastEditorSize\.width\s*&&\s*screenHeight === lastEditorSize\.height\s*\) \{\s*return false\s*\}/,
  '相同宽高必须提前返回，不能再次触发全局重绘'
)
assert.match(
  sizeInitMatch[1],
  /lastEditorSize = \{ width: screenWidth, height: screenHeight \}/,
  '有效变化后需要记录新尺寸'
)
assert.match(sizeInitMatch[1], /scheduleViewRenderAll\(\)[\s\S]*?return true/)

const canvasSizeInitMatch = source.match(
  /const canvasSizeInit = \(\) => \{([\s\S]*?)\r?\n\}/
)
assert.ok(canvasSizeInitMatch, '编辑器需要统一处理外部 resize')
assert.match(
  canvasSizeInitMatch[1],
  /sizeInit\(\)[\s\S]*?if \(canvasCoreRef\.value\)/,
  '外部 resize 仍需保留 CanvasCore 内部网格重算；全局图表广播由 sizeInit 自己去重'
)

assert.match(
  source,
  /onBeforeUnmount\(\(\) => \{[\s\S]*?window\.removeEventListener\('resize', canvasSizeInit\)[\s\S]*?window\.clearTimeout\(viewRenderTimer\)/,
  '卸载时必须移除窗口监听并取消待发送的重绘事件'
)

console.log('DashboardEditor resize lifecycle tests passed')
