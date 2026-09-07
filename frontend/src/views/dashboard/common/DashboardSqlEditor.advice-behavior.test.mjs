import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = readFileSync(new URL('./DashboardSqlEditor.vue', import.meta.url), 'utf8')
const names = ['cleanBuilderAdviceText', 'shouldHideBuilderAdviceItem', 'cleanBuilderAdviceItems', 'setBuilderAgentAdvice']
const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'))
const ast = ts.createSourceFile('editor.ts', script, ts.ScriptTarget.Latest, true)
const functions = names.map((name) => {
  const declaration = ast.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === name)
  assert.ok(declaration, `Missing ${name}`)
  return declaration.getText(ast)
}).join('\n')

function advice(value) {
  const context = vm.createContext({
    builderAgentAdvice: {},
    unique: (items) => [...new Set(items)],
    currentBuilderReadableIssues: () => [],
    fallbackBuilderConfigSuggestions: () => ['时间范围：固定使用 dt', '分组项：先不填'],
    mergeBuilderSuggestions: (a, b) => [...a, ...b],
    builderSuggestionOrder: () => 0,
    inferBuilderIntentText: () => '归因分析',
  })
  vm.runInContext(ts.transpileModule(functions, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, context)
  context.setBuilderAgentAdvice(value)
  return JSON.parse(JSON.stringify(context.builderAgentAdvice))
}

test('blocking SQL and JOIN errors remain visible with the actual repair advice', () => {
  const errors = [
    '归因 SQL 无法按当前方言解析。',
    '归因结果必须保留零贡献行，使用触点统计 LEFT JOIN 贡献统计。',
    'SQL 字段 entity_id 未由来源 CTE 输出。',
    '跨表关联必须保留主体边界。',
  ]
  const result = advice({ severity: 'warning', issues: errors, advice: '请修复 SQL 字段来源和完整触点集合。' })
  assert.deepEqual(result.issues, errors)
  assert.equal(result.advice, '请修复 SQL 字段来源和完整触点集合。')
  assert.deepEqual(result.suggestions, [])
})

test('a failure message without issues is preserved', () => {
  const result = advice({ severity: 'warning', message: 'SQL 生成服务超时，请重试。', advice: '请重试。' })
  assert.equal(result.message, 'SQL 生成服务超时，请重试。')
})

test('ordinary nonblocking advice keeps configuration suggestions', () => {
  const result = advice({ severity: 'info', suggestions: ['添加分组项以比较各渠道'] })
  assert.ok(result.suggestions.includes('添加分组项以比较各渠道'))
  assert.ok(result.suggestions.includes('时间范围：固定使用 dt'))
})
