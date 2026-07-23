import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const mappingPath = join(currentDir, 'dashboardSqlFieldMapping.ts')
const editorPath = join(currentDir, 'DashboardSqlEditor.vue')

assert.equal(existsSync(mappingPath), true, '共享抽屉需要提供可独立测试的字段映射纯函数')

const build = await esbuild.build({
  entryPoints: [mappingPath],
  bundle: true,
  format: 'esm',
  platform: 'node',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const {
  getStrictFieldMappingIssue,
  reconcileDashboardSqlFieldMapping,
  resolveDashboardSqlTableColumns,
} = await import(moduleUrl)

const invalidMapping = {
  columns: ['removed_column'],
  x: 'removed_dimension',
  y: ['removed_metric'],
  series: 'removed_series',
}
const fields = ['period', 'roi_value', 'channel']
const data = [{ period: '2026-07', roi_value: 1.25, channel: 'organic' }]

{
  const strict = reconcileDashboardSqlFieldMapping(invalidMapping, fields, data, true)
  assert.deepEqual(strict, { columns: [], x: '', y: [], series: '' })
  assert.deepEqual(resolveDashboardSqlTableColumns(strict.columns, fields, true), [])
  assert.equal(getStrictFieldMappingIssue('table', strict), 'columns')
  assert.equal(getStrictFieldMappingIssue('metric', strict), 'y')
  assert.equal(getStrictFieldMappingIssue('line', strict), 'x')
  assert.equal(
    getStrictFieldMappingIssue('pie', { ...strict, y: ['roi_value'] }),
    'series',
    '饼图必须显式选择分类字段，不能猜测首列'
  )
}

{
  const compatible = reconcileDashboardSqlFieldMapping(invalidMapping, fields, data, false)
  assert.deepEqual(compatible, {
    columns: fields,
    x: 'period',
    y: ['roi_value'],
    series: '',
  })
  assert.deepEqual(resolveDashboardSqlTableColumns([], fields, false), fields)
  assert.equal(getStrictFieldMappingIssue('line', compatible), null)
}

const source = readFileSync(editorPath, 'utf8')
assert.match(source, /strictFieldMapping\?: boolean/)
assert.match(source, /strictFieldMappingError/)
assert.match(source, /resolveDashboardSqlTableColumns/)
assert.match(source, /getStrictFieldMappingIssue/)

console.log('DashboardSqlEditor strict field mapping tests passed')
