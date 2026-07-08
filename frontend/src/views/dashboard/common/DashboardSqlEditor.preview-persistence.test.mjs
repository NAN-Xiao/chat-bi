import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const sourceResultForSaveMatch = source.match(
  /function sourceResultForSave\(type: ChartDataSourceType\) \{([\s\S]*?)\r?\n\}/
)
const writeEditorStateMatch = source.match(
  /function writeEditorStateToViewInfo\([\s\S]*?\) \{([\s\S]*?)\r?\nfunction persistEditorDraftToViewInfo/
)
const initEditorMatch = source.match(/function initEditor\(\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nwatch\(/)

assert.ok(sourceResultForSaveMatch, '需要保留图表数据源结果保存函数')
assert.doesNotMatch(
  sourceResultForSaveMatch[1],
  /\bstatus:\s*result\.status|\bmessage:\s*result\.message/,
  '数据源 lastResult 只能保存可复用数据，不应持久化 SQL 解析/执行错误状态'
)

assert.ok(writeEditorStateMatch, '需要保留编辑器写回图表配置函数')
assert.doesNotMatch(
  writeEditorStateMatch[1],
  /props\.viewInfo\.status\s*=\s*preview\.status|props\.viewInfo\.message\s*=\s*preview\.message/,
  '编辑器写回 viewInfo 时不应持久化预览错误状态和错误消息'
)

assert.ok(initEditorMatch, '需要保留编辑器初始化函数')
assert.doesNotMatch(
  initEditorMatch[1],
  /preview\.status\s*=\s*viewInfo\.status|preview\.message\s*=\s*viewInfo\.message/,
  '编辑器打开时不应从已保存图表配置恢复旧的预览错误状态'
)
