import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'ResourceTree.vue'), 'utf8')

assert.match(source, /type DashboardScope = 'default' \| 'my'/)
assert.doesNotMatch(source, /ROI_GROUP_ID|ROI_SCOPE|createRoiDashboardEntry|isRoiGroupNode/)
assert.doesNotMatch(source, /useRoiDashboardStore|canAccessRoiDashboard|roiNavigationBehavior/)

const combinedTree = source.match(
  /const buildCombinedTree = \([\s\S]*?\r?\n\}\r?\n\r?\nconst findDashboardNode/
)
assert.ok(combinedTree, '必须保留普通组合看板树构造函数')
assert.doesNotMatch(combinedTree[0], /roi|ROI/)
assert.match(combinedTree[0], /normalizeDefaultDashboardNodes/)
assert.match(combinedTree[0], /normalizeMyDashboardNodes/)

for (const locale of ['en', 'ko-KR', 'zh-CN', 'zh-TW']) {
  const messages = JSON.parse(
    readFileSync(join(currentDir, `../../../i18n/${locale}.json`), 'utf8')
  )
  for (const key of [
    'roi_dashboard',
    'set_roi_datasource',
    'new_roi_dashboard',
    'roi_dashboard_name_tips',
    'roi_dashboard_name_required',
  ]) {
    assert.equal(key in messages.dashboard, false, `${locale} 不应保留 ROI 独立页面文案 ${key}`)
  }
  assert.equal(
    typeof messages.tenant.select_roi_datasource,
    'string',
    `${locale} 必须保留工作空间 ROI 数据源配置文案`
  )
}

console.log('Resource tree no-ROI tests passed')
