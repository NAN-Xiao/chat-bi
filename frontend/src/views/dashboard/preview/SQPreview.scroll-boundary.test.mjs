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
const { getDashboardGridCellWidth, getDashboardGridContentRows } = await import(moduleUrl)

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

const topLevelCellWidth = getDashboardGridCellWidth(1000, 72, 10, 16)
assert.equal(topLevelCellWidth, (1000 - 16 * 2 + 10) / 72)
assert.equal(16 + topLevelCellWidth * 72 - 10, 984)

const tabCellWidth = getDashboardGridCellWidth(1000, 72, 6, 6)
assert.equal(tabCellWidth, (1000 - 6) / 72)
assert.equal(6 + tabCellWidth * 72 - 6, 994)

assert.equal(getDashboardGridCellWidth(20, 72, 10, 16), 10 / 72)

const previewSource = readFileSync(join(currentDir, 'SQPreview.vue'), 'utf8')
assert.match(previewSource, /getDashboardGridContentRows\(displayComponentData\.value\)/)
assert.match(previewSource, /class="canvas-scroll-spacer"/)
assert.match(previewSource, /:style="canvasScrollSpacerStyle"/)
assert.match(previewSource, /const PREVIEW_EDGE_GAP = 16/)
assert.match(previewSource, /const edgeGap = props\.inTab \? gridGap : PREVIEW_EDGE_GAP/)
assert.match(
  previewSource,
  /getDashboardGridCellWidth\(\s*screenWidth,\s*props\.baseMatrixCount\.x,\s*gridGap,\s*edgeGap\s*\)/
)
assert.match(previewSource, /basePaddingLeft\.value = edgeGap/)
assert.match(
  previewSource,
  /left: cellWidth\.value \* \(gridX - 1\) \+ basePaddingLeft\.value \+ 'px'/
)
assert.match(
  previewSource,
  /width: Math\.max\(0, cellWidth\.value \* item\.sizeX - baseMarginLeft\.value\) \+ 'px'/
)

console.log('SQPreview scroll boundary tests passed')
