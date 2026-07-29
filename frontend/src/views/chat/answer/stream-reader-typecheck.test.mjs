import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const analysisSource = fs.readFileSync(new URL('./AnalysisAnswer.vue', import.meta.url), 'utf8')
const predictSource = fs.readFileSync(new URL('./PredictAnswer.vue', import.meta.url), 'utf8')
const previewSource = fs.readFileSync(new URL('../../dashboard/preview/SQPreview.vue', import.meta.url), 'utf8')

test('流式回答不直接调用可空的共享 reader', () => {
  assert.doesNotMatch(analysisSource, /await currentReader\.read\(\)/)
  assert.doesNotMatch(predictSource, /await currentReader\.read\(\)/)
})

test('预览尺寸监听不使用无效的 ts-expect-error', () => {
  assert.doesNotMatch(
    previewSource,
    /@ts-expect-error[^\n]*\n\s*detectorTargetElement = document\.getElementById\(domId\)/
  )
})
