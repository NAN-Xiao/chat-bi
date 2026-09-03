import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const editorPath = fileURLToPath(new URL('./DashboardSqlEditor.vue', import.meta.url))
const formPath = fileURLToPath(new URL('./DashboardAnalysisModelForm.vue', import.meta.url))
const editorSource = readFileSync(editorPath, 'utf8')

test('keeps analysis model forms in a dedicated component', () => {
  assert.equal(existsSync(formPath), true, '分析模型表单组件必须存在')
  assert.match(editorSource, /import DashboardAnalysisModelForm from ['"]\.\/DashboardAnalysisModelForm\.vue['"]/, 'SQL 编辑器必须引入独立模型表单组件')
  assert.match(editorSource, /<DashboardAnalysisModelForm[\s\S]*\/>/, 'SQL 编辑器必须渲染独立模型表单组件')
})

test('keeps global filters and grouping inside the model form component', () => {
  const source = readFileSync(formPath, 'utf8')
  assert.match(source, />全局筛选</, '模型组件必须包含全局筛选')
  assert.match(source, />分组项</, '模型组件必须包含分组配置')
  assert.match(source, /BuilderFilterTree/, '模型组件必须复用筛选树')
})
