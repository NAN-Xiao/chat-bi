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

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const runSave = async (guard, request, events) => {
  const token = guard.beginSave()
  assert.notEqual(token, null, '打开会话必须允许保存')
  await request.promise
  if (guard.markSaved(token)) events.push('saved')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  const request = deferred()
  const events = []
  guard.beginOpen()
  const pending = runSave(guard, request, events)
  if (guard.beginCancel()) events.push('cancelled')
  request.resolve()
  await pending
  assert.deepEqual(events, ['cancelled'], 'pending save 被取消后旧响应不得 emit saved')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  const oldRequest = deferred()
  const events = []
  guard.beginOpen()
  const oldSave = runSave(guard, oldRequest, events)
  assert.equal(guard.beginCancel(), true)
  guard.beginOpen()
  oldRequest.resolve()
  await oldSave
  assert.deepEqual(events, [], '重开后旧会话响应不得保存或关闭新会话')
  const newToken = guard.beginSave()
  assert.notEqual(newToken, null, '旧响应完成后新会话必须仍保持可保存')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  const request = deferred()
  const events = []
  guard.beginOpen()
  const pending = runSave(guard, request, events)
  request.resolve()
  await pending
  assert.deepEqual(events, ['saved'], '正常保存只能 emit saved')
  assert.equal(guard.beginCancel(), false, '保存完成后的 close 不得 emit cancelled')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  const failedRequest = deferred()
  guard.beginOpen()
  const failed = runSave(guard, failedRequest, [])
  failedRequest.reject(new Error('save failed'))
  await assert.rejects(failed, /save failed/)

  const retryRequest = deferred()
  const events = []
  const retry = runSave(guard, retryRequest, events)
  retryRequest.resolve()
  await retry
  assert.deepEqual(events, ['saved'], '保存失败后当前会话必须允许重试')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  guard.beginOpen()
  assert.equal(guard.beginCancel(), true)
  assert.equal(guard.beginCancel(), false, '同一次会话重复取消必须安全')
}

{
  const guard = createRoiDatasourceDialogCloseGuard()
  guard.beginOpen()
  const first = guard.beginSave()
  const duplicate = guard.beginSave()
  assert.equal(guard.markSaved(first), true)
  assert.equal(guard.markSaved(duplicate), false, '同一次会话重复保存最多完成一次')
}

assert.match(dialog, /createRoiDatasourceDialogCloseGuard/)
assert.match(dialog, /closeGuard\.beginSave\(\)/)
assert.match(dialog, /closeGuard\.markSaved\(saveToken\)/)
assert.match(dialog, /closeGuard\.beginCancel\(\)/)

console.log('ROI datasource dialog tests passed')
