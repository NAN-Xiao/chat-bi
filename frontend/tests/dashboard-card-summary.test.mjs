import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { createI18n } from 'vue-i18n'
import { renderToString } from 'vue/server-renderer'

const originalCwd = process.cwd()
const root = fileURLToPath(new URL('../', import.meta.url))
const messages = JSON.parse(readFileSync(new URL('../src/i18n/zh-CN.json', import.meta.url), 'utf8'))
process.chdir(root)
const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
try {
  const { default: Header } = await server.ssrLoadModule('/src/views/chat/component/ChartInsightHeader.vue')
  const common = {
    chartType: 'line',
    data: [{ date: '2026-09-26', users: 6 }, { date: '2026-09-27', users: 11 }],
    x: [{ value: 'date' }],
    y: [{ name: '活跃用户数', value: 'users', metricType: 'additive' }],
    showDateContext: false,
    surface: 'dashboard',
  }
  async function render(overrides = {}) {
    const app = createSSRApp(Header, { ...common, ...overrides })
    app.use(createI18n({ legacy: false, locale: 'zh-CN', messages: { 'zh-CN': messages } }))
    return renderToString(app)
  }
  const html = await render()
  assert.match(html, /最新值/, '主数值必须有清楚的含义标签')
  assert.match(html, /title="[^"]*活跃用户数[^"]*2026-09-27[^"]*11/, '主值悬浮说明应带指标、日期和数值')
  assert.match(html, /区间均值/)
  assert.match(html, /区间合计/)
  assert.doesNotMatch(html, /class="configured-trend-anchor"/, '筛选区已有日期时不重复铺日期')

  const latestOnly = await render({ insight: { comparison: { enabled: false }, aggregate: { enabled: false } } })
  assert.match(latestOnly, /最新值/, '关闭附加统计仍须保留主数值')
  assert.match(latestOnly, /class="configured-trend-value"[^>]*>11</)
  assert.doesNotMatch(latestOnly, /class="configured-trend-metrics"/)

  const aggregateOnly = await render({ insight: { comparison: { enabled: false }, aggregate: { metrics: ['average'] } } })
  assert.doesNotMatch(aggregateOnly, /class="configured-trend-group configured-trend-comparison"/)
  assert.match(aggregateOnly, /区间均值/)
  assert.doesNotMatch(aggregateOnly, /区间合计/, '显式只选择均值时不能补出合计')
  console.log('dashboard card summary rendering passed')
} finally {
  await server.close()
  process.chdir(originalCwd)
}
