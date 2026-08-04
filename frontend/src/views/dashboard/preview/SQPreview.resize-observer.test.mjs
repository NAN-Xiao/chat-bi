import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./SQPreview.vue', import.meta.url)), 'utf8')

assert.doesNotMatch(
  source,
  /element-resize-detector|elementResizeDetector/,
  '预览容器不能同时使用两套尺寸监听，否则一次布局变化会重复广播重绘'
)
assert.doesNotMatch(
  source,
  /useEmittLazy/,
  '尺寸回调不能调用会动态注册 Vue 卸载钩子的延迟广播函数'
)
assert.match(source, /const \{ emitter \} = useEmitt\(\)/, '组件应在 setup 阶段取得事件总线')
assert.match(
  source,
  /let viewRenderTimer: ReturnType<typeof window\.setTimeout> \| undefined/,
  '组件需要持有自己的重绘广播定时器'
)
assert.match(
  source,
  /function scheduleViewRenderAll\(\) \{[\s\S]*?if \(viewRenderTimer\) \{\s*return\s*\}[\s\S]*?viewRenderTimer = window\.setTimeout\([\s\S]*?emitter\.emit\('view-render-all', \{ reason: 'resize' \}\)[\s\S]*?}, 150\)/,
  '重复尺寸事件应合并为一次可由组件管理的延迟广播'
)
assert.match(
  source,
  /emitter\.emit\('view-render-all', \{ reason: 'resize' \}\)/,
  '预览尺寸广播必须携带 resize 原因，供图表接收端去重'
)

assert.match(
  source,
  /let lastPreviewSize = \{\s*width: -1,\s*height: -1,?\s*\}/,
  '预览层需要保存上一次测量尺寸'
)

const sizeInitMatch = source.match(
  /const sizeInit = \(force = false, notifyCharts = true\) => \{([\s\S]*?)\r?\n\}/
)
assert.ok(sizeInitMatch, '尺寸初始化函数需要支持首次强制初始化')
assert.match(
  sizeInitMatch[1],
  /if \(\s*!force\s*&&\s*screenWidth === lastPreviewSize\.width\s*&&\s*screenHeight === lastPreviewSize\.height\s*\) \{\s*return false\s*\}/,
  '宽高没有变化时必须提前返回且不广播图表重绘'
)
assert.match(
  sizeInitMatch[1],
  /lastPreviewSize = \{ width: screenWidth, height: screenHeight \}/,
  '实际尺寸变化后必须记录新尺寸'
)
assert.match(
  sizeInitMatch[1],
  /if \(notifyCharts\) \{\s*scheduleViewRenderAll\(\)\s*\}[\s\S]*?return true/,
  '真实尺寸变化默认需要通知图表，但允许首次网格初始化跳过广播'
)

assert.match(
  source,
  /sizeInit\(true, false\)/,
  '首次挂载必须完成布局初始化，但不能广播一次冗余的全量图表重绘'
)
assert.match(
  source,
  /resizeObserver = new ResizeObserver\(\(\) => sizeInit\(\)\)/,
  '挂载后只使用原生 ResizeObserver 复用去重后的测量函数'
)
assert.match(
  source,
  /onBeforeUnmount\(\(\) => \{[\s\S]*?resizeObserver\?\.disconnect\(\)[\s\S]*?if \(viewRenderTimer\) \{[\s\S]*?window\.clearTimeout\(viewRenderTimer\)[\s\S]*?viewRenderTimer = undefined[\s\S]*?\}/,
  '组件卸载时必须取消尚未发出的全局重绘广播'
)

console.log('SQPreview resize observer tests passed')
