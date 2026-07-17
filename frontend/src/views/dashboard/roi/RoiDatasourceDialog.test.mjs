import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import esbuild from 'esbuild'

const dialogPath = 'src/views/dashboard/roi/RoiDatasourceDialog.vue'
const behaviorPath = 'src/views/dashboard/roi/roiDatasourceDialogBehavior.ts'

assert.equal(existsSync(dialogPath), true)
assert.equal(existsSync(behaviorPath), true, '必须提供生产使用的 ROI 数据源错误映射')

const dialog = readFileSync(dialogPath, 'utf8')
assert.match(dialog, /getRoiDatasourceSaveErrorMessage/)

const build = await esbuild.build({
  entryPoints: [behaviorPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { createRoiDatasourceDialogCloseGuard, getRoiDatasourceSaveErrorMessage } =
  await import(moduleUrl)

const safeDetails = [
  '已有 ROI 图表时不能更换数据源',
  '数据已被其他人修改，请刷新后重试',
  'ROI 配置已被其他人创建或修改，请刷新后重试',
]
for (const detail of safeDetails) {
  assert.equal(
    getRoiDatasourceSaveErrorMessage({ response: { status: 409, data: { detail } } }),
    detail
  )
}

const fallback = '保存 ROI 数据源失败，请稍后重试'
assert.equal(
  getRoiDatasourceSaveErrorMessage({
    response: { status: 409, data: { detail: 'password=secret; Traceback: connection failed' } },
  }),
  fallback
)
assert.equal(
  getRoiDatasourceSaveErrorMessage({ response: { status: 500, data: { detail: safeDetails[0] } } }),
  fallback,
  '非 409 即使 detail 命中也不得透传'
)
assert.equal(getRoiDatasourceSaveErrorMessage(new Error('internal stack')), fallback)

{
  const guard = createRoiDatasourceDialogCloseGuard()
  guard.beginOpen()
  guard.markSaved()
  assert.equal(guard.beginCancel(), false, '保存成功后的关闭事件不得再触发 cancelled')

  guard.beginOpen()
  assert.equal(guard.beginCancel(), true, '重新打开后用户取消必须正常触发 cancelled')
  assert.equal(guard.beginCancel(), false, '同一次关闭只能触发一次 cancelled')
}

assert.match(dialog, /createRoiDatasourceDialogCloseGuard/)
assert.match(dialog, /closeGuard\.markSaved\(\)/)
assert.match(dialog, /closeGuard\.beginCancel\(\)/)

console.log('ROI datasource dialog tests passed')
