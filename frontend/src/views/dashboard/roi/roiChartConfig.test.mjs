import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const configPath = join(currentDir, 'roiChartConfig.ts')
const source = readFileSync(configPath, 'utf8')
const build = await esbuild.build({
  entryPoints: [configPath],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
})
const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { getRoiChartSaveErrorMessage } = await import(moduleUrl)

assert.equal(
  getRoiChartSaveErrorMessage({ response: { status: 409, data: { detail: 'password=secret' } } }),
  '数据已被其他人修改，请刷新后重试'
)
assert.equal(
  getRoiChartSaveErrorMessage({ response: { status: 500, data: { detail: 'Traceback' } } }),
  '保存 ROI 图表失败，请稍后重试'
)
assert.equal(getRoiChartSaveErrorMessage(new Error('SQL: DROP TABLE')), '保存 ROI 图表失败，请稍后重试')

assert.doesNotMatch(source, /RoiChartForm|hydrateRoiChartForm|serializeRoiChartForm/)
assert.doesNotMatch(source, /createRoiEditorRequestGuard|getRoiChartMappingError|canCancelRoiEditor/)

console.log('ROI chart config tests passed')
