import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const layoutSource = fs.readFileSync(new URL('./LayoutDsl.vue', import.meta.url), 'utf8')
const dashboardSource = fs.readFileSync(
  new URL('../../views/dashboard/preview/SQPreviewShow.vue', import.meta.url),
  'utf8'
)

test('uses distinct subtle backgrounds for top and dashboard side navigation', () => {
  assert.match(layoutSource, /--top-nav-bg: var\(--theme-header-bg\);/)
  assert.match(layoutSource, /\.top-nav-shell[\s\S]*?background: var\(--top-nav-bg\);/)
  assert.match(dashboardSource, /--dashboard-preview-sidebar-bg: var\(--theme-dashboard-sidebar-bg\);/)
})
