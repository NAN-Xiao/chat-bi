import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const requestSource = readFileSync(new URL('./request.ts', import.meta.url), 'utf8')
const authSource = readFileSync(new URL('../api/login.ts', import.meta.url), 'utf8')
const delegateSource = readFileSync(
  new URL('./platformWorkspaceDelegate.ts', import.meta.url),
  'utf8'
)

const requestInterceptorSource = requestSource.slice(
  requestSource.indexOf('this.instance.interceptors.request.use'),
  requestSource.indexOf('// Response interceptor')
)

test('request 在同步入口捕获工作空间且拦截器不重读租户存储', () => {
  assert.match(requestSource, /const capturedConfig = captureWorkspaceRequestConfig\(config\)/)
  assert.match(requestSource, /return this\.instance\.request\(\{[\s\S]*\.\.\.capturedConfig/)
  assert.doesNotMatch(requestInterceptorSource, /wsCache\.get\('user\.tenantId'\)/)
  assert.doesNotMatch(requestSource, /syncTenantContextFromResponse/)
})

test('请求配置暴露启动和显式切换策略', () => {
  assert.match(requestSource, /workspaceMode\?: WorkspaceRequestMode/)
  assert.match(requestSource, /workspaceTenantId\?: string/)
  assert.match(requestSource, /workspaceSwitchId\?: number/)
  assert.match(authSource, /info: \(config\?: FullRequestConfig\) =>/)
  assert.match(authSource, /workspaceMode: 'bootstrap'/)
  assert.match(authSource, /login\/access-token'[\s\S]*workspaceMode: 'none'/)
})

test('成功和失败响应都在业务处理前校验工作空间快照', () => {
  const successValidation = requestSource.indexOf(
    'assertWorkspaceResponseConsumable(response.config, response)'
  )
  const businessHandling = requestSource.indexOf('if (response.data?.code === 0)')
  const errorValidation = requestSource.indexOf(
    'assertWorkspaceResponseConsumable(config, error.response)'
  )
  const errorToast = requestSource.indexOf('this.handleError(error)')

  assert.ok(successValidation > 0 && successValidation < businessHandling)
  assert.ok(errorValidation > 0 && errorValidation < errorToast)
  assert.match(requestSource, /isWorkspaceContextStaleError\(error\)/)
})

test('fetchStream 在第一个 await 前捕获快照并校验响应', () => {
  const fetchStart = requestSource.indexOf('public async fetchStream')
  const fetchSource = requestSource.slice(fetchStart, requestSource.indexOf('// PUT request', fetchStart))
  const capture = fetchSource.indexOf('captureWorkspaceRequest')
  const firstAwait = fetchSource.indexOf('await ')

  assert.ok(capture > 0)
  assert.ok(firstAwait === -1 || capture < firstAwait)
  assert.match(fetchSource, /workspaceContext\.assertConsumable\(workspaceSnapshot, responseTenantId\)/)
})

test('平台代理请求在同步入口捕获租户和 generation', () => {
  assert.match(delegateSource, /capturePlatformWorkspaceDelegateSnapshot/)
  assert.match(delegateSource, /assertPlatformWorkspaceDelegateSnapshot/)
  assert.match(requestSource, /__platformDelegateSnapshot/)
  assert.match(requestSource, /capturePlatformWorkspaceDelegateSnapshot\(\)/)
  assert.match(
    requestSource,
    /assertPlatformWorkspaceDelegateSnapshot\([\s\S]*responseTenantId/
  )
  assert.doesNotMatch(requestInterceptorSource, /getPlatformWorkspaceDelegateTenantId/)
  assert.doesNotMatch(requestInterceptorSource, /isPlatformWorkspaceDelegateSession/)
})
