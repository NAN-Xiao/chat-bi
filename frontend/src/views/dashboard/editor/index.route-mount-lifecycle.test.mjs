import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./index.vue', import.meta.url)), 'utf8')
const loadCanvas =
  source.match(/const loadCanvasFromRoute = async \(\) => \{([\s\S]*?)\r?\n\}/)?.[0] || ''

assert.match(
  source,
  /const dataInitState = ref\(false\)/,
  '编辑页首次渲染前必须关闭资源就绪门，不能挂载残留画布'
)
assert.ok(loadCanvas, '需要保留统一的路由画布加载入口')

const draftReturnIndex = loadCanvas.indexOf('canvasStateReady = true')
const closeGateIndex = loadCanvas.indexOf('dataInitState.value = false')
const firstAwaitIndex = loadCanvas.indexOf('await ')
assert.ok(draftReturnIndex >= 0, '匹配的未保存创建态草稿需要保留快速返回')
assert.ok(
  closeGateIndex > draftReturnIndex,
  '草稿快速返回必须发生在关闭已就绪画布之前，避免草稿路径额外卸载'
)
assert.ok(
  closeGateIndex >= 0 && closeGateIndex < firstAwaitIndex,
  '非草稿路径必须在第一次异步等待前关闭旧画布'
)

const draftBranch =
  loadCanvas.match(
    /if \(\s*sourceKey &&[\s\S]*?dashboardStore\.hasUnsavedCanvasChanges\s*\) \{([\s\S]*?)\r?\n\s*\}/
  )?.[1] || ''
assert.match(
  draftBranch,
  /dataInitState\.value = true[\s\S]*?canvasStateReady = true[\s\S]*?return/,
  '草稿快速返回需要显式恢复资源就绪门'
)
assert.match(
  loadCanvas,
  /finally \{\s*if \(loadVersion === routeLoadVersion\) \{\s*dataInitState\.value = true\s*canvasStateReady = true/,
  '只有当前加载版本可以在 finally 中放行画布'
)
assert.match(
  source,
  /<template v-if="dataInitState">\s*<Toolbar[\s\S]*?<DashboardEditor/,
  '工具栏和画布必须由同一个资源就绪门控制'
)
assert.doesNotMatch(
  source,
  /<DashboardEditor\s+v-if="dataInitState"/,
  '资源就绪门应控制完整编辑 UI，不能只控制画布子树'
)

console.log('Dashboard editor route mount lifecycle tests passed')
