import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const menuSource = fs.readFileSync(new URL('./Menu.vue', import.meta.url), 'utf8')
const dashboardTreeSource = fs.readFileSync(
  new URL('../../views/dashboard/common/ResourceTree.vue', import.meta.url),
  'utf8'
)

test('uses compact medium-weight labels for top navigation and semibold dashboard groups', () => {
  assert.match(
    menuSource,
    /\.shuzhi-layout-menu-horizontal[\s\S]*?> \.ed-menu-item,[\s\S]*?font-weight: 500;/
  )
  assert.match(
    dashboardTreeSource,
    /data-virtual-group='true'[\s\S]*?> \.custom-tree-node[\s\S]*?> \.label-tooltip \{[\s\S]*?font-weight: 600;/
  )
})

test('keeps top navigation compact without changing its control height', () => {
  assert.match(menuSource, /\.shuzhi-layout-menu-horizontal[\s\S]*?gap: 2px;/)
  assert.match(
    menuSource,
    /> \.ed-menu-item,[\s\S]*?height: 30px !important;[\s\S]*?margin: 0;[\s\S]*?padding: 0 10px !important;/
  )
})
