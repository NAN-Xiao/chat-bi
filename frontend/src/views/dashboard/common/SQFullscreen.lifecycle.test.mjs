import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./SQFullscreen.vue', import.meta.url)), 'utf8')
const mountedBlock = source.match(/onMounted\(\(\) => \{([\s\S]*?)\r?\n\}\)/)?.[0] || ''

assert.match(
  source,
  /const syncFullscreenState = \(\) => \{\s*dashboardStore\.setFullscreenFlag\(!!document\.fullscreenElement\)\s*\}/,
  '全屏组件需要提供从浏览器真实状态同步 Pinia 的入口'
)
assert.match(
  source,
  /const fullscreenChange = \(\) => \{\s*syncFullscreenState\(\)/,
  'fullscreenchange 事件必须复用同一状态同步逻辑'
)
assert.match(
  mountedBlock,
  /syncFullscreenState\(\)[\s\S]*?document\.addEventListener\('fullscreenchange', fullscreenChange\)/,
  '工具栏重挂时必须先同步全屏状态，再恢复事件监听'
)

console.log('Dashboard fullscreen lifecycle tests passed')
