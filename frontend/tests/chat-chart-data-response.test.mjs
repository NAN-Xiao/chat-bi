import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
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
  error: '上一次请求失败',
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
assert.equal(record.error, undefined)

const permissionDeniedRecord = {
  id: 462,
}

applyChartDataResponseToRecord(permissionDeniedRecord, {
  status: 'failed',
  error_type: 'permission_denied',
  message: '没有查看权限',
})

assert.equal(permissionDeniedRecord.error, '没有查看权限')
assert.equal(permissionDeniedRecord.data.error_type, 'permission_denied')

const permissionDeniedFallbackRecord = {
  id: 463,
}

applyChartDataResponseToRecord(permissionDeniedFallbackRecord, {
  status: 'failed',
  error_type: 'permission_denied',
})

assert.equal(permissionDeniedFallbackRecord.error, '没有查看权限')

const chartAnswerSource = fs.readFileSync(
  path.join(process.cwd(), 'src/views/chat/answer/ChartAnswer.vue'),
  'utf8'
)
assert.match(
  chartAnswerSource,
  /<ChartBlock\s+v-if="showTerminalResult && !message\.record\?\.error"/,
  '只有最终结果就绪且无错误时才应挂载图表块'
)

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
