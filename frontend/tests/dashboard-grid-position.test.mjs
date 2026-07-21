import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/utils/dashboardGridPosition.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { getNextDashboardComponentY, normalizeDashboardGridCoordinate } = await import(moduleUrl)

assert.equal(getNextDashboardComponentY([]), 1)
assert.equal(normalizeDashboardGridCoordinate(0), 1)
assert.equal(normalizeDashboardGridCoordinate(-3), 1)
assert.equal(normalizeDashboardGridCoordinate(4), 4)

assert.equal(
  getNextDashboardComponentY([
    { y: 1, sizeY: 14 },
    { y: 15, sizeY: 8 },
  ]),
  23
)

assert.equal(getNextDashboardComponentY([{ y: 0, sizeY: 14 }]), 15)

console.log('dashboard grid position tests passed')
