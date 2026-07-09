import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

const builderConfigForSaveMatch = source.match(
  /function builderConfigForSave\(\) \{([\s\S]*?)\r?\n\}/
)
const restoreSqlBuilderStateMatch = source.match(
  /function restoreSqlBuilderState\(value: any\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction formulaTokensReferenceMetricIds/
)
const writeEditorStateMatch = source.match(
  /function writeEditorStateToViewInfo\(options: \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction persistEditorDraftToViewInfo/
)

assert.ok(builderConfigForSaveMatch, '需要保留 SQL builder 保存配置入口')
assert.ok(restoreSqlBuilderStateMatch, '需要保留 SQL builder 状态恢复入口')
assert.ok(writeEditorStateMatch, '需要保留编辑器写回图表入口')

assert.doesNotMatch(
  builderConfigForSaveMatch[1],
  /\bactiveTab\b/,
  '保存图表时不应持久化图表配置 tab，避免再次打开时自动进入重面板'
)
assert.doesNotMatch(
  builderConfigForSaveMatch[1],
  /\bmetricItems\b/,
  '保存图表时不应持久化红框内普通分析指标配置'
)
assert.doesNotMatch(
  builderConfigForSaveMatch[1],
  /\bcalculatedMetrics\b/,
  '保存图表时不应持久化红框内公式指标配置'
)

assert.doesNotMatch(
  restoreSqlBuilderStateMatch[1],
  /sqlBuilder\.activeTab\s*=/,
  '打开历史图表时不应从旧 builder 配置恢复图表配置 tab'
)
assert.doesNotMatch(
  restoreSqlBuilderStateMatch[1],
  /sqlBuilder\.metricItems\s*=/,
  '打开历史图表时不应恢复红框内普通分析指标配置'
)
assert.doesNotMatch(
  restoreSqlBuilderStateMatch[1],
  /sqlBuilder\.calculatedMetrics\s*=/,
  '打开历史图表时不应恢复红框内公式指标配置'
)

assert.match(
  writeEditorStateMatch[0],
  /builder:\s*builderConfigForSave\(\)/,
  'SQL sourceConfig 仍保留轻量 builder 信息入口，避免影响时间范围等非红框配置'
)

console.log('dashboard SQL builder persistence tests passed')
