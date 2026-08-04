import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const userSource = readFileSync(new URL('./user.ts', import.meta.url), 'utf8')
const datasourceSource = readFileSync(new URL('./datasourceContext.ts', import.meta.url), 'utf8')
const datasourceApiSource = readFileSync(new URL('../api/datasource.ts', import.meta.url), 'utf8')

test('用户信息请求和应用是两个显式步骤', () => {
  assert.match(userSource, /async requestInfo\(config\?: FullRequestConfig\)/)
  assert.match(userSource, /applyInfo\(res: UserInfoDto\)/)
  assert.match(userSource, /const res = await this\.requestInfo/)
})

test('切换验证成功并提交上下文后才应用目标用户信息', () => {
  const requestIndex = userSource.indexOf('const userInfo = await this.requestInfo')
  const commitIndex = userSource.indexOf('workspaceContext.commitSwitch(transaction)', requestIndex)
  const applyIndex = userSource.indexOf('this.applyInfo(userInfo)', requestIndex)

  assert.ok(requestIndex > 0)
  assert.ok(commitIndex > requestIndex)
  assert.ok(applyIndex > commitIndex)
  assert.match(userSource, /assertUserInfoTenant\(userInfo, transaction\.targetTenantId\)/)
})

test('工作空间字段不再写入 localStorage', () => {
  for (const key of [
    'tenantId',
    'tenantPublicId',
    'tenantName',
    'tenantRole',
    'workspaceRole',
    'hasWorkspace',
    'workspaceStatus',
  ]) {
    assert.doesNotMatch(userSource, new RegExp(`wsCache\\.set\\('user\\.${key}'`))
  }
})

test('数据源加载携带显式事务租户并只应用当前事务结果', () => {
  assert.match(datasourceApiSource, /accessibleList: \(config\?: FullRequestConfig\)/)
  assert.match(datasourceSource, /workspaceTenantId: requestTenantId/)
  assert.match(datasourceSource, /workspaceSwitchId: options\?\.workspaceSwitchId/)
  assert.match(
    datasourceSource,
    /workspaceContext\.isCurrentSwitch\(requestTenantId, options\.workspaceSwitchId\)/
  )
})

test('只有当前事务失败时才执行回滚和原数据源恢复', () => {
  assert.match(userSource, /if \(!workspaceContext\.isCurrentSwitch\(transaction\)\) return false/)
  assert.match(userSource, /workspaceContext\.rollbackSwitch\(transaction\)/)
  assert.match(userSource, /datasourceContext\.setDatasourceById\(previous\.datasourceId, false\)/)
})

test('事务开始前解析依赖且开始后的副作用全部受 try catch 保护', () => {
  const switchSource = userSource.slice(
    userSource.indexOf('async switchTenant'),
    userSource.indexOf('async clearActiveTenant')
  )
  const importIndex = switchSource.indexOf("await import('./datasourceContext')")
  const beginIndex = switchSource.indexOf('workspaceContext.beginSwitch')
  const tryIndex = switchSource.indexOf('try {', beginIndex)
  const changingIndex = switchSource.indexOf("phase: 'changing'", beginIndex)

  assert.ok(importIndex > 0 && importIndex < beginIndex)
  assert.ok(tryIndex > beginIndex && tryIndex < changingIndex)
})

test('当前切换失败由 Store 统一显示一次错误', () => {
  assert.match(userSource, /workspaceMode: 'switch'[\s\S]*customError: true/)
  assert.match(datasourceSource, /workspaceMode: 'switch'[\s\S]*customError: true/)
  assert.match(
    userSource,
    /workspaceContext\.rollbackSwitch\(transaction\)[\s\S]*ElMessage\.error\(formatRequestErrorMessage\(error, '工作空间切换失败'\)\)/
  )
})
