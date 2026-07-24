import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/dashboard/preview/reportPromptKeyboard.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { shouldSubmitReportPromptOnEnter } = await import(moduleUrl)

assert.equal(
  shouldSubmitReportPromptOnEnter({ key: 'Enter' }),
  true,
  '普通 Enter 应提交报表解读问题'
)

for (const modifier of ['shiftKey', 'ctrlKey', 'altKey', 'metaKey']) {
  assert.equal(
    shouldSubmitReportPromptOnEnter({ key: 'Enter', [modifier]: true }),
    false,
    `${modifier} 与 Enter 组合时不应提交`
  )
}

assert.equal(
  shouldSubmitReportPromptOnEnter({ key: 'Enter', isComposing: true }),
  false,
  '中文输入法组合输入期间按 Enter 不应提交'
)
assert.equal(
  shouldSubmitReportPromptOnEnter({ key: 'Enter', keyCode: 229 }),
  false,
  '旧浏览器输入法组合输入期间按 Enter 不应提交'
)
assert.equal(
  shouldSubmitReportPromptOnEnter({ key: 'a' }),
  false,
  '非 Enter 按键不应提交'
)

console.log('report prompt keyboard tests passed')
