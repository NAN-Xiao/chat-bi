import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const executorPath = join(currentDir, 'dashboardSqlPreviewExecutor.ts')

assert.equal(existsSync(executorPath), true, '共享抽屉需要提供可独立测试的预览执行器解析层')

const build = await esbuild.build({
  entryPoints: [executorPath],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { resolveDashboardSqlPreviewExecutor } = await import(moduleUrl)

const nativeRequest = {
  datasource: 8,
  sql: 'SELECT DATE_ADD(dt, period) AS period FROM roi_events',
  pivot: { enabled: false },
  title: 'ROI 趋势',
  chartType: 'line',
  chartConfig: { xAxis: [{ value: 'period' }] },
}

{
  const calls = []
  const defaultExecutor = resolveDashboardSqlPreviewExecutor(undefined, async (request) => {
    calls.push(request)
    return { status: 'success', fields: ['period'], data: [], message: '' }
  })

  await defaultExecutor(nativeRequest)
  assert.deepEqual(calls, [
    {
      datasource: 8,
      sql: nativeRequest.sql,
      pivot: { enabled: false },
    },
  ], '普通看板默认执行器必须保留现有 dashboard preview 请求契约')
}

{
  const calls = []
  const customExecutor = resolveDashboardSqlPreviewExecutor(async (request) => {
    calls.push(request)
    return { status: 'success', fields: ['period'], data: [], message: '' }
  }, async () => assert.fail('注入执行器时不得调用普通看板 preview API'))

  await customExecutor(nativeRequest)
  assert.deepEqual(calls, [nativeRequest], '注入执行器必须原样接收原生方言 SQL 和图表上下文')
}

console.log('DashboardSqlEditor preview executor tests passed')
