import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { parse } from '@vue/compiler-sfc'
import { baseParse } from '@vue/compiler-dom'

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
  /finally \{\s*if \(routeLoadLifecycle\.isCurrent\(loadVersion\) && routeStateApplied\) \{\s*dataInitState\.value = true\s*canvasStateReady = true/,
  '只有已提交目标状态的当前加载可以在 finally 中放行画布'
)
const findElements = (node, matches = []) => {
  if (node?.type === 1) matches.push(node)
  for (const child of node?.children || []) findElements(child, matches)
  return matches
}

const assertSharedEditorGate = (templateSource) => {
  const ast = baseParse(templateSource)
  const elements = findElements(ast)
  const gates = elements.filter(
    (element) =>
      element.tag === 'template' &&
      element.props.some(
        (prop) => prop.type === 7 && prop.name === 'if' && prop.exp?.content === 'dataInitState'
      )
  )
  assert.equal(gates.length, 1, '完整编辑 UI 必须只有一个资源就绪门')

  const editorComponents = elements.filter((element) =>
    ['Toolbar', 'DashboardEditor'].includes(element.tag)
  )
  const gatedComponents = findElements(gates[0]).filter((element) =>
    ['Toolbar', 'DashboardEditor'].includes(element.tag)
  )
  assert.deepEqual(
    gatedComponents.map((element) => element.tag),
    ['Toolbar', 'DashboardEditor'],
    '资源就绪门必须同时包含工具栏和画布'
  )
  assert.equal(
    editorComponents.every((element) => gatedComponents.includes(element)),
    true,
    '工具栏或画布不能出现在资源就绪门之外'
  )
}

assert.throws(
  () =>
    assertSharedEditorGate(
      '<template v-if="dataInitState"><Toolbar /></template><DashboardEditor />'
    ),
  '模板结构测试必须能识别门外的 DashboardEditor'
)

const templateSource = parse(source).descriptor.template?.content || ''
assert.ok(templateSource, '编辑页必须保留 Vue 模板')
assertSharedEditorGate(templateSource)

console.log('Dashboard editor route mount lifecycle tests passed')
