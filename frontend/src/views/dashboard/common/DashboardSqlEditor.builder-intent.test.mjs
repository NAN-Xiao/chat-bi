import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'DashboardSqlEditor.vue')
const source = readFileSync(componentPath, 'utf8')

assert.doesNotMatch(source, /生成意图/, '图表配置界面不应再展示或引用“生成意图”')
assert.doesNotMatch(source, /placeholder="补充业务口径或想看的结论"/, '图表配置界面不应再展示生成意图输入框')
assert.doesNotMatch(source, /v-model="sqlBuilder\.aiIntent"/, '界面不应再绑定隐藏的生成意图输入状态')
assert.doesNotMatch(source, /\baiIntent:/, 'SQL Builder 状态保存中不应继续保留隐藏的生成意图字段')
assert.doesNotMatch(source, /sqlBuilder\.aiIntent\s*=/, '恢复旧配置时不应把旧生成意图写回隐藏状态')
assert.doesNotMatch(source, /String\(sqlBuilder\.aiIntent/, '本地意图推断不应再读取隐藏的生成意图状态')
assert.match(
  source,
  /intent:\s*''/,
  '调用 AI SQL 生成接口时应显式传空 intent，避免旧隐藏值影响生成结果'
)
