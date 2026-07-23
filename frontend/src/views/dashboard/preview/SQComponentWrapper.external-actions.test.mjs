import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8')

assert.match(
  source,
  /refreshExecutor\?: \(\) => Promise<void>/,
  '共享包装器需要允许宿主接管刷新命令'
)
assert.match(source, /refreshing\?: boolean/, '共享包装器需要接收宿主控制的刷新状态')
assert.match(
  source,
  /if \(props\.refreshExecutor\)[\s\S]*?if \(props\.refreshing\) return[\s\S]*?await props\.refreshExecutor\(\)/,
  '外部刷新执行器存在时，应跳过普通刷新路径并防止重复执行'
)
assert.match(source, /:loading="refreshing"/, '刷新按钮需要显示统一的加载状态')
assert.match(source, /:disabled="refreshing"/, '刷新按钮需要在加载期间禁用')
assert.match(
  source,
  /<slot name="more-actions" :view-info="currentViewInfo"\s*\/>/,
  '更多菜单需要向宿主暴露当前图表信息'
)

assert.match(source, /dashboardApi\.preview_sql/, '普通看板 SQL 刷新逻辑必须保留')
assert.match(source, /refreshMixedChartData/, '混合数据刷新逻辑必须保留')
assert.match(source, /ChartFullscreenDialog/, '全屏图表能力必须保留')
assert.match(source, /toggleReportPrompt/, '图表解读能力必须保留')
assert.match(source, /exportChartTableData/, '导出能力必须保留')
assert.match(source, /moveChartToDashboard/, '移动图表能力必须保留')

console.log('SQComponentWrapper external actions tests passed')
