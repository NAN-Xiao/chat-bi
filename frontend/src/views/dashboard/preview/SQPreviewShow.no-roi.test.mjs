import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQPreviewShow.vue'), 'utf8')

assert.doesNotMatch(source, /RoiDashboardPanel|useRoiDashboardStore/)
assert.doesNotMatch(source, /canAccessRoiDashboard|resolveRoiPreviewAccessPlan/)
assert.doesNotMatch(source, /roiLandingRedirect|dashboard\/roi/)
assert.doesNotMatch(source, /<RoiDashboardPanel/)
assert.match(source, /isUnsupportedDashboardMode/)
assert.match(source, /resolveBusinessDashboardLandingTarget/)

console.log('SQPreviewShow no-ROI tests passed')
