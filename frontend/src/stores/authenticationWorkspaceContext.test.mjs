import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const userSource = readFileSync(new URL('./user.ts', import.meta.url), 'utf8')
const requestSource = readFileSync(new URL('../utils/request.ts', import.meta.url), 'utf8')
const routerSource = readFileSync(new URL('../router/watch.ts', import.meta.url), 'utf8')
const loginSource = readFileSync(new URL('../views/login/index.vue', import.meta.url), 'utf8')

test('新认证会话在写入 Token 前清理旧身份和工作空间', () => {
  assert.match(
    userSource,
    /startAuthenticatedSession\(token: string\)[\s\S]*?this\.clear\(\)[\s\S]*?this\.setToken\(token\)/
  )
  assert.match(userSource, /async login[\s\S]*this\.startAuthenticatedSession\(res\.access_token\)/)
  assert.match(loginSource, /userStore\.startAuthenticatedSession\(res\.access_token\)/)
})

test('401 立即使工作空间失效并在跳登录前清理用户 Store', () => {
  assert.match(requestSource, /invalidateAuthenticationSession/)
  assert.match(requestSource, /workspaceContext\.clear\(\)/)
  assert.match(requestSource, /clearPlatformWorkspaceDelegateContext\(\)/)
  assert.match(requestSource, /clearWorkspaceSelectorCaches\(\)/)
  assert.match(requestSource, /useUserStore\(\)\.clear\(\)/)
})

test('登录页只有同时存在 Token 和 uid 才重定向', () => {
  assert.match(
    routerSource,
    /if \(to\.path\.startsWith\('\/login'\) && token && userStore\.getUid\)/
  )
})

test('用户清理同步清空选择器缓存', () => {
  const clearAction = userSource.slice(userSource.indexOf('clear() {'))
  assert.match(clearAction, /clearWorkspaceSelectorCaches\(\)/)
})
