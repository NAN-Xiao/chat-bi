import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/utils/workspacePermission.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const moduleUrl = `data:text/javascript;base64,${Buffer.from(build.outputFiles[0].text).toString('base64')}`
const { canAccessRoiDashboard } = await import(moduleUrl)
assert.equal(typeof canAccessRoiDashboard, 'function', '必须提供严格 ROI 访问判断')

assert.equal(canAccessRoiDashboard({ getTenantRole: 'owner' }), true)
assert.equal(canAccessRoiDashboard({ getTenantRole: 'admin' }), true)
assert.equal(canAccessRoiDashboard({ getTenantRole: 'member' }), false)
assert.equal(
  canAccessRoiDashboard({ getTenantRole: 'owner', isPlatformWorkspaceDelegate: true }),
  false
)
assert.equal(canAccessRoiDashboard({ getTenantRole: 'owner', isSystemAdminUser: true }), false)

console.log('workspace ROI permission tests passed')
