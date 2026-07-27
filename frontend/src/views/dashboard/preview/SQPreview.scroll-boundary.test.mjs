import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import esbuild from 'esbuild'

const currentDir = dirname(fileURLToPath(import.meta.url))
const frontendRoot = join(currentDir, '..', '..', '..', '..')

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/utils/dashboardGridPosition.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: frontendRoot,
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { getDashboardGridContentRows } = await import(moduleUrl)

assert.equal(
  getDashboardGridContentRows([
    { y: 1, sizeY: 14 },
    { y: 15, sizeY: 8 },
  ]),
  22,
  '滚动内容高度应覆盖最后一个图表的底边，不能额外放大一个网格行'
)
assert.equal(getDashboardGridContentRows([{ y: 0, sizeY: 14 }]), 14)
assert.equal(getDashboardGridContentRows([]), 0)

const previewSource = readFileSync(join(currentDir, 'SQPreview.vue'), 'utf8')
assert.match(previewSource, /getDashboardGridContentRows\(displayComponentData\.value\)/)
assert.match(previewSource, /class="canvas-scroll-spacer"/)
assert.match(previewSource, /:style="canvasScrollSpacerStyle"/)

console.log('SQPreview scroll boundary tests passed')
