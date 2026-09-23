import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const menuSource = fs.readFileSync(new URL('./Menu.vue', import.meta.url), 'utf8')
const dashboardTreeSource = fs.readFileSync(
  new URL('../../views/dashboard/common/ResourceTree.vue', import.meta.url),
  'utf8'
)

test('uses semibold labels for top navigation and dashboard groups only', () => {
  assert.match(
    menuSource,
    /\.shuzhi-layout-menu-horizontal[\s\S]*?> \.ed-menu-item,[\s\S]*?font-weight: 600;/
  )
  assert.match(
    dashboardTreeSource,
    /data-virtual-group='true'[\s\S]*?> \.custom-tree-node[\s\S]*?> \.label-tooltip \{[\s\S]*?font-weight: 600;/
  )
})

test('spaces top navigation items without changing their height', () => {
  assert.match(menuSource, /\.shuzhi-layout-menu-horizontal[\s\S]*?gap: 8px;/)
  assert.match(
    menuSource,
    /> \.ed-menu-item,[\s\S]*?height: 34px !important;[\s\S]*?margin: 0;[\s\S]*?padding: 0 14px !important;/
  )
})

test('shows the active navigation underline for menu items and submenus', () => {
  assert.match(
    menuSource,
    /> \.ed-menu-item\.is-active,[\s\S]*?> \.ed-sub-menu\.is-active \.ed-sub-menu__title[\s\S]*?\.menu-title-text::after \{[\s\S]*?opacity: 1;[\s\S]*?transform: scaleX\(1\);/
  )
})
