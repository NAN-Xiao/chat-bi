import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8')
const behaviorPath = join(currentDir, 'SQComponentWrapper.externalActions.ts')

assert.equal(existsSync(behaviorPath), true, '外部刷新和插槽契约需要可执行的行为单元')

const build = await esbuild.build({
  entryPoints: [behaviorPath],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  resolveSQComponentWrapperMoreActionsSlotProps,
  runSQComponentWrapperRefresh,
} = await import(moduleUrl)

{
  const calls = []
  const result = await runSQComponentWrapperRefresh({
    refreshExecutor: async () => calls.push('external'),
    refreshing: false,
    fallback: async () => calls.push('fallback'),
  })
  assert.equal(result, 'external')
  assert.deepEqual(calls, ['external'], '外部执行器存在时不得继续执行普通刷新路径')
}

{
  const calls = []
  const result = await runSQComponentWrapperRefresh({
    refreshExecutor: async () => calls.push('external'),
    refreshing: true,
    fallback: async () => calls.push('fallback'),
  })
  assert.equal(result, 'skipped')
  assert.deepEqual(calls, [], '宿主刷新中必须阻止重复触发')
}

{
  const calls = []
  const result = await runSQComponentWrapperRefresh({
    refreshing: false,
    fallback: async () => calls.push('fallback'),
  })
  assert.equal(result, 'fallback')
  assert.deepEqual(calls, ['fallback'], '未注入执行器时必须保留普通刷新路径')
}

{
  const viewInfo = { id: 'chart-1', chart: { title: 'ROI' } }
  assert.deepEqual(
    resolveSQComponentWrapperMoreActionsSlotProps(viewInfo),
    { viewInfo },
    '更多菜单插槽必须把当前图表对象原样暴露给宿主'
  )
}

assert.match(
  source,
  /refreshExecutor\?: \(\) => Promise<void>/,
  '共享包装器需要允许宿主接管刷新命令'
)
assert.match(source, /refreshing\?: boolean/, '共享包装器需要接收宿主控制的刷新状态')
assert.match(
  source,
  /runSQComponentWrapperRefresh\(\{[\s\S]*?refreshExecutor:\s*props\.refreshExecutor[\s\S]*?refreshing:\s*props\.refreshing[\s\S]*?fallback:\s*refreshDashboardChartData/,
  '组件必须接入可执行行为单元的外部刷新分支'
)
assert.match(source, /:loading="refreshing"/, '刷新按钮需要显示统一的加载状态')
assert.match(source, /:disabled="refreshing"/, '刷新按钮需要在加载期间禁用')
assert.match(
  source,
  /<slot name="more-actions" v-bind="moreActionsSlotProps"\s*\/>/,
  '更多菜单需要向宿主暴露当前图表信息'
)

assert.match(source, /dashboardApi\.preview_sql/, '普通看板 SQL 刷新逻辑必须保留')
assert.match(source, /refreshMixedChartData/, '混合数据刷新逻辑必须保留')
assert.match(source, /ChartFullscreenDialog/, '全屏图表能力必须保留')
assert.match(source, /toggleReportPrompt/, '图表解读能力必须保留')
assert.match(source, /exportChartTableData/, '导出能力必须保留')
assert.match(source, /moveChartToDashboard/, '移动图表能力必须保留')

console.log('SQComponentWrapper external actions tests passed')
