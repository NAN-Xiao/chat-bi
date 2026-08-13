import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./AnalysisAssistantDock.vue', import.meta.url), 'utf8')

test('分析助手切换状态直接来自 WorkspaceContext', () => {
  assert.match(source, /workspaceContextState/)
  assert.match(
    source,
    /const workspaceContextSwitching = computed\(\(\) => workspaceContextState\.phase === 'switching'\)/
  )
})

test('切换工作空间时中止流并清空旧对话和选择项', () => {
  assert.match(source, /streamController\.value\?\.abort\(\)/)
  assert.match(source, /selectedCustomPromptId\.value = null/)
  assert.match(source, /selectedDataSkillId\.value = null/)
  const watcherStart = source.search(/watch\(\r?\n  \(\) => workspaceContextState\.phase/)
  assert.ok(watcherStart >= 0)
  const watcher = source.slice(watcherStart, watcherStart + 500)
  assert.match(watcher, /streamController\.value\?\.abort\(\)/)
  assert.match(watcher, /clearMessages\(\)/)
})

test('切换期间阻断助手请求和历史操作', () => {
  for (const functionName of [
    'loadHistoryList',
    'loadConversation',
    'deleteHistoryConversation',
    'generateDashboardFromMessage',
    'runQuestion',
    'sendMessage',
    'regenerateMessage',
  ]) {
    const functionStart = source.indexOf(`const ${functionName}`)
    assert.ok(functionStart >= 0, `${functionName} should exist`)
    const nextFunction = source.indexOf('\nconst ', functionStart + 1)
    const body = source.slice(functionStart, nextFunction > 0 ? nextFunction : functionStart + 1800)
    assert.match(body, /workspaceContextSwitching\.value/, functionName)
  }
})

test('数据源加载完成后若切换已开始不再追加旧问题', () => {
  const runStart = source.indexOf('const runQuestion')
  const loadCall = source.indexOf('await analysisContext.loadDatasources()', runStart)
  const appendGuard = source.indexOf('if (workspaceContextSwitching.value) return', loadCall)
  const appendStart = source.indexOf('if (options.appendUser !== false)', loadCall)

  assert.ok(loadCall > runStart)
  assert.ok(appendGuard > loadCall && appendGuard < appendStart)
})

test('切换期间的过期响应保持静默且控件统一禁用', () => {
  assert.match(source, /isWorkspaceContextStaleError/)
  assert.match(source, /workspaceContextSwitching \|\| isStreaming/)
  assert.match(source, /workspaceContextSwitching \|\| isStreaming \|\| generatingDashboard/)
})
