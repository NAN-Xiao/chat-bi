import assert from 'node:assert/strict'
import test from 'node:test'
import { chineseErrorMessage } from './chineseErrorMessage.ts'

const fallback = 'SQL 执行失败，请检查查询配置后重试。'

test('英文请求、SQL 驱动错误和空错误使用中文提示', () => {
  for (const error of [undefined, '', new Error('Network Error'),
    { response: { status: 500, data: { detail: 'Internal Server Error' } } },
    { status: 'failed', message: 'Unknown column foo in field list' }]) {
    assert.equal(chineseErrorMessage(error, fallback), fallback)
  }
})

test('保留中文业务消息并解析嵌套和序列化响应', () => {
  const message = '字段配置无效，请重新选择。'
  for (const error of [{ message }, { reason: message },
    { response: { data: { detail: [{ msg: message }] } } },
    JSON.stringify({ message }), new Error(message)]) {
    assert.equal(chineseErrorMessage(error, fallback), message)
  }
})

test('诊断字段和网关 HTML 不作为用户主提示', () => {
  assert.equal(chineseErrorMessage({ message: 'SQL failed', traceback: '内部诊断' }, fallback), fallback)
  assert.equal(chineseErrorMessage('<html><body>网关异常</body></html>', fallback), fallback)
})

test('循环引用不会阻止读取其余消息字段', () => {
  const error = { message: '请求失败，请重试。' }
  error.response = error
  assert.equal(chineseErrorMessage(error, fallback), error.message)
})
