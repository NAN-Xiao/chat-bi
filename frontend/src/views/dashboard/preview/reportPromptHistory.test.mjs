import assert from 'node:assert/strict'
import esbuild from 'esbuild'

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
  const storage = createStorage()
  saveReportPromptHistory(storage, '   ', now)
  assert.deepEqual(loadReportPromptHistory(storage, now), [], '空白输入不能写入历史')
}

console.log('report prompt history tests passed')
