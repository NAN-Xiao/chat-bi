import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const nonBlockingAdviceMatch = source.match(
  /function isNonBlockingBuilderAdviceItem\(value: string\) \{([\s\S]*?)\r?\n\}/
)

assert.ok(nonBlockingAdviceMatch, '需要保留配置 Agent 非阻断建议识别函数')
assert.match(
  nonBlockingAdviceMatch[1],
  /事件筛选条件|事件名筛选|未限定\s*event/,
  '事件类指标已自带 eventName，Agent 误报“缺少事件筛选条件”时不能阻断 SQL 生成'
)

assert.match(
  source,
  /function resultWarningItems\(result: any\)/,
  '后端 warnings 必须作为非阻断提示进入前端展示'
)
assert.match(
  source.match(/function updateBuilderAgentAdviceFromResult\(result: any[\s\S]*?\n\}/)?.[0] || '',
  /resultWarningItems\(result\)/,
  '生成 SQL 成功后，warnings 应进入建议区而不是阻断区'
)

const blockingItemsBody =
  source.match(/function resultBlockingIssueItems\(result: any\) \{([\s\S]*?)\r?\n\}/)?.[1] || ''
assert.match(
  blockingItemsBody,
  /result\?\.success === false[\s\S]*?issues/,
  '后端明确判定生成失败时，具体 SQL 校验错误不能被普通建议规则降级'
)

const stopExecutionBody =
  source.match(
    /function stopBuilderExecutionWithAdvice\(result: any, generatedSql = ''\) \{([\s\S]*?)\r?\n\}/
  )?.[1] || ''
assert.match(
  stopExecutionBody,
  /ElMessage\.warning\([\s\S]*?blockingIssues\[0\] \|\| result\?\.message/,
  '停止执行时应直接显示首个真实校验错误'
)
