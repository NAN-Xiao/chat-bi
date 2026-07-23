import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const sessionPath = join(currentDir, 'dashboardSqlPreviewSession.ts')
const editorPath = join(currentDir, 'DashboardSqlEditor.vue')

assert.equal(existsSync(sessionPath), true, '共享抽屉需要提供 preview session/generation 协调器')

const build = await esbuild.build({
  entryPoints: [sessionPath],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { createDashboardSqlPreviewSession } = await import(moduleUrl)

let resolveA
const slowA = new Promise((resolve) => {
  resolveA = resolve
})
const state = { fields: [], data: [], lastPreviewSignature: '' }
const session = createDashboardSqlPreviewSession()

session.open()
const tokenA = session.begin('signature-a')
const commitA = slowA.then((result) => {
  if (!session.canCommit(tokenA, 'signature-a')) return false
  Object.assign(state, result, { lastPreviewSignature: tokenA.signature })
  return true
})

session.close()
session.open()
const tokenB = session.begin('signature-b')
assert.equal(session.canCommit(tokenB, 'signature-b'), true)
Object.assign(state, {
  fields: ['field_b'],
  data: [{ field_b: 2 }],
  lastPreviewSignature: tokenB.signature,
})

resolveA({ fields: ['field_a'], data: [{ field_a: 1 }] })
assert.equal(await commitA, false, '关闭 A 并打开 B 后，A 的迟到响应必须失效')
assert.equal(session.isLatest(tokenA), false, 'A 的迟到 finally 不得清理 B 的 loading')
assert.deepEqual(state, {
  fields: ['field_b'],
  data: [{ field_b: 2 }],
  lastPreviewSignature: 'signature-b',
})

const tokenB1 = session.begin('signature-b')
const tokenB2 = session.begin('signature-b')
assert.equal(session.canCommit(tokenB1, 'signature-b'), false, '同一会话内新 generation 必须淘汰旧请求')
assert.equal(session.canCommit(tokenB2, 'changed-signature'), false, '请求期间签名变化必须阻止提交')
assert.equal(session.canCommit(tokenB2, 'signature-b'), true)

session.switchView()
assert.equal(session.canCommit(tokenB2, 'signature-b'), false, '切换 viewInfo 必须淘汰旧请求')

const source = readFileSync(editorPath, 'utf8')
assert.match(source, /createDashboardSqlPreviewSession/)
assert.match(source, /previewSession\.open\(\)/)
assert.match(source, /previewSession\.close\(\)/)
assert.match(source, /previewSession\.switchView\(\)/)
assert.match(source, /previewSession\.canCommit\(previewToken, currentPreviewSignature\(\)\)/)
assert.match(
  source,
  /if \(previewSession\.isLatest\(previewToken\)\) \{[\s\S]*if \(useGlobalLoading\)[\s\S]*clearBuilderLoading\(\)/,
  '只有当前 generation 可以结束对应的预览 loading'
)

console.log('DashboardSqlEditor preview session tests passed')
