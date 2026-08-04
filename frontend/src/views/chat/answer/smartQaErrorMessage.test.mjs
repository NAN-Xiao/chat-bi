import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

import { resolveSmartQaErrorMessage } from './smartQaErrorMessage.ts'

const messages = {
  'chat.task_error.http_400': '请求参数有误，请检查后重试。',
  'chat.task_error.http_401': '登录状态已失效，请重新登录。',
  'chat.task_error.http_403': '当前账号没有执行此操作的权限。',
  'chat.task_error.http_404': '问数任务不存在或已失效，请重新提问。',
  'chat.task_error.http_422': '请求参数校验失败，请重新提问。',
  'chat.task_error.http_429': '请求过于频繁，请稍后重试。',
  'chat.task_error.http_500': '问数服务处理异常，请稍后重试。',
  'chat.task_error.http_502': '问数服务网关异常，请稍后重试。',
  'chat.task_error.http_503': '问数服务暂时不可用，请稍后重试。',
  'chat.task_error.http_504': '问数服务响应超时，请稍后重试。',
  'chat.task_error.network': '网络连接异常，请检查网络后重试。',
  'chat.task_error.generic': '问数任务执行失败，请稍后重试。',
  'chat.permission_denied_tip': '当前账号没有访问本问题所需数据的权限。',
  'chat.task_error.data_unavailable': '当前数据源缺少本次问题所需的数据。',
}

const t = (key) => messages[key] || key

test('将 Axios 404 转换为中文任务失效提示', () => {
  const error = Object.assign(new Error('Request failed with status code 404'), {
    response: { status: 404, data: 'Task not found' },
  })

  assert.equal(resolveSmartQaErrorMessage(error, t), messages['chat.task_error.http_404'])
})

test('优先保留后端中文业务说明', () => {
  const error = {
    response: {
      status: 429,
      data: { message: '当前租户请求过于频繁，请稍后再试。' },
    },
  }

  assert.equal(resolveSmartQaErrorMessage(error, t), '当前租户请求过于频繁，请稍后再试。')
})

test('解析 SSE 嵌套 data_unavailable 中文消息', () => {
  const error = JSON.stringify({
    error_type: 'data_unavailable',
    message: '当前数据源缺少英雄稀有度字段。',
  })

  assert.equal(resolveSmartQaErrorMessage(error, t), '当前数据源缺少英雄稀有度字段。')
})

test('业务错误类型使用本地化提示', () => {
  assert.equal(
    resolveSmartQaErrorMessage({ error_type: 'permission_denied' }, t),
    messages['chat.permission_denied_tip']
  )
  assert.equal(
    resolveSmartQaErrorMessage({ error_type: 'data_unavailable' }, t),
    messages['chat.task_error.data_unavailable']
  )
})

test('已知 HTTP 状态使用对应的本地化提示', () => {
  for (const status of [400, 401, 403, 404, 422, 429, 500, 502, 503, 504]) {
    assert.equal(
      resolveSmartQaErrorMessage(
        { response: { status, data: { message: 'Request failed' } } },
        t
      ),
      messages[`chat.task_error.http_${status}`]
    )
  }
})

test('无响应异常显示网络中文提示', () => {
  assert.equal(resolveSmartQaErrorMessage({ request: {} }, t), messages['chat.task_error.network'])
})

test('未知英文异常不直接展示给用户', () => {
  assert.equal(
    resolveSmartQaErrorMessage(new Error('opaque internal failure'), t),
    messages['chat.task_error.generic']
  )
})

test('不展示缺少标准错误字段的原始 JSON', () => {
  assert.equal(
    resolveSmartQaErrorMessage(JSON.stringify({ context: '内部中文诊断信息' }), t),
    messages['chat.task_error.generic']
  )
})

test('ChartAnswer 统一使用 AI 看板错误解析器', () => {
  const source = fs.readFileSync(new URL('./ChartAnswer.vue', import.meta.url), 'utf8')

  assert.match(source, /import \{ resolveSmartQaErrorMessage \} from '.\/smartQaErrorMessage'/)
  assert.match(source, /resolveSmartQaErrorMessage\(error, t\)/)
  assert.match(source, /resolveSmartQaErrorMessage\(latestRecord\.error, t\)/)
  assert.doesNotMatch(source, /normalizeTaskError/)
  assert.doesNotMatch(source, /Error:\$\{error\}/)
})
