import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/preview/reportInterpretationTarget.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { buildReportInterpretationTarget } = await import(moduleUrl)

const entries = [
  {
    component: { id: 'chart-1' },
    viewInfo: {
      status: 'success',
      data: { data: [{ channel: 'stored', value: 10 }] },
    },
  },
]

{
  const target = buildReportInterpretationTarget('dashboard-1', entries, {
    'chart-1': { data: [{ channel: 'visible', value: 6 }] },
  })
  assert.equal(target.has_visible_data, true, '当前渲染快照有行时应允许解读')
  assert.deepEqual(target.component_ids, ['chart-1'])
}

{
  const target = buildReportInterpretationTarget('dashboard-1', entries, {
    'chart-1': { data: [] },
  })
  assert.equal(target.has_visible_data, false, '当前空快照不能回退到持久化旧行')
}

{
  const target = buildReportInterpretationTarget(
    'dashboard-1',
    [
      ...entries,
      {
        component: { id: 'chart-2' },
        viewInfo: {
          status: 'failed',
          error_type: 'permission_denied',
          data: { data: [{ channel: 'old', value: 99 }] },
        },
      },
    ],
    {}
  )
  assert.equal(target.has_permission_denied, true, '任一图表权限失败时应拒绝整个解读目标')
}

{
  const target = buildReportInterpretationTarget(
    'dashboard-1',
    [
      entries[0],
      entries[0],
      { component: { id: '' }, viewInfo: { data: { data: [] } } },
    ],
    {}
  )
  assert.deepEqual(target.component_ids, ['chart-1'], '组件 ID 应去重并忽略空值')
}

console.log('report interpretation target tests passed')
