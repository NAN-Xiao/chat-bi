import assert from 'node:assert/strict'
import esbuild from 'esbuild'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/preview/reportPromptHistory.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const {
  REPORT_PROMPT_HISTORY_LIMIT,
  REPORT_PROMPT_HISTORY_TTL_MS,
  loadReportPromptHistory,
  saveReportPromptHistory,
} = await import(moduleUrl)

function createStorage(initialValue) {
  const state = new Map()
  if (initialValue !== undefined) {
    state.set('dashboard_report_prompt_history:v1', initialValue)
  }
  return {
    getItem: (key) => state.get(key) ?? null,
    setItem: (key, value) => state.set(key, value),
    removeItem: (key) => state.delete(key),
    dump: () => state,
  }
}

const now = new Date('2026-07-09T10:00:00.000Z').getTime()

assert.equal(REPORT_PROMPT_HISTORY_LIMIT, 4, '报表解读输入历史最多保留 4 条')
assert.equal(REPORT_PROMPT_HISTORY_TTL_MS, 3 * 24 * 60 * 60 * 1000, '报表解读输入历史 TTL 为 3 天')

{
  const storage = createStorage()
  ;['问题1', '问题2', '问题3', '问题4', '问题5'].forEach((text, index) => {
    saveReportPromptHistory(storage, text, now + index)
  })

  assert.deepEqual(
    loadReportPromptHistory(storage, now + 5).map((item) => item.text),
    ['问题5', '问题4', '问题3', '问题2'],
    '新增历史应置顶，并裁剪到最近 4 条'
  )
}

{
  const storage = createStorage()
  saveReportPromptHistory(storage, '  重复问题  ', now)
  saveReportPromptHistory(storage, '重复问题', now + 1000)

  const history = loadReportPromptHistory(storage, now + 1000)
  assert.deepEqual(
    history.map((item) => item.text),
    ['重复问题'],
    '重复内容应去重并刷新到最新位置'
  )
  assert.equal(history[0].expiresAt, now + 1000 + REPORT_PROMPT_HISTORY_TTL_MS)
}

{
  const storage = createStorage()
  saveReportPromptHistory(
    storage,
    {
      text: '问题带结果',
      answer: '这是解读结果',
      title: '英雄养成情况',
      targetContext: '解读对象：英雄养成情况',
    },
    now
  )

  const history = loadReportPromptHistory(storage, now)
  assert.equal(history[0].text, '问题带结果', '历史应保留问题')
  assert.equal(history[0].answer, '这是解读结果', '历史应同时保留本次解读结果')
  assert.equal(history[0].title, '英雄养成情况', '历史应保留可读标题')
  assert.equal(history[0].targetContext, '解读对象：英雄养成情况', '历史应保留解读对象')
}

{
  const storage = createStorage(
    JSON.stringify([
      { text: '已过期', updatedAt: now - REPORT_PROMPT_HISTORY_TTL_MS - 1, expiresAt: now - 1 },
      { text: '未过期', updatedAt: now - 1000, expiresAt: now + 1000 },
    ])
  )

  assert.deepEqual(
    loadReportPromptHistory(storage, now).map((item) => item.text),
    ['未过期'],
    '读取历史时应清理超过 TTL 的记录'
  )
  assert.deepEqual(
    JSON.parse(storage.getItem('dashboard_report_prompt_history:v1')).map((item) => item.text),
    ['未过期'],
    '过期记录应写回清理结果，避免下次继续出现'
  )
}

{
  const storage = createStorage(
    JSON.stringify([{ text: '旧问题', updatedAt: now - 1000, expiresAt: now + 1000 }])
  )

  const history = loadReportPromptHistory(storage, now)
  assert.equal(history[0].text, '旧问题', '旧版只有问题的历史记录仍应可读取')
  assert.equal(history[0].answer, '', '旧版历史没有结果时应使用空字符串')
}

{
  const storage = createStorage()
  saveReportPromptHistory(storage, '   ', now)
  assert.deepEqual(loadReportPromptHistory(storage, now), [], '空白输入不能写入历史')
}

console.log('report prompt history tests passed')

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentSources = [
  {
    name: '整张看板解读',
    source: readFileSync(join(currentDir, 'SQPreviewHead.vue'), 'utf8'),
  },
  {
    name: '图表区域解读',
    source: readFileSync(join(currentDir, 'SQComponentWrapper.vue'), 'utf8'),
  },
]

for (const component of componentSources) {
  const historyListCount = (
    component.source.match(
      /<div v-if="reportPromptHistory\.length" class="report-prompt-history">/g
    ) || []
  ).length
  assert.equal(historyListCount, 2, `${component.name}应在初始输入态和回答追问态都展示输入历史`)
  assert.match(
    component.source,
    /<div class="report-conversation-footer">[\s\S]*?<div class="report-answer-tip">[\s\S]*?<div v-if="reportPromptHistory\.length" class="report-prompt-history">[\s\S]*?<div class="report-chat-input">/,
    `${component.name}回答态历史和输入框应放在同一个底部 footer 中，避免被回答滚动区遮挡`
  )
  assert.match(
    component.source,
    /@click="selectReportPromptHistory\(item\)"/,
    `${component.name}点击历史时应恢复整条历史记录，而不是只回填问题文本`
  )
  const selectHistoryMatch = component.source.match(
    /function selectReportPromptHistory\(item: ReportPromptHistoryItem\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction abortReportGeneration/
  )
  assert.ok(selectHistoryMatch, `${component.name}应保留历史点击处理函数`)
  assert.match(
    selectHistoryMatch[1],
    /if \(reportHasConversation\.value\) \{[\s\S]*?submitReportPrompt\(\)/,
    `${component.name}在回答态点击旧版只有问题的历史时，应重新生成对应问题的解读内容`
  )
}
