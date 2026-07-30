import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const source = readFileSync(
  fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url)),
  'utf8'
)

test('restores the persisted datasource before capturing the initial preview signature', () => {
  const initEditorBody = source.match(/function initEditor\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
  const restoreDatasourceIndex = initEditorBody.indexOf(
    'selectedExecutionDatasourceId.value = normalizeExecutionDatasourceId(viewInfo?.datasource)'
  )
  const captureSignatureIndex = initEditorBody.indexOf(
    'lastPreviewSignature.value = currentPreviewSignature()'
  )

  assert.ok(restoreDatasourceIndex >= 0, '编辑器初始化时必须先恢复图表已保存的执行数据源')
  assert.ok(captureSignatureIndex >= 0, '编辑器初始化时必须记录已预览的数据源签名')
  assert.ok(
    restoreDatasourceIndex < captureSignatureIndex,
    '已保存的数据源必须在记录初始预览签名前恢复，避免仅修改图表样式时误报 SQL 已变化'
  )
})

test('keeps datasource in the preview signature so real datasource changes still require preview', () => {
  const signatureBody = source.match(/function currentPreviewSignature\(\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''

  assert.match(
    signatureBody,
    /datasource:\s*selectedExecutionDatasourceId\.value/,
    '执行数据源必须继续参与预览签名校验'
  )
})

test('rebases a legacy chart only when its query source stayed unchanged during datasource loading', () => {
  const loadDatasourceBody = source.match(
    /async function loadExecutionDatasources\(viewInfo: any\) \{([\s\S]*?)\r?\n\}/
  )?.[1] || ''

  assert.match(
    loadDatasourceBody,
    /const initialPreviewSignature = currentPreviewSignature\(\)/,
    '异步加载数据源前必须记录当前查询签名'
  )
  assert.match(
    loadDatasourceBody,
    /currentPreviewSignature\(\) === initialPreviewSignature/,
    '自动补齐历史图表的数据源前必须确认用户没有修改查询配置'
  )
  assert.match(
    loadDatasourceBody,
    /lastPreviewSignature\.value = currentPreviewSignature\(\)/,
    '历史图表自动解析出绑定数据源后必须更新初始预览签名'
  )
  assert.match(
    loadDatasourceBody,
    /!savedDatasourceId/,
    '只允许为未持久化数据源的历史图表重置初始签名'
  )
})
