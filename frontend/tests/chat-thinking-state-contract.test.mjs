import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const root = process.cwd()

test('会话恢复和任务结束都按全部未完成记录同步输入锁', () => {
  const source = fs.readFileSync(path.join(root, 'src/views/chat/index.vue'), 'utf8')
  const unfinishedStart = source.indexOf('function hasUnfinishedRecord')
  const restoreStart = source.indexOf('function restoreChatTypingState')
  const syncStart = source.indexOf('function syncChatTypingState', restoreStart)
  const stateHelpers = source.slice(
    unfinishedStart,
    source.indexOf('const hasUnfinishedGeneration')
  )
  const finishStart = source.indexOf('async function onChartAnswerFinish')
  const errorStart = source.indexOf('function onChartAnswerError', finishStart)
  const finishSource = source.slice(finishStart, source.indexOf('const loadingOver', finishStart))
  const errorSource = source.slice(errorStart, source.indexOf('function onChatStop', errorStart))

  assert.ok(
    unfinishedStart >= 0 && restoreStart > unfinishedStart && syncStart > restoreStart,
    '应定义全记录、恢复和运行时状态同步函数'
  )
  assert.match(stateHelpers, /hasUnfinishedRecord\(records\)/)
  assert.match(
    stateHelpers,
    /function hasUnfinishedRecord\(records = currentChat\.value\.records\)[\s\S]*shouldMarkChatTypingOnRestore\(records\)/,
    '页面恢复和运行时同步必须共用全记录任务判定'
  )
  assert.match(
    stateHelpers,
    /function syncChatTypingState\(\)[\s\S]*hasUnfinishedRecord\(\)[\s\S]*isTyping\.value = shouldType[\s\S]*loading\.value = shouldType/,
    '任务状态变化后应从当前会话全部未完成记录重新计算输入锁'
  )
  assert.match(finishSource, /syncChatTypingState\(\)/)
  assert.doesNotMatch(finishSource, /isTyping\.value = false|loading\.value = false/)
  assert.match(errorSource, /syncChatTypingState\(\)/)
  assert.doesNotMatch(errorSource, /isTyping\.value = false|loading\.value = false/)
})

test('ChartAnswer 使用组件本地 loading 并与记录生成态组合', () => {
  const source = fs.readFileSync(path.join(root, 'src/views/chat/answer/ChartAnswer.vue'), 'utf8')
  const loadingStart = source.indexOf('const localLoading = ref(false)')
  const loadingEnd = source.indexOf('const stopFlag', loadingStart)
  const loadingSource = source.slice(loadingStart, loadingEnd)

  assert.ok(loadingStart >= 0, 'ChartAnswer 应维护组件本地 loading')
  assert.match(loadingSource, /return props\.loading \|\| localLoading\.value/)
  assert.match(loadingSource, /localLoading\.value = v/)
  assert.match(source, /<BaseAnswer[^>]*:loading="_loading"/)
})
