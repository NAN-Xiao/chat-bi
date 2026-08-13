import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8')

assert.match(source, /buildDashboardDateFilterRequestForView/)
assert.match(source, /date_filter:\s*buildDashboardDateFilterRequestForView/)
assert.doesNotMatch(source, /buildAppliedDashboardDatePivot/)

const refreshChartDataMatch = source.match(
  /async function refreshChartData\(\) \{([\s\S]*?)\r?\n\}/
)

assert.ok(refreshChartDataMatch, '需要保留看板批量刷新入口')

const body = refreshChartDataMatch[1]
const beforePreviewSql = body.slice(0, body.indexOf('const result = await previewChartSql'))

assert.match(
  beforePreviewSql,
  /prepareDashboardChartRefreshState\(viewInfo, 'loading'\)/,
  '批量刷新前必须复用公共快照保留协议，空快照图表保持空态而不是闪回遮罩'
)
assert.match(
  beforePreviewSql,
  /if \(hasPreviousRows\) \{\s*viewInfo\.dataState = 'loading'\s*viewInfo\.refreshState = 'loading'\s*\}/,
  '有行数据的图表刷新期间必须进入 loading 显示刷新角标；空快照图表不得重新进入 loading 造成遮罩闪回'
)
assert.match(
  body,
  /hasPreviousRows \|\| \(isDashboardQueryBusy\(result\) && hasPreviousShape\)/,
  '刷新失败只能用真实行数据（或 busy 且有结构）回退，空快照不能吞掉错误信息'
)
assert.match(
  body,
  /\} else \{\s*viewInfo\.dataState = 'failed'\s*\}/,
  '失败且没有可回退内容时必须落成 failed，不能停留在 loading 导致遮罩卡住'
)
assert.match(
  body,
  /catch \(error: any\) \{[\s\S]*?hasDashboardChartRows\(viewInfo\)/,
  '请求异常时按行数据决定保留旧内容还是显示错误，空快照不能吞掉异常信息'
)
assert.match(
  body,
  /viewInfo\.dataState = 'ready'[\s\S]*?viewInfo\.refreshState = ''[\s\S]*?markChartSnapshotRefreshed/,
  '批量刷新成功写入结果后必须落成 ready，并清理刷新状态'
)
