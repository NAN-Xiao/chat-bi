import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  enterCurrentWorkspaceAdmin,
  resolveCurrentWorkspaceAdminTenant,
} from '../../utils/workspaceAdminEntry.ts'

const source = readFileSync(fileURLToPath(new URL('./Menu.vue', import.meta.url)), 'utf8')
const menuItemSource = readFileSync(
  fileURLToPath(new URL('./MenuItem.vue', import.meta.url)),
  'utf8'
)

assert.match(
  source,
  /resolveCurrentWorkspaceAdminTenant\(userStore\)/,
  '工作空间管理入口应通过当前工作空间策略生成'
)

assert.doesNotMatch(
  source,
  /adminWorkspaceTenants\.value\[0\]/,
  '不得静默回退到第一个可管理工作空间'
)

assert.match(
  menuItemSource,
  /enterCurrentWorkspaceAdmin\(userStore,/,
  '点击工作空间管理应执行当前工作空间入口策略'
)

const workspaceState = (role, overrides = {}) => ({
  getTenantId: 'tenant-current',
  getTenantPublicId: 'CURRENT',
  getTenantName: '当前工作空间',
  getTenantRole: role,
  workspaceRole: role,
  tenantRole: role,
  isPlatformWorkspaceDelegate: false,
  isSystemAdminUser: false,
  ...overrides,
})

test('普通成员看不到当前工作空间管理入口', () => {
  assert.equal(resolveCurrentWorkspaceAdminTenant(workspaceState('member')), null)
})

test('owner 和 admin 可以管理当前工作空间', () => {
  for (const role of ['owner', 'admin']) {
    assert.deepEqual(resolveCurrentWorkspaceAdminTenant(workspaceState(role)), {
      id: 'tenant-current',
      public_id: 'CURRENT',
      name: '当前工作空间',
      role,
    })
  }
})

test('平台工作空间代理保留当前代理空间管理入口', () => {
  assert.deepEqual(
    resolveCurrentWorkspaceAdminTenant(
      workspaceState('member', { isPlatformWorkspaceDelegate: true })
    ),
    {
      id: 'tenant-current',
      public_id: 'CURRENT',
      name: '当前工作空间',
      role: 'member',
    }
  )
})

test('点击管理入口不切换工作空间', async () => {
  let rememberedTenant
  let navigated = false
  let switchCount = 0
  const store = workspaceState('admin', {
    switchTenant: async () => {
      switchCount += 1
    },
  })

  const entered = await enterCurrentWorkspaceAdmin(store, {
    remember: (tenant) => {
      rememberedTenant = tenant
    },
    navigate: async () => {
      navigated = true
    },
  })

  assert.equal(entered, true)
  assert.equal(store.getTenantId, 'tenant-current')
  assert.equal(switchCount, 0)
  assert.equal(navigated, true)
  assert.equal(rememberedTenant?.id, 'tenant-current')
})

test('无管理权限时点击策略不执行导航', async () => {
  let sideEffectCount = 0
  const entered = await enterCurrentWorkspaceAdmin(workspaceState('member'), {
    remember: () => {
      sideEffectCount += 1
    },
    navigate: async () => {
      sideEffectCount += 1
    },
  })

  assert.equal(entered, false)
  assert.equal(sideEffectCount, 0)
})
