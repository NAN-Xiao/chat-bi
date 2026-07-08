import assert from 'node:assert/strict'
import esbuild from 'esbuild'

const build = await esbuild.build({
  entryPoints: ['src/views/chat/answer/chartDataResponse.ts'],
  bundle: true,
  platform: 'node',
  format: 'esm',
  write: false,
  absWorkingDir: process.cwd(),
})

const bundledSource = build.outputFiles[0].text
const moduleUrl = `data:text/javascript;base64,${Buffer.from(bundledSource).toString('base64')}`
const { applyChartDataResponseToRecord } = await import(moduleUrl)

const record = {
  id: 460,
  data: {
    status: 'business_notice',
  },
  chart: '',
  analysis: '未能确认 UserRegister 埋点是否存在，相关数值可能受数据源状态影响。',
  analysis_notice: {
    reason: 'event_existence_unknown',
    items: ['UserRegister'],
  },
}

applyChartDataResponseToRecord(record, {
  fields: ['渠道', '新增用户数'],
  data: [
    {
      渠道: 'Facebook',
      新增用户数: 46375,
    },
  ],
  status: 'success',
})

assert.equal(record.analysis_notice, undefined)
assert.deepEqual(record.data.data, [
  {
    渠道: 'Facebook',
    新增用户数: 46375,
  },
])

const noticeRecord = {
  id: 461,
  chart: '{"type":"column"}',
  analysis: '已有分析',
}

applyChartDataResponseToRecord(noticeRecord, {
  status: 'business_notice',
  notice: {
    reason: 'missing_event',
    items: ['PayBuyRet'],
  },
  message: '当前数据源缺少 PayBuyRet 埋点数据。',
})

assert.equal(noticeRecord.chart, '')
assert.deepEqual(noticeRecord.analysis_notice, {
  reason: 'missing_event',
  items: ['PayBuyRet'],
})
assert.equal(noticeRecord.analysis, '当前数据源缺少 PayBuyRet 埋点数据。')

console.log('chat chart data response tests passed')
