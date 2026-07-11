import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { createRequire } from 'node:module'
import ts from 'typescript'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(import.meta.url)

function loadTsModule(relativePath) {
  const filePath = path.join(root, relativePath)
  const source = fs.readFileSync(filePath, 'utf8')
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  }).outputText
  const module = { exports: {} }
  vm.runInNewContext(
    output,
    {
      exports: module.exports,
      module,
      require,
    },
    { filename: filePath }
  )
  return module.exports
}

const {
  hasRecommendedQuestions,
  isPostAnswerActionPending,
  shouldRetryPostAnswerActionStart,
  shouldRunPostAnswerActions,
} = loadTsModule('src/views/chat/answer/postAnswerActions.ts')

assert.equal(hasRecommendedQuestions(undefined), false)
assert.equal(hasRecommendedQuestions(''), false)
assert.equal(hasRecommendedQuestions('[]'), false)
assert.equal(hasRecommendedQuestions('not json'), false)
assert.equal(hasRecommendedQuestions('["继续看近 30 天趋势"]'), true)

assert.equal(
  shouldRunPostAnswerActions({
    id: 466,
    question: '算一下近七天的LTV',
    finish: true,
    recommended_question: undefined,
  }),
  true
)

assert.equal(
  shouldRunPostAnswerActions({
    id: 467,
    question: '算一下近七天的LTV',
    finish_time: '2026-07-10 14:28:10',
    recommended_question: '[]',
  }),
  true
)

const skippedRecords = [
  undefined,
  { question: '没有记录 ID', finish: true },
  { id: 1, question: '未完成', finish: false },
  { id: 2, first_chat: true, finish: true },
  { id: 3, finish: true, error: 'failed' },
  { id: 4, finish: true, stopped: true },
  { id: 5, finish: true, local_answer: '请先绑定数据源' },
  { id: 6, finish: true, recommended_question: '["已有追问"]' },
]

for (const record of skippedRecords) {
  assert.equal(shouldRunPostAnswerActions(record), false)
}

assert.equal(isPostAnswerActionPending(466, new Set([466])), true)
assert.equal(isPostAnswerActionPending(467, new Set([466])), false)
assert.equal(isPostAnswerActionPending(undefined, new Set([466])), false)

assert.equal(shouldRetryPostAnswerActionStart(false, 1, 3), true)
assert.equal(shouldRetryPostAnswerActionStart(false, 3, 3), false)
assert.equal(shouldRetryPostAnswerActionStart(true, 1, 3), false)

console.log('chat post answer action tests passed')
