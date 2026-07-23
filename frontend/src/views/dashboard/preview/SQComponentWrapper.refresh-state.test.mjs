import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8')

const refreshChartDataMatch = source.match(
  /async function refreshDashboardChartData\(\) \{([\s\S]*?)\r?\n\}/
)

assert.ok(refreshChartDataMatch, '需要保留普通看板批量刷新入口')

const body = refreshChartDataMatch[1]
const beforePreviewSql = body.slice(0, body.indexOf('const result = await previewChartSql'))

assert.match(
  beforePreviewSql,
  /viewInfo\.dataState = 'loading'/,
  '批量刷新每个图表前必须先进入 loading，避免等待接口期间把空数组误判成“没有找到数据”'
)
assert.match(
  beforePreviewSql,
  /viewInfo\.refreshState = 'loading'/,
  '批量刷新每个图表前必须标记 refreshState=loading，让所有看板共用同一套 pending 判断'
)
assert.match(
  body,
  /viewInfo\.dataState = 'ready'[\s\S]*?viewInfo\.refreshState = ''[\s\S]*?markChartSnapshotRefreshed/,
  '批量刷新成功写入结果后必须落成 ready，并清理刷新状态'
)
